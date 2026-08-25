"""
Scythe - kinetic video rendering engine - project-aware entry point.

Drop videos + images + audio into a project, define a cut-list, get an MP4.

Two modes:
  1. Cut-list mode:  python main.py --project projects/my-video
     Reads config.json (style) + prompts/cutlist.json (timeline).
     Compiles one ffmpeg filtergraph and renders in a single pass.
  2. Beat-detect mode:  python main.py --audio audio/track.wav --assets video_assets/ --out output.mp4
     Legacy librosa beat-sync, no voiceover.

Project directory structure:
  project/
  ├── config.json      # Style: resolution, font, audio offset (optional)
  ├── audio/           # soundtrack.mp3 + voiceover.wav (auto-detected)
  ├── prompts/         # cutlist.json (generated via LLM prompt)
  ├── raw_footage/     # Video clips + images
  ├── overlays/        # Logos, textures, grids, grain
  └── output/          # master.mp4 + web.mp4 (+ subtitles.ass)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

from src.compiler import AudioSpec, compile_graph, snap_timeline
from src.compiler.text import build_ass
from src.gpu import (
    CPU_PROFILE,
    dry_run,
    parse_encoders,
    probe,
    profile_for,
    quality_for,
)
from src.telemetry import ProgressParser
from src.themes import ThemeError, load_theme
from src.validator import validate
from src.verify import VerificationError, verify

MACHINE = False  # JSON events are the only stdout content in machine mode

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def _materialize_stills(segments, project_dir, fps, out_dir):
    """One finite clip per image reference; rewrite the asset path in place.

    Images are single frames; without -loop 1 they cannot carry a segment's
    duration, and -loop 1 in the render graph is the unbounded-queue source
    (issues.md #12/#17). Materialize each image reference to a finite clip of
    exactly the snapped segment span, then let the compiler open it as plain
    video. Returns the created clip paths for cleanup.
    """
    os.makedirs(out_dir, exist_ok=True)
    created = []
    counter = 0
    for seg in segments:
        duration = seg["end"] - seg["start"]
        refs = []
        if seg.get("asset") and os.path.splitext(seg["asset"])[1].lower() in IMAGE_EXTS:
            refs.append((seg, "asset"))
        for ov in seg.get("overlays", []):
            if os.path.splitext(ov["asset"])[1].lower() in IMAGE_EXTS:
                refs.append((ov, "asset"))
        for holder, key in refs:
            full = os.path.join(project_dir, holder[key])
            clip = os.path.join(out_dir, f"clip_{counter}.mp4")
            cmd = ["ffmpeg", "-y", "-loop", "1", "-framerate", str(fps),
                   "-i", full, "-t", f"{duration:g}", "-r", str(fps),
                   "-pix_fmt", "yuv420p", clip]
            subprocess.run(cmd, check=True, capture_output=True)
            holder[key] = os.path.relpath(clip, project_dir)
            created.append(clip)
            counter += 1
    return created


def log(msg):
    print(msg, file=sys.stderr if MACHINE else sys.stdout)


def _json_event(event):
    print(json.dumps(event))


def _fail(message, code=1):
    if MACHINE:
        _json_event({"type": "error", "message": message})
    else:
        print(message)
    sys.exit(code)


def _progress_sink(event):
    if MACHINE:
        _json_event(event)
    else:
        print(f"Progress: {event['percent']}% frame={event['frame']} "
              f"speed={event['speed']}x eta={event['eta_seconds']}s",
              file=sys.stderr)


def _tmp_path(out_path):
    """Temp sibling ending in .mp4 so ffmpeg can infer the output format."""
    return out_path[:-4] + ".tmp.mp4"


def _run_render(cmd, duration, output_paths, segments=None, fps=None):
    """Run ffmpeg with -progress pipe:1, streaming telemetry events.

    Outputs are written to <name>.tmp.mp4 and verified before the atomic
    rename: duration must match the cutlist span, frame count must be
    exact, and the picture must be live. A failed gate deletes the tmp
    output and aborts without renaming.
    """
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    parser = ProgressParser(duration, emit=_progress_sink)
    for line in proc.stdout:
        parser.feed_line(line)
    stderr = proc.stderr.read()
    proc.wait()
    if proc.returncode != 0:
        _fail(f"FFmpeg failed:\n{stderr[-4000:]}", code=proc.returncode)
    if segments is not None and fps is not None:
        for out_path in output_paths:
            tmp = _tmp_path(out_path)
            try:
                verify(tmp, segments, fps, span=duration)
            except VerificationError as e:
                if os.path.exists(tmp):
                    os.remove(tmp)
                _fail(f"Render failed verification: {e}")
    for out_path in output_paths:
        os.replace(_tmp_path(out_path), out_path)
    if MACHINE:
        _json_event({"type": "done"})
    log(f"Done → {', '.join(output_paths)}")


# ── Defaults ──────────────────────────────────────────────────────────────

DEFAULTS = {
    "resolution": [1920, 1080],   # width, height (16:9 desktop default)
    "fps": 30,
    "font": "LiberationSerif-Bold",
    "font_size": 72,
    "stroke_width": 4,
    "stroke_color": "black",
    "text_color": "white",
    "audio_offset": 0.0,
    "lufs_target": -14,
    "voice_cleanup": True,
    "duck_threshold": 0.02,
    "duck_ratio": 2,
    "text_box_width": 0.8,
    "safe_zone_top": 0.12,
    "safe_zone_bottom": 0.25,
    "theme": None,
    "lut": None,
    "default_filter": None,
    "default_effect": None,
    "transition_mode": "hard_cut",
    "transition_duration": 0.5,
    "ken_burns_easing": "linear",
    "max_segments_per_chunk": 20,
    "outputs": [
        {"name": "master", "crf": 18},
        {"name": "web", "max_height": 720, "crf": 23},
    ],
}

# Presets for common formats
PRESETS = {
    "vertical":    {"resolution": [1080, 1920]},
    "widescreen":  {"resolution": [1920, 1080]},
    "square":      {"resolution": [1080, 1080]},
    "story":       {"resolution": [1080, 1920], "font": "LiberationSans-Bold", "font_size": 52},
    "cinematic":   {"resolution": [1920, 1080], "font": "LiberationSerif-Bold", "font_size": 90},
}


def load_config(project_dir, cli_overrides=None):
    """Merge DEFAULTS <- theme <- config.json <- CLI overrides."""
    config = dict(DEFAULTS)

    config_path = os.path.join(project_dir, "config.json")
    project_config = {}
    if os.path.exists(config_path):
        with open(config_path) as f:
            project_config = json.load(f)

    # Theme layer: explicit project config beats theme defaults
    theme_ref = project_config.get("theme")
    if theme_ref:
        try:
            config.update(load_theme(theme_ref, base_dir=project_dir))
        except ThemeError as e:
            log(f"ERROR: {e}")
            sys.exit(1)

    # Apply preset if specified
    preset_name = project_config.pop("preset", None)
    if preset_name and preset_name in PRESETS:
        config.update(PRESETS[preset_name])

    config.update(project_config)

    # CLI overrides take highest priority
    if cli_overrides:
        config.update({k: v for k, v in cli_overrides.items() if v is not None})

    return config


# ── Audio ─────────────────────────────────────────────────────────────────

def _has_audio_stream(path):
    """True when ffprobe finds an audio stream (content, not extension)."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30,
    )
    return "audio" in result.stdout


def _detect_audio(project_dir):
    """Resolve soundtrack/voiceover from audio/ per the naming convention."""
    audio_dir = os.path.join(project_dir, "audio")
    if not os.path.isdir(audio_dir):
        log("  WARNING: no audio/ directory, output will be silent")
        return None

    files = sorted(os.listdir(audio_dir))
    audio_files = [f for f in files
                   if _has_audio_stream(os.path.join(audio_dir, f))]

    if not audio_files:
        log(f"  WARNING: no audio files in {audio_dir}, output will be silent")
        return None

    vo_file = None
    soundtrack_files = []
    for f in audio_files:
        low = f.lower()
        if "voice" in low or "vo." in low or low.startswith("vo_"):
            vo_file = f
        else:
            soundtrack_files.append(f)

    if vo_file:
        log(f"  Soundtrack: {soundtrack_files[0] if soundtrack_files else '(none)'}")
        log(f"  Voiceover:  {vo_file}")
        return AudioSpec(
            soundtrack=os.path.join(audio_dir, soundtrack_files[0])
            if soundtrack_files else None,
            voiceover=os.path.join(audio_dir, vo_file),
        )

    log(f"  Soundtrack: {soundtrack_files[0]}")
    return AudioSpec(soundtrack=os.path.join(audio_dir, soundtrack_files[0]))


def _resolve_profile():
    """Return (profile, error). Honors NOX_GPU and NOX_ENCODER."""
    gpu_off = os.environ.get("NOX_GPU", "").lower() == "off"
    forced = os.environ.get("NOX_ENCODER")
    if gpu_off and forced:
        return CPU_PROFILE, "NOX_GPU=off and NOX_ENCODER are mutually exclusive"
    if gpu_off:
        return CPU_PROFILE, None
    if forced:
        profile = profile_for(forced)
        if profile is None:
            return CPU_PROFILE, f"unknown encoder '{forced}' (NOX_ENCODER)"
        if not dry_run(forced, profile.extra_args):
            return profile, f"encoder '{forced}' is not invokable on this machine"
        return profile, None
    return probe(), None


def _select_profile():
    """Render-path profile resolution: abort on any error."""
    profile, error = _resolve_profile()
    if error:
        log(f"ERROR: {error}")
        sys.exit(1)
    return profile


def _ffmpeg_names(flag):
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", flag],
        capture_output=True, text=True, timeout=30,
    )
    return parse_encoders(result.stdout)


def check_gpu():
    """Print the GPU capability report and exit by invokability."""
    encoders = sorted(
        n for n in _ffmpeg_names("-encoders")
        if any(k in n for k in ("nvenc", "qsv", "vaapi", "videotoolbox", "v4l2"))
        or n == "libx264")
    decoders = sorted(
        n for n in _ffmpeg_names("-decoders")
        if any(k in n for k in ("cuvid", "qsv", "vaapi", "videotoolbox", "v4l2m2m")))
    hwaccels_result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-hwaccels"],
        capture_output=True, text=True, timeout=30,
    )
    hwaccels = [line.strip() for line in hwaccels_result.stdout.splitlines()
                if line.strip() and not line.startswith("Hardware")]

    profile, error = _resolve_profile()
    dry_run_ok = dry_run(profile.encoder, profile.extra_args) if error is None else False
    report = {
        "encoders": encoders,
        "decoders": decoders,
        "hwaccels": hwaccels,
        "chosen": {
            "encoder": profile.encoder,
            "dry_run_ok": dry_run_ok,
            "error": error,
        },
    }
    print(json.dumps(report, indent=2))
    sys.exit(0 if dry_run_ok else 1)


# ── Cut-List Mode ─────────────────────────────────────────────────────────

def generate_from_cutlist(project_dir, audio_offset=None, resolution=None, fps=None,
                          font=None, font_size=None, stroke_width=None,
                          stroke_color=None, text_color=None):
    """Read cutlist.json and config.json, render the full video in one ffmpeg pass."""
    project_dir = os.path.abspath(project_dir)

    # Load config
    config = load_config(project_dir, {
        "audio_offset": audio_offset,
        "resolution": resolution,
        "fps": fps,
        "font": font,
        "font_size": font_size,
        "stroke_width": stroke_width,
        "stroke_color": stroke_color,
        "text_color": text_color,
    })

    target_size = tuple(config["resolution"])

    # Load cutlist
    cutlist_path = os.path.join(project_dir, "prompts", "cutlist.json")
    if not os.path.exists(cutlist_path):
        log(f"ERROR: No cutlist found at {cutlist_path}")
        log("Feed prompts/brutalist-video-prompt.md to an LLM to generate one.")
        sys.exit(1)

    with open(cutlist_path) as f:
        segments = json.load(f)

    violations = validate(segments, project_dir, config)
    if violations:
        log("Cutlist validation failed:")
        for v in violations:
            idx = f"segment {v.segment_index}: " if v.segment_index is not None else ""
            log(f"  - [{v.rule}] {idx}{v.message}")
        log(f"  ({len(violations)} violation(s))")
        sys.exit(1)

    segments = snap_timeline(segments, config["fps"])

    output_dir = os.path.join(project_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    log(f"Project:  {project_dir}")
    log(f"Config:   {target_size[0]}×{target_size[1]} @ {config['fps']}fps | {config['font']} {config['font_size']}px")
    log(f"Outputs:  {', '.join(o['name'] + '.mp4' for o in config['outputs'])}")
    log(f"Segments: {len(segments)}")
    log("─" * 50)

    log("Detecting audio...")
    audio = _detect_audio(project_dir)
    if audio is None:
        log("  → No audio, output will be silent")
    if config["audio_offset"]:
        log(f"  Offset:   {config['audio_offset']:.1f}s")

    materialized = _materialize_stills(
        segments, project_dir, config["fps"],
        os.path.join(output_dir, ".materialized"))
    if materialized:
        log(f"  Materialized: {len(materialized)} still clip(s)")

    try:
        _render_project(project_dir, config, segments, audio, output_dir)
    finally:
        for clip in materialized:
            if os.path.exists(clip):
                os.remove(clip)
        mat_dir = os.path.join(output_dir, ".materialized")
        if os.path.isdir(mat_dir) and not os.listdir(mat_dir):
            os.rmdir(mat_dir)


def _chunk_segments(segments, max_per_chunk):
    """Split a snapped hard-cut timeline into chunks at segment boundaries.

    Boundaries are segment boundaries, which the frame-aligned timeline makes
    exact multiples of 1/fps, so concatenating chunk outputs cannot drift.
    """
    assert max_per_chunk > 0, "max_segments_per_chunk must be > 0"
    return [segments[i:i + max_per_chunk]
            for i in range(0, len(segments), max_per_chunk)]


def _render_chunk(project_dir, config, chunk, profile, chunk_dir, k):
    """Render one chunk's video per output (no audio). Returns output paths."""
    t0 = chunk[0]["start"]
    local = [dict(seg, start=seg["start"] - t0, end=seg["end"] - t0) for seg in chunk]
    graph = compile_graph(config, local, None, project_dir, profile, None)
    paths = {}
    for out in graph.outputs:
        paths[out.name] = os.path.join(chunk_dir, f"{out.name}_{k}.mp4")
    cmd = ["ffmpeg", "-y", *profile.extra_args]
    for arg_list in graph.input_args:
        cmd.extend(arg_list)
    cmd += ["-filter_complex", graph.filter_complex]
    for i, out in enumerate(graph.outputs):
        cmd += ["-map", out.label, "-c:v", profile.encoder,
                *quality_for(profile.encoder, out.crf), "-pix_fmt", "yuv420p",
                paths[out.name]]
    subprocess.run(cmd, check=True, capture_output=True, timeout=3600)
    return paths


def _render_audio(project_dir, config, audio, duration, profile, out_path):
    """Master the full audio mix once (loudnorm, ducking) to out_path."""
    cover = [{"start": 0.0, "end": duration, "phase": "hook", "text": None,
              "asset": None, "filter": "white_flash", "effect": None}]
    graph = compile_graph(config, cover, audio, project_dir, profile, None)
    cmd = ["ffmpeg", "-y", *profile.extra_args]
    for arg_list in graph.input_args:
        cmd.extend(arg_list)
    cmd += ["-filter_complex", graph.filter_complex]
    cmd += ["-map", "[vfps]", "-f", "null", "-"]
    cmd += ["-map", graph.audio_maps[0], "-c:a", "aac", "-b:a", "192k", out_path]
    subprocess.run(cmd, check=True, capture_output=True, timeout=3600)


def _concat_chunks(chunk_paths, out_path):
    """Concat video chunks with the concat demuxer, stream copy, no re-encode."""
    list_path = out_path + ".concat.txt"
    with open(list_path, "w") as f:
        for path in chunk_paths:
            f.write(f"file '{path}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
           "-c", "copy", out_path]
    subprocess.run(cmd, check=True, capture_output=True, timeout=3600)
    os.remove(list_path)


def _render_chunked(project_dir, config, segments, audio, output_dir, profile):
    """Chunked render: per-chunk video passes, stream-copy concat, one audio pass."""
    chunks = _chunk_segments(segments, config["max_segments_per_chunk"])
    chunk_dir = os.path.join(output_dir, ".chunks")
    os.makedirs(chunk_dir, exist_ok=True)
    log(f"Chunked render: {len(chunks)} chunks of ≤{config['max_segments_per_chunk']} segments")
    duration = segments[-1]["end"]
    outputs_cfg = config.get("outputs") or [{"name": "render"}]
    names = [o["name"] for o in outputs_cfg]

    try:
        chunk_paths = {name: [] for name in names}
        for k, chunk in enumerate(chunks):
            paths = _render_chunk(project_dir, config, chunk, profile, chunk_dir, k)
            for name, path in paths.items():
                chunk_paths[name].append(path)

        audio_path = None
        if audio is not None:
            audio_path = os.path.join(chunk_dir, "audio.m4a")
            _render_audio(project_dir, config, audio, duration, profile, audio_path)

        output_paths = []
        for name in names:
            out_path = os.path.join(output_dir, f"{name}.mp4")
            output_paths.append(out_path)
            tmp = _tmp_path(out_path)
            _concat_chunks(chunk_paths[name], tmp)
            if audio_path:
                muxed = tmp + ".muxed.mp4"
                mux = ["ffmpeg", "-y", "-i", tmp, "-i", audio_path,
                       "-map", "0:v", "-map", "1:a", "-c", "copy",
                       "-movflags", "+faststart", muxed]
                subprocess.run(mux, check=True, capture_output=True, timeout=3600)
                os.remove(tmp)
                tmp = muxed
            # verify before rename (chunk boundaries are frame-exact by
            # construction; the gate confirms the concatenation did not drift)
            try:
                verify(tmp, segments, config["fps"])
            except VerificationError as e:
                if os.path.exists(tmp):
                    os.remove(tmp)
                _fail(f"Render failed verification: {e}")
            os.replace(tmp, out_path)
        log(f"Done → {', '.join(output_paths)}")
    finally:
        shutil.rmtree(chunk_dir, ignore_errors=True)


def _render_project(project_dir, config, segments, audio, output_dir):
    """Compile and execute the render for a (snapped, materialized) timeline."""
    duration = segments[-1]["end"]
    max_chunk = config.get("max_segments_per_chunk", 20)
    transition_mode = config.get("transition_mode", "hard_cut")
    if len(segments) > max_chunk and transition_mode == "hard_cut":
        profile = _select_profile()
        log(f"  Encoder: {profile.encoder}")
        _render_chunked(project_dir, config, segments, audio, output_dir, profile)
        return
    if len(segments) > max_chunk:
        log(f"  WARNING: {len(segments)} segments exceed max_segments_per_chunk "
            f"({max_chunk}) with transition_mode '{transition_mode}'; "
            "chunking requires hard_cut, rendering single-pass (memory unbounded)")
    log("Compiling filtergraph...")
    log("Probing hardware...")
    profile = _select_profile()
    log(f"  Encoder: {profile.encoder}")
    ass_path = None
    ass_content = build_ass(segments, config)
    if ass_content:
        ass_path = os.path.join(output_dir, "subtitles.ass")
        with open(ass_path, "w") as f:
            f.write(ass_content)
        log(f"  Subtitles: {ass_path}")
    graph = compile_graph(config, segments, audio, project_dir, profile, ass_path)
    duration = graph.duration  # post-transition span; the gate compares against this

    cmd = ["ffmpeg", "-y", *profile.extra_args]
    for arg_list in graph.input_args:
        cmd.extend(arg_list)
    cmd += ["-filter_complex", graph.filter_complex]
    output_paths = []
    for i, out in enumerate(graph.outputs):
        out_path = os.path.join(output_dir, f"{out.name}.mp4")
        output_paths.append(out_path)
        cmd += ["-map", out.label, "-c:v", profile.encoder,
                *quality_for(profile.encoder, out.crf), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart"]
        if graph.audio_maps:
            cmd += ["-map", graph.audio_maps[i], "-c:a", "aac"]
        if i == len(graph.outputs) - 1:
            cmd += ["-progress", "pipe:1"]
        cmd.append(_tmp_path(out_path))  # atomic rename to final name on success

    log(f"Rendering {duration:.1f}s → {', '.join(output_paths)}...")
    log("Running: " + " ".join(cmd))
    _run_render(cmd, duration, output_paths, segments, config["fps"])


# ── Beat-Detect Mode (legacy) ─────────────────────────────────────────────

def generate_kinetic_sequence(audio_path, asset_dir, output_path):
    import glob
    import librosa
    from moviepy import AudioFileClip, VideoFileClip, concatenate_videoclips

    y, sr = librosa.load(audio_path)
    _, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    durations = [beat_times[i + 1] - beat_times[i] for i in range(len(beat_times) - 1)]

    assets = sorted(glob.glob(os.path.join(asset_dir, "*.mp4")))
    if not assets:
        raise FileNotFoundError(f"No .mp4 files found in {asset_dir}")

    clips = []
    asset_idx = 0

    for duration in durations:
        target_asset = assets[asset_idx % len(assets)]
        src_clip = VideoFileClip(target_asset)
        cut_length = min(duration, src_clip.duration)
        clips.append(src_clip.subclipped(0, cut_length))
        asset_idx += 1

    final = concatenate_videoclips(clips)
    audio = AudioFileClip(audio_path).subclipped(beat_times[0], beat_times[len(durations)])
    final = final.with_audio(audio)
    final.write_videofile(output_path, fps=30, codec="libx264", audio_codec="aac",
                          ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"])


# ── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scythe - kinetic video rendering engine")
    parser.add_argument("--project", "-p", help="Path to project directory (cut-list mode)")
    parser.add_argument("--check-gpu", action="store_true", help="Print GPU capability report and exit")
    parser.add_argument("--json", action="store_true", help="Machine mode: newline-delimited JSON events on stdout")

    # Style overrides
    parser.add_argument("--resolution", type=str, help="WxH e.g. 1920x1080 (overrides config)")
    parser.add_argument("--fps", type=int, help="Output framerate")
    parser.add_argument("--font", help="Font name (e.g. LiberationSans-Bold)")
    parser.add_argument("--font-size", type=int, help="Text font size in px")
    parser.add_argument("--audio-offset", type=float, help="Start N seconds into audio")

    # Beat-detect mode
    parser.add_argument("--audio", "-a", help="Path to audio file (beat-detect mode)")
    parser.add_argument("--assets", help="Path to video_assets directory (beat-detect mode)")
    parser.add_argument("--out", "-o", help="Output path (beat-detect mode)")

    args = parser.parse_args()

    MACHINE = args.json or os.environ.get("NOX_JSON") == "1"

    if args.check_gpu:
        check_gpu()
    elif args.project:
        resolution = None
        if args.resolution:
            parts = args.resolution.split("x")
            resolution = [int(parts[0]), int(parts[1])]

        generate_from_cutlist(
            args.project,
            audio_offset=args.audio_offset,
            resolution=resolution,
            fps=args.fps,
            font=args.font,
            font_size=args.font_size,
        )
    elif args.audio and args.assets:
        out = args.out or "output_kinetic.mp4"
        generate_kinetic_sequence(args.audio, args.assets, out)
    else:
        parser.print_help()
        print("\nExamples:")
        print("  python main.py --project projects/my-video")
        print("  python main.py --project projects/my-video --resolution 1920x1080")
        print("  python main.py --project projects/my-video --font LiberationSans-Bold --font-size 52")
        print("  python main.py --audio audio/track.wav --assets video_assets/ --out output.mp4")
