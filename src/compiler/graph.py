"""Compile config + cutlist into one ffmpeg invocation (Spec B).

Pure functions: no ffmpeg execution, no file writes. The renderer
(main.py) executes the returned CompiledGraph.
"""

import os
from dataclasses import dataclass

from src.compiler.video import filter_chain, zoompan_chain

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

FONT_FILES = {
    "LiberationSerif-Bold": "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "LiberationSerif": "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "LiberationSans-Bold": "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "LiberationSans": "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "LiberationMono-Bold": "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    "LiberationMono": "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
}


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


def _escape_text(text):
    out = []
    for ch in text:
        out.append("\\" + ch if ch in "\\':,;[]%" else ch)
    return "".join(out)


def _font_file(font_name):
    if font_name not in FONT_FILES:
        raise ValueError(f"unknown font: {font_name}")
    return FONT_FILES[font_name]


def _fmt(value):
    return f"{value:g}"


def _segment_chain(label, seg, width, height, fps):
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
    zoompan = zoompan_chain(effect_name, width, height, fps, frame_count)
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


def compile_graph(config, segments, audio=None, project_dir=".", profile=None):
    """Compile config + segments (+ audio) into one ffmpeg invocation.

    Asset paths in segments are resolved against project_dir. AudioSpec
    paths are used as given (main.py resolves them against project_dir).
    A HardwareProfile with a non-empty hw_chain appends upload nodes
    before the encoder; None or CPU_PROFILE emits the plain CPU graph.
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
    for i, seg in enumerate(segments):
        asset = seg.get("asset")
        if asset is None or seg.get("filter") == "white_flash":
            chain = _segment_chain(None, seg, width, height, fps)
        else:
            index = asset_index[os.path.join(project_dir, seg["asset"])]
            label = split_labels[index][ref_counter.get(index, 0)]
            ref_counter[index] = ref_counter.get(index, 0) + 1
            chain = _segment_chain(label, seg, width, height, fps)
        chains.append(f"{chain}[seg{i}]")

    seg_labels = "".join(f"[seg{i}]" for i in range(len(segments)))
    chains.append(f"{seg_labels}concat=n={len(segments)}:v=1:a=0[vcat]")
    chains.append(f"[vcat]fps={fps},trim=duration={_fmt(duration)},setpts=PTS-STARTPTS[vfps]")

    current = "[vfps]"
    text_seq = 0
    for seg in segments:
        text = seg.get("text")
        if not text:
            continue
        params = [
            f"text={_escape_text(text)}",
            f"fontfile={_font_file(config['font'])}",
            f"fontsize={config['font_size']}",
            f"fontcolor={config['text_color']}",
            f"borderw={config['stroke_width']}",
            f"bordercolor={config['stroke_color']}",
            "x=(w-text_w)/2",
            "y=(h-text_h)/2",
            f"enable='between(t,{_fmt(seg['start'])},{_fmt(seg['end'])})'",
        ]
        label = f"[vt{text_seq}]"
        text_seq += 1
        chains.append(f"{current}drawtext={':'.join(params)}{label}")
        current = label

    if profile is not None and profile.hw_chain:
        chains.append(f"{current}{profile.hw_chain}[vout]")
        current = "[vout]"

    audio_chains, audio_map = _audio_chains(
        audio, duration, config, len(inputs), inputs)
    chains.extend(audio_chains)

    return CompiledGraph(inputs, ";".join(chains), current, audio_map, duration)
