"""Compile config + cutlist into one ffmpeg invocation (Spec B).

Pure functions: no ffmpeg execution, no file writes. The renderer
(main.py) executes the returned CompiledGraph.
"""

import os
from dataclasses import dataclass

from src.compiler.video import filter_chain, zoompan_chain

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


@dataclass(frozen=True)
class AudioSpec:
    """Resolved audio inputs. soundtrack is ducked to 0.3 under voiceover."""
    soundtrack: str | None = None
    voiceover: str | None = None


@dataclass(frozen=True)
class CompiledGraph:
    """One ffmpeg invocation: per-input arg lists, the filtergraph, maps."""
    input_args: list[list[str]]
    filter_complex: str
    video_map: str
    audio_map: str | None
    duration: float


def _fmt(value):
    return f"{value:g}"


def _segment_chain(label, seg, width, height, fps, easing="linear"):
    start = seg["start"]
    duration = seg["end"] - start
    filter_name = seg.get("filter")
    effect_name = seg.get("effect")

    if filter_name == "white_flash":
        return (f"color=c=white:s={width}x{height}:r={fps}:d={_fmt(duration)}"
                ",format=yuv420p")
    if seg.get("asset") is None:
        return (f"color=c=black:s={width}x{height}:r={fps}:d={_fmt(duration)}"
                ",format=yuv420p")

    clip_start = seg.get("clip_start", 0)
    clip_end = seg.get("clip_end", clip_start + duration)
    frame_count = max(1, int(round(duration * fps)))
    parts = [
        f"trim=start={_fmt(clip_start)}:end={_fmt(clip_end)}",
        "setpts=PTS-STARTPTS",
        f"fps={fps}",
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
    ]
    filters = filter_chain(filter_name)
    if filters:
        parts.append(filters)
    zoompan = zoompan_chain(effect_name, width, height, fps, frame_count, easing)
    if zoompan:
        parts.append(zoompan)
    parts.append("setsar=1")
    parts.append("format=yuv420p")
    return label + ",".join(parts)


def _audio_chains(audio, duration, config, audio_input_index, inputs):
    """Register audio inputs and return (chains, audio_map).

    Chain: voice cleanup -> sidechain ducking on the soundtrack ->
    amix -> loudnorm to the configured LUFS target.
    """
    if audio is None or (audio.soundtrack is None and audio.voiceover is None):
        return [], None

    st_label = None
    vo_label = None
    if audio.soundtrack is not None:
        inputs.append(["-i", audio.soundtrack])
        st_label = f"[{audio_input_index}:a]"
        audio_input_index += 1
    if audio.voiceover is not None:
        inputs.append(["-i", audio.voiceover])
        vo_label = f"[{audio_input_index}:a]"

    offset = config.get("audio_offset", 0.0)
    trim = f"atrim=start={_fmt(offset)}:end={_fmt(offset + duration)}"
    loudnorm = ("loudnorm=I={}:TP=-1.5:LRA=11,aresample=48000"
                .format(_fmt(config.get("lufs_target", -14))))

    if st_label and vo_label:
        threshold = config.get("duck_threshold", 0.02)
        ratio = config.get("duck_ratio", 2)
        chains = [f"{st_label}{trim},asetpts=PTS-STARTPTS[st_t]"]
        if config.get("voice_cleanup", True):
            vo_clean = ("afftdn=nf=-40:nt=w,agate=threshold=0.02:attack=20:release=250,"
                        f"{trim},asetpts=PTS-STARTPTS[vo0]")
        else:
            vo_clean = f"{trim},asetpts=PTS-STARTPTS[vo0]"
        chains.append(f"{vo_label}{vo_clean}")
        chains.append("[vo0]asplit=2[vo_sc][vo_mix]")
        chains.append(
            f"[st_t][vo_sc]sidechaincompress=threshold={_fmt(threshold)}"
            f":ratio={_fmt(ratio)}:attack=20:release=500:makeup=1[st_ducked]")
        chains.append("[st_ducked][vo_mix]amix=inputs=2:normalize=0:duration=first[aout_raw]")
        chains.append(f"[aout_raw]{loudnorm}[aout]")
        return chains, "[aout]"

    label = st_label or vo_label
    return [f"{label}{trim},asetpts=PTS-STARTPTS[aout_raw]",
            f"[aout_raw]{loudnorm}[aout]"], "[aout]"


XFADE_MODES = {
    "cross_dissolve": "fade",
    "dip_to_black": "fadeblack",
    "dip_to_white": "fadewhite",
    "luma_wipe": "luma",
}


def _xfade_mode(mode):
    if mode not in XFADE_MODES:
        raise ValueError(f"unknown transition_mode: {mode}")
    return XFADE_MODES[mode]


def _transition_chains(segments, mode, duration_s, width, height, fps):
    """Chained xfade nodes replacing concat. Returns (chains, output_label)."""
    for seg in segments:
        if seg["end"] - seg["start"] <= duration_s:
            raise ValueError(
                f"transition_duration {duration_s}s exceeds a segment duration")

    if mode == "luma_wipe":
        count = len(segments) - 1
        labels = "".join(f"[m{k}]" for k in range(count))
        chains = [
            f"nullsrc=s={width}x{height}:r={fps}:d={_fmt(segments[-1]['end'])},"
            f"geq=r='X*255/{width}':g='X*255/{width}':b='X*255/{width}'[m0]",
            f"[m0]split={count}{labels}",
        ]
        first = "[seg0]"
        for k in range(1, len(segments)):
            offset = segments[k]["start"] - k * duration_s
            out = "[vcat]" if k == len(segments) - 1 else f"[vx{k}]"
            chains.append(
                f"{first}[seg{k}][m{k-1}]xfade=transition=luma"
                f":duration={_fmt(duration_s)}:offset={_fmt(offset)}{out}")
            first = out
        return chains, "[vcat]"

    chains = []
    first = "[seg0]"
    for k in range(1, len(segments)):
        offset = segments[k]["start"] - k * duration_s
        out = "[vcat]" if k == len(segments) - 1 else f"[vx{k}]"
        chains.append(
            f"{first}[seg{k}]xfade=transition={_xfade_mode(mode)}"
            f":duration={_fmt(duration_s)}:offset={_fmt(offset)}{out}")
        first = out
    return chains, "[vcat]"


def compile_graph(config, segments, audio=None, project_dir=".", profile=None,
                   ass_path=None):
    """Compile config + segments (+ audio) into one ffmpeg invocation.

    Asset paths in segments are resolved against project_dir. AudioSpec
    paths are used as given (main.py resolves them against project_dir).
    A HardwareProfile with a non-empty hw_chain appends upload nodes
    before the encoder; None or CPU_PROFILE emits the plain CPU graph.
    ass_path, when set, burns the generated .ass via the subtitles filter.
    """
    assert isinstance(segments, list) and segments, "cutlist must be a non-empty array"
    width, height = config["resolution"]
    fps = config["fps"]
    duration = segments[-1]["end"]

    inputs = []
    asset_index = {}
    segment_refs = {}

    for seg in segments:
        asset = seg.get("asset")
        if asset is None:
            continue
        full_asset = os.path.join(project_dir, asset)
        if full_asset in asset_index:
            segment_refs[asset_index[full_asset]] += 1
            continue
        index = len(inputs)
        ext = os.path.splitext(asset)[1].lower()
        if ext in IMAGE_EXTS:
            inputs.append(["-loop", "1", "-framerate", str(fps), "-i", full_asset])
        else:
            inputs.append(["-i", full_asset])
        asset_index[full_asset] = index
        segment_refs[index] = 1

    chains = []
    split_labels = {}
    for index, count in segment_refs.items():
        if count > 1:
            labels = "".join(f"[v{index}_{k}]" for k in range(count))
            chains.append(f"[{index}:v]split={count}{labels}")
            split_labels[index] = [f"[v{index}_{k}]" for k in range(count)]
        else:
            split_labels[index] = [f"[{index}:v]"]

    ref_counter = {}
    easing = config.get("ken_burns_easing", "linear")
    for i, seg in enumerate(segments):
        asset = seg.get("asset")
        if asset is None or seg.get("filter") == "white_flash":
            chain = _segment_chain(None, seg, width, height, fps, easing)
        else:
            # theme defaults apply to asset segments lacking explicit values
            if seg.get("filter") is None and config.get("default_filter"):
                seg = dict(seg, filter=config["default_filter"])
            if seg.get("effect") is None and config.get("default_effect"):
                seg = dict(seg, effect=config["default_effect"])
            index = asset_index[os.path.join(project_dir, seg["asset"])]
            label = split_labels[index][ref_counter.get(index, 0)]
            ref_counter[index] = ref_counter.get(index, 0) + 1
            chain = _segment_chain(label, seg, width, height, fps, easing)
        chains.append(f"{chain}[seg{i}]")

    transition_mode = config.get("transition_mode", "hard_cut")
    if transition_mode != "hard_cut" and len(segments) > 1:
        transition_d = config.get("transition_duration", 0.5)
        duration = segments[-1]["end"] - (len(segments) - 1) * transition_d
        t_chains, _ = _transition_chains(
            segments, transition_mode, transition_d, width, height, fps)
        chains.extend(t_chains)
    else:
        seg_labels = "".join(f"[seg{i}]" for i in range(len(segments)))
        chains.append(f"{seg_labels}concat=n={len(segments)}:v=1:a=0[vcat]")
    chains.append(f"[vcat]fps={fps},trim=duration={_fmt(duration)},setpts=PTS-STARTPTS[vfps]")
    current = "[vfps]"
    lut = config.get("lut")
    if lut:
        lut_path = os.path.join(project_dir, lut)
        chains.append(f"[vfps]lut3d=file={lut_path}:interp=tetrahedral[vlut]")
        current = "[vlut]"

    if ass_path:
        chains.append(f"{current}subtitles=filename={ass_path}[vsub]")
        current = "[vsub]"

    if profile is not None and profile.hw_chain:
        chains.append(f"{current}{profile.hw_chain}[vout]")
        current = "[vout]"

    audio_chains, audio_map = _audio_chains(
        audio, duration, config, len(inputs), inputs)
    chains.extend(audio_chains)

    return CompiledGraph(inputs, ";".join(chains), current, audio_map, duration)
