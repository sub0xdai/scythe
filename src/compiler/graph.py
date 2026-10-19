"""Compile config + timeline into one ffmpeg invocation.

Pure functions: no ffmpeg execution, no file writes. The renderer
(main.py) executes the returned CompiledGraph.

A timeline is a base video track (contiguous, canvas-sized) plus optional
overlay video tracks composited by time window, plus optional audio
tracks mixed with per-track gain, fades and sidechain ducking.
"""

import os
from dataclasses import dataclass

from src.compiler.keyframes import keyframe_chain
from src.compiler.video import filter_chain, ken_burns_chain
from src.tracks import Timeline, audio_spec_to_tracks, parse_document


def snap_timeline(segments, fps):
    """Return segments with every start/end snapped to the nearest whole frame.

    Deterministic: each boundary becomes round(t * fps) / fps, so chunk
    boundaries and the verification gate compare against frame-exact times
    and per-chunk rounding drift cannot accumulate.
    """
    frame = 1.0 / fps
    return [
        dict(seg, start=round(seg["start"] * fps) / fps,
             end=round(seg["end"] * fps) / fps)
        for seg in segments
    ]


def snap_tracks(timeline, fps):
    """Snap every video track's segment boundaries to whole frames."""
    snapped = [
        type(track)(id=track.id, segments=snap_timeline(track.segments, fps),
                    x=track.x, y=track.y, scale=track.scale,
                    opacity=track.opacity, base=track.base)
        for track in timeline.video
    ]
    return Timeline(video=snapped, audio=list(timeline.audio),
                    duration=snapped[0].segments[-1]["end"]
                    if snapped[0].segments else timeline.duration)


@dataclass(frozen=True)
class AudioSpec:
    """Legacy two-track audio: soundtrack ducked under the voiceover."""
    soundtrack: str | None = None
    voiceover: str | None = None


@dataclass(frozen=True)
class VideoOutput:
    """One encoded output: filtergraph label, filename stem, quality knob."""
    name: str
    label: str
    crf: int = 23


@dataclass(frozen=True)
class CompiledGraph:
    """One ffmpeg invocation: per-input arg lists, the filtergraph, outputs."""
    input_args: list
    filter_complex: str
    outputs: list
    audio_maps: list | None
    duration: float


def _fmt(value):
    return f"{value:g}"


def _drift_expr(pos, drift):
    """Overlay position: base px plus optional px/sec drift over t."""
    if drift:
        return f"{_fmt(pos)}+{_fmt(drift)}*t" if pos else f"{_fmt(drift)}*t"
    return _fmt(pos)


def _fade_chains(seg, duration, alpha):
    chains = []
    fade_in = seg.get("fade_in") or 0
    fade_out = seg.get("fade_out") or 0
    opts = ":alpha=1" if alpha else ""
    if fade_in > 0:
        chains.append(f"fade=t=in:st=0:d={_fmt(min(fade_in, duration))}{opts}")
    if fade_out > 0:
        start = max(0.0, duration - fade_out)
        chains.append(f"fade=t=out:st={_fmt(start)}:d={_fmt(fade_out)}{opts}")
    return chains


def _solid_source(seg, width, height, fps, duration):
    color = seg.get("color")
    if color is None:
        white = seg.get("filter") == "white_flash"
        color = "white" if white else "black"
    return (f"color=c={color}:s={width}x{height}:r={fps}:d={_fmt(duration)}"
            ",format=yuv420p")


def _is_generated(seg):
    return seg.get("asset") is None or seg.get("filter") == "white_flash"


def _segment_chain(label, seg, width, height, fps, easing="linear",
                   alpha=False, track_scale=1.0, track_opacity=1.0):
    """One segment's full picture pipeline, ending at canvas size."""
    duration = seg["end"] - seg["start"]
    frame_count = max(1, int(round(duration * fps)))
    speed = seg.get("speed")
    speed = 1.0 if speed is None else float(speed)
    if speed <= 0:
        raise ValueError(f"segment speed must be > 0, got {speed}")
    box_w = max(2, round(width * track_scale / 2) * 2)
    box_h = max(2, round(height * track_scale / 2) * 2)

    if _is_generated(seg):
        parts = [_solid_source(seg, box_w, box_h, fps, duration)]
        parts.extend(_fade_chains(seg, duration, alpha))
        if alpha:
            opacity = seg.get("opacity", 1.0) * track_opacity
            if opacity < 1.0:
                parts.append(f"colorchannelmixer=aa={_fmt(opacity)}")
            parts.append("format=rgba")
        return (label or "") + ",".join(parts)

    clip_start = seg.get("clip_start", 0)
    clip_end = seg.get("clip_end", clip_start + duration * speed)
    scale_filter = seg.get("scale")
    parts = [
        f"trim=start={_fmt(clip_start)}:end={_fmt(clip_end)}",
        "setpts=PTS-STARTPTS",
        f"fps={fps}",
    ]
    if speed != 1.0:
        parts.append(f"setpts=PTS/{_fmt(speed)}")
    if scale_filter is not None and scale_filter != 1.0:
        parts.append(f"scale=iw*{_fmt(scale_filter)}:ih*{_fmt(scale_filter)}")
    parts += [
        f"scale={box_w}:{box_h}:force_original_aspect_ratio=increase",
        f"crop={box_w}:{box_h}",
    ]
    filters = filter_chain(seg.get("filter"))
    if filters:
        parts.append(filters)
    motion = keyframe_chain(seg.get("keyframes"), box_w, box_h, frame_count)
    if not motion:
        motion = ken_burns_chain(seg.get("effect"), box_w, box_h, fps,
                                 frame_count, easing)
    if motion:
        parts.append(motion)
    parts.append("setsar=1")
    parts.extend(_fade_chains(seg, duration, alpha))
    if alpha:
        opacity = seg.get("opacity", 1.0) * track_opacity
        if opacity < 1.0:
            parts.append(f"colorchannelmixer=aa={_fmt(opacity)}")
        parts.append("format=rgba")
    else:
        parts.append("format=yuv420p")
    return (label or "") + ",".join(parts)


def _audio_maps(n_outputs, chains):
    """Append an asplit when several outputs share the mix; return labels."""
    if n_outputs <= 1:
        return ["[aout]"]
    labels = "".join(f"[aout{k}]" for k in range(n_outputs))
    chains.append(f"[aout]asplit={n_outputs}{labels}")
    return [f"[aout{k}]" for k in range(n_outputs)]


def _track_audio_chain(track, label, span, audio_offset=0.0, cleanup=False):
    """Trim, clean, gain, fade and delay one audio track onto the timeline."""
    duration = track.duration if track.duration is not None else max(
        0.0, span - track.start)
    duration = min(duration, max(0.0, span - track.start))
    if duration <= 0:
        raise ValueError(f"audio track '{track.id}': no room on the timeline")
    offset = track.offset + audio_offset
    parts = [
        f"atrim=start={_fmt(offset)}:end={_fmt(offset + duration)}",
        "asetpts=PTS-STARTPTS",
    ]
    if cleanup:
        parts.append("afftdn=nf=-40:nt=w,agate=threshold=0.02:attack=20:release=250")
    if track.gain != 1.0:
        parts.append(f"volume={_fmt(track.gain)}")
    if track.fade_in > 0:
        parts.append(f"afade=t=in:st=0:d={_fmt(min(track.fade_in, duration))}")
    if track.fade_out > 0:
        parts.append(f"afade=t=out:st={_fmt(max(0.0, duration - track.fade_out))}"
                     f":d={_fmt(track.fade_out)}")
    if track.start > 0:
        parts.append(f"adelay={round(track.start * 1000)}:all=1")
    parts.append(f"apad,atrim=end={_fmt(span)}")
    return f"{label}{','.join(parts)}[at_{track.id}]"


def _audio_chains(tracks, span, config, start_index, inputs, n_outputs=1,
                  project_dir="."):
    """Register audio inputs and return (chains, audio_maps).

    Each track is trimmed, cleaned, gained, faded and delayed onto the
    timeline. A track with duck_under is compressed against the mix of the
    tracks it names, then everything is summed and loudnorm-mastered.
    """
    if not tracks:
        return [], None

    audio_offset = config.get("audio_offset", 0.0)
    cleanup_enabled = config.get("voice_cleanup", True)
    chains = []
    raw_labels = {}
    for k, track in enumerate(tracks):
        inputs.append(["-i", os.path.join(project_dir, track.asset)])
        label = f"[{start_index + k}:a]"
        cleanup = cleanup_enabled and track.cleanup
        chains.append(_track_audio_chain(track, label, span, audio_offset, cleanup))
        raw_labels[track.id] = f"[at_{track.id}]"

    by_id = {track.id: track for track in tracks}
    duckers = [t for t in tracks if t.duck_under]
    for track in duckers:
        unknown = [d for d in track.duck_under if d not in by_id]
        if unknown:
            raise ValueError(f"audio track '{track.id}' ducks under unknown "
                             f"track(s): {unknown}")

    duck_refs = {track.id: 0 for track in tracks}
    for track in duckers:
        for trigger_id in track.duck_under:
            duck_refs[trigger_id] += 1

    available = {}
    for track in tracks:
        count = 1 + duck_refs[track.id]
        if count == 1:
            available[track.id] = [raw_labels[track.id]]
            continue
        splits = "".join(f"[atrig_{track.id}_{j}]" for j in range(count))
        chains.append(f"{raw_labels[track.id]}asplit={count}{splits}")
        available[track.id] = [f"[atrig_{track.id}_{j}]" for j in range(count)]

    threshold = config.get("duck_threshold", 0.02)
    ratio = config.get("duck_ratio", 2)
    used = {track.id: 0 for track in tracks}
    duck_labels = {}
    for track in duckers:
        picks = []
        own = available[track.id][used[track.id]]
        used[track.id] += 1
        for trigger_id in track.duck_under:
            picks.append(available[trigger_id][used[trigger_id]])
            used[trigger_id] += 1
        trigger = f"[atrig_{track.id}]"
        if len(picks) == 1:
            chains.append(f"{picks[0]}anull{trigger}")
        else:
            chains.append(f"{''.join(picks)}amix=inputs={len(picks)}"
                          f":normalize=0{trigger}")
        ducked = f"[aduck_{track.id}]"
        chains.append(
            f"{own}{trigger}sidechaincompress="
            f"threshold={_fmt(threshold)}:ratio={_fmt(ratio)}"
            f":attack=20:release=500{ducked}")
        duck_labels[track.id] = ducked

    final_labels = []
    for track in tracks:
        if track.id in duck_labels:
            final_labels.append(duck_labels[track.id])
            continue
        index = used[track.id]
        final_labels.append(available[track.id][index])
        used[track.id] = index + 1
    for track in tracks:
        assert used[track.id] == len(available[track.id]), \
            f"audio track '{track.id}' label consumed {used[track.id]} of " \
            f"{len(available[track.id])}"

    if len(final_labels) == 1:
        chains.append(f"{final_labels[0]}anull[aout_raw]")
    else:
        chains.append(f"{''.join(final_labels)}amix=inputs={len(final_labels)}"
                      f":normalize=0:duration=longest[aout_raw]")
    loudnorm = ("loudnorm=I={}:TP=-1.5:LRA=11,aresample=48000"
                .format(_fmt(config.get("lufs_target", -14))))
    chains.append(f"[aout_raw]{loudnorm}[aout]")
    return chains, _audio_maps(n_outputs, chains)


XFADE_TRANSITIONS = {
    "fade", "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown",
    "circlecrop", "rectcrop", "distance", "fadeblack", "fadewhite",
    "radial", "smoothleft", "smoothright", "smoothup", "smoothdown",
    "circleopen", "circleclose", "vertopen", "vertclose", "horzopen",
    "horzclose", "dissolve", "pixelize", "diagtl", "diagtr", "diagbl",
    "diagbr", "hlslice", "hrslice", "vuslice", "vdslice", "hblur",
    "fadegrays", "wipetl", "wipetr", "wipebl", "wipebr", "squeezeh",
    "squeezev",
}

XFADE_MODES = {
    "cross_dissolve": "fade",
    "dip_to_black": "fadeblack",
    "dip_to_white": "fadewhite",
    "luma_wipe": "hlslice",
    "slide_left": "slideleft",
    "slide_right": "slideright",
    "slide_up": "slideup",
    "slide_down": "slidedown",
    "circle_open": "circleopen",
    "circle_close": "circleclose",
    "wipe_left": "wipeleft",
    "wipe_right": "wiperight",
    "pixelize": "pixelize",
    "radial": "radial",
    "dissolve": "dissolve",
}


def resolve_transition(mode):
    """Resolve a transition name to a libavfilter xfade transition."""
    if mode in XFADE_MODES:
        return XFADE_MODES[mode]
    if mode in XFADE_TRANSITIONS:
        return mode
    raise ValueError(f"unknown transition: {mode}")


def _boundary_transitions(segments, config, fps):
    """Per-cut (mode, duration) pairs, or None for a plain concat timeline."""
    default_mode = config.get("transition_mode", "hard_cut")
    default_dur = config.get("transition_duration", 0.5)
    explicit = any(seg.get("transition") for seg in segments[1:])
    if default_mode == "hard_cut" and not explicit:
        return None
    frame = 1.0 / fps
    out = []
    for seg in segments[1:]:
        mode = seg.get("transition") or default_mode
        if mode == "hard_cut":
            out.append(("fade", frame))
            continue
        duration = float(seg.get("transition_duration", default_dur))
        if duration <= 0:
            duration = frame
        out.append((resolve_transition(mode), duration))
    return out


def _transition_chains(segments, boundaries):
    """Chained xfade nodes replacing concat. Returns (chains, label, span)."""
    for i, seg in enumerate(segments):
        duration = seg["end"] - seg["start"]
        if i > 0 and boundaries[i - 1][1] >= duration:
            raise ValueError(
                f"segment {i}: transition {boundaries[i - 1][1]}s is not "
                f"shorter than the segment ({duration}s)")

    chains = []
    first = "[seg0]"
    shift = 0.0
    for k in range(1, len(segments)):
        mode, duration = boundaries[k - 1]
        shift += duration
        offset = segments[k]["start"] - shift
        out = "[vcat]" if k == len(segments) - 1 else f"[vx{k}]"
        chains.append(f"{first}[seg{k}]xfade=transition={mode}"
                      f":duration={_fmt(duration)}:offset={_fmt(offset)}{out}")
        first = out
    return chains, "[vcat]", segments[-1]["end"] - shift


def _target_scale(output, width, height):
    """Return the scale filter string for an output, or None for identity."""
    if "max_height" in output:
        max_h = output["max_height"]
        if height <= max_h:
            return None
        w = round(width * max_h / height / 2) * 2
        return f"scale={w}:{max_h}"
    if "resolution" in output:
        tw, th = output["resolution"]
        if (tw, th) == (width, height):
            return None
        return f"scale={tw}:{th}"
    return None


def _output_chains(current, outputs_cfg, width, height, profile, chains):
    """Append per-output tails; return the VideoOutput list for mapping."""
    cfg = outputs_cfg or []
    if not cfg:
        if profile is not None and profile.hw_chain:
            chains.append(f"{current}{profile.hw_chain}[vout]")
            return [VideoOutput("render", "[vout]", 23)]
        return [VideoOutput("render", current, 23)]

    names = [o.get("name") for o in cfg]
    if any(not isinstance(n, str) or not n for n in names):
        raise ValueError("each output needs a non-empty 'name'")
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"duplicate output names: {dupes}")
    scales = [_target_scale(o, width, height) for o in cfg]

    if len(cfg) == 1 and scales[0] is None:
        name, crf = cfg[0]["name"], cfg[0].get("crf", 23)
        if profile is not None and profile.hw_chain:
            chains.append(f"{current}{profile.hw_chain}[vout]")
            return [VideoOutput(name, "[vout]", crf)]
        return [VideoOutput(name, current, crf)]

    hw = profile.hw_chain if profile is not None else ""
    outputs = []
    if len(cfg) > 1:
        split_labels = "".join(f"[o{k}]" for k in range(len(cfg)))
        chains.append(f"{current}split={len(cfg)}{split_labels}")
        for k, (o, scale) in enumerate(zip(cfg, scales)):
            tail = f"{scale},setsar=1" if scale else ""
            if hw:
                tail = f"{tail}{',' if tail else ''}{hw}"
            label = f"[o{k}]"
            if tail:
                label = f"[fo{k}]"
                chains.append(f"[o{k}]{tail}[fo{k}]")
            outputs.append(VideoOutput(o["name"], label, o.get("crf", 23)))
    else:
        o, scale = cfg[0], scales[0]
        tail = f"{scale},setsar=1" if scale else ""
        if hw:
            tail = f"{tail}{',' if tail else ''}{hw}"
        label = current if not tail else "[fo0]"
        if tail:
            chains.append(f"{current}{tail}[fo0]")
        outputs.append(VideoOutput(o["name"], label, o.get("crf", 23)))
    return outputs


def _resolve_timeline(document, audio):
    if isinstance(document, Timeline):
        return document
    extra = audio_spec_to_tracks(audio) if isinstance(audio, AudioSpec) else list(audio or [])
    return parse_document(document, extra)


def compile_graph(config, document, audio=None, project_dir=".", profile=None,
                  ass_path=None):
    """Compile config + timeline (+ audio) into one ffmpeg invocation.

    ``document`` is a segment array, a ``{tracks: [...]}`` cutlist object, or
    an already-parsed Timeline. Asset paths resolve against project_dir.
    Each reference registers its own finite input (no -loop 1); still images
    are materialized into finite clips by the caller before compile. A
    HardwareProfile with a non-empty hw_chain appends upload nodes before the
    encoder. ass_path, when set, burns the generated .ass last in the chain.
    """
    timeline = _resolve_timeline(document, audio)
    width, height = config["resolution"]
    fps = config["fps"]
    easing = config.get("ken_burns_easing", "linear")

    inputs = []
    segment_inputs = {}
    overlay_inputs = {}
    for t_index, track in enumerate(timeline.video):
        for i, seg in enumerate(track.segments):
            key = (t_index, i)
            if _is_generated(seg):
                segment_inputs[key] = None
                continue
            inputs.append(["-i", os.path.join(project_dir, seg["asset"])])
            segment_inputs[key] = len(inputs) - 1
            for j, ov in enumerate(seg.get("overlays", [])):
                inputs.append(["-i", os.path.join(project_dir, ov["asset"])])
                overlay_inputs[(t_index, i, j)] = len(inputs) - 1

    chains = []
    base = timeline.base
    for i, seg in enumerate(base.segments):
        asset = seg.get("asset")
        if not _is_generated(seg):
            if seg.get("filter") is None and config.get("default_filter"):
                seg = dict(seg, filter=config["default_filter"])
            if seg.get("effect") is None and config.get("default_effect"):
                seg = dict(seg, effect=config["default_effect"])
            label = f"[{segment_inputs[(0, i)]}:v]"
        else:
            label = None
        chains.append(f"{_segment_chain(label, seg, width, height, fps, easing)}[seg{i}]")
        for j, ov in enumerate(seg.get("overlays", [])):
            ov_src = f"[{overlay_inputs[(0, i, j)]}:v]"
            opacity = ov.get("opacity", 1.0)
            if opacity < 1.0:
                prep_label = f"[ovp{i}_{j}]"
                chains.append(f"{ov_src}format=rgba,"
                              f"colorchannelmixer=aa={_fmt(opacity)}{prep_label}")
                ov_src = prep_label
            xexpr = _drift_expr(ov.get("x", 0), ov.get("dx", 0))
            yexpr = _drift_expr(ov.get("y", 0), ov.get("dy", 0))
            chains.append(f"[seg{i}]{ov_src}overlay=x='{xexpr}':y='{yexpr}'[seg{i}]")

    boundaries = _boundary_transitions(base.segments, config, fps)
    if boundaries:
        t_chains, label, duration = _transition_chains(base.segments, boundaries)
        chains.extend(t_chains)
        chains.append(f"{label}trim=duration={_fmt(duration)}[vfps]")
        current = "[vfps]"
    elif len(base.segments) == 1:
        duration = base.segments[-1]["end"]
        chains.append(f"[seg0]trim=duration={_fmt(duration)}[vfps]")
        current = "[vfps]"
    else:
        duration = base.segments[-1]["end"]
        seg_labels = "".join(f"[seg{i}]" for i in range(len(base.segments)))
        chains.append(f"{seg_labels}concat=n={len(base.segments)}:v=1:a=0[vcat]")
        chains.append(f"[vcat]trim=duration={_fmt(duration)}[vfps]")
        current = "[vfps]"

    layered = False
    for t_index, track in enumerate(timeline.video):
        if track.base:
            continue
        for i, seg in enumerate(track.segments):
            label = None
            if not _is_generated(seg):
                label = f"[{segment_inputs[(t_index, i)]}:v]"
            chain = _segment_chain(label, seg, width, height, fps, easing,
                                   alpha=True, track_scale=track.scale,
                                   track_opacity=track.opacity)
            seg_label = f"[ovt{t_index}_{i}]"
            chains.append(f"{chain}{seg_label}")
            shifted = f"[ovs{t_index}_{i}]"
            chains.append(f"{seg_label}setpts=PTS+{_fmt(seg['start'])}/TB{shifted}")
            x = track.x + seg.get("x", 0)
            y = track.y + seg.get("y", 0)
            out = f"[vl{t_index}_{i}]"
            chains.append(
                f"{current}{shifted}overlay=x={_fmt(x)}:y={_fmt(y)}"
                f":eof_action=pass:enable='between(t,{_fmt(seg['start'])},"
                f"{_fmt(seg['end'])})'{out}")
            current = out
            layered = True
    if layered:
        chains.append(f"{current}setsar=1[vbase]")
        current = "[vbase]"

    lut = config.get("lut")
    if lut:
        lut_path = os.path.join(project_dir, lut)
        chains.append(f"{current}lut3d=file={lut_path}:interp=tetrahedral[vlut]")
        current = "[vlut]"

    if ass_path:
        chains.append(f"{current}subtitles=filename={ass_path}[vsub]")
        current = "[vsub]"

    outputs = _output_chains(current, config.get("outputs"), width, height,
                             profile, chains)

    audio_chains, audio_maps = _audio_chains(
        timeline.audio, duration, config, len(inputs), inputs, len(outputs),
        project_dir)
    chains.extend(audio_chains)

    return CompiledGraph(inputs, ";".join(chains), outputs, audio_maps, duration)
