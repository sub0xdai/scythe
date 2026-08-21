"""
Kinetic Video Rendering Engine — project-aware entry point.

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
  └── output/          # Rendered .mp4
"""

import argparse
import json
import os
import subprocess
import sys

from src.compiler import AudioSpec, compile_graph
from src.compiler.text import build_ass
from src.gpu import (
    CPU_PROFILE,
    dry_run,
    parse_encoders,
    probe,
    profile_for,
)
from src.themes import ThemeError, load_theme
from src.validator import validate


# ── Defaults ──────────────────────────────────────────────────────────────

DEFAULTS = {
    "resolution": [1080, 1920],   # width, height (9:16 vertical)
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
            print(f"ERROR: {e}")
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

AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".m4a"}


def _detect_audio(project_dir):
    """Resolve soundtrack/voiceover from audio/ per the naming convention."""
    audio_dir = os.path.join(project_dir, "audio")
    if not os.path.isdir(audio_dir):
        print("  WARNING: no audio/ directory, output will be silent")
        return None

    files = sorted(os.listdir(audio_dir))
    audio_files = [f for f in files if os.path.splitext(f)[1].lower() in AUDIO_EXTS]

    if not audio_files:
        print(f"  WARNING: no audio files in {audio_dir}, output will be silent")
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
        print(f"  Soundtrack: {soundtrack_files[0] if soundtrack_files else '(none)'}")
        print(f"  Voiceover:  {vo_file}")
        return AudioSpec(
            soundtrack=os.path.join(audio_dir, soundtrack_files[0])
            if soundtrack_files else None,
            voiceover=os.path.join(audio_dir, vo_file),
        )

    print(f"  Soundtrack: {soundtrack_files[0]}")
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
        print(f"ERROR: {error}")
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
        print(f"ERROR: No cutlist found at {cutlist_path}")
        print("Feed prompts/brutalist-video-prompt.md to an LLM to generate one.")
        sys.exit(1)

    with open(cutlist_path) as f:
        segments = json.load(f)

    violations = validate(segments, project_dir, config)
    if violations:
        print("Cutlist validation failed:")
        for v in violations:
            idx = f"segment {v.segment_index}: " if v.segment_index is not None else ""
            print(f"  - [{v.rule}] {idx}{v.message}")
        print(f"  ({len(violations)} violation(s))")
        sys.exit(1)

    output_dir = os.path.join(project_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "render.mp4")

    print(f"Project:  {project_dir}")
    print(f"Config:   {target_size[0]}×{target_size[1]} @ {config['fps']}fps | {config['font']} {config['font_size']}px")
    print(f"Output:   {output_path}")
    print(f"Segments: {len(segments)}")
    print("─" * 50)

    print("Detecting audio...")
    audio = _detect_audio(project_dir)
    if audio is None:
        print("  → No audio, output will be silent")
    if config["audio_offset"]:
        print(f"  Offset:   {config['audio_offset']:.1f}s")

    duration = segments[-1]["end"]
    print("Compiling filtergraph...")
    print("Probing hardware...")
    profile = _select_profile()
    print(f"  Encoder: {profile.encoder}")
    ass_path = None
    ass_content = build_ass(segments, config)
    if ass_content:
        ass_path = os.path.join(output_dir, "subtitles.ass")
        with open(ass_path, "w") as f:
            f.write(ass_content)
        print(f"  Subtitles: {ass_path}")
    graph = compile_graph(config, segments, audio, project_dir, profile, ass_path)

    cmd = ["ffmpeg", "-y", *profile.extra_args]
    for arg_list in graph.input_args:
        cmd.extend(arg_list)
    cmd += ["-filter_complex", graph.filter_complex,
            "-map", graph.video_map]
    if graph.audio_map:
        cmd += ["-map", graph.audio_map]
    cmd += ["-c:v", profile.encoder, "-preset", "medium", "-crf", "23",
            "-threads", "4", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if graph.audio_map:
        cmd += ["-c:a", "aac"]
    cmd.append(output_path)

    print(f"Rendering {output_path} ({duration:.1f}s)...")
    print("Running: " + " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFmpeg failed:")
        print(result.stderr[-4000:])
        sys.exit(result.returncode)
    print(f"Done → {output_path}")


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
    parser = argparse.ArgumentParser(description="Kinetic Video Rendering Engine")
    parser.add_argument("--project", "-p", help="Path to project directory (cut-list mode)")
    parser.add_argument("--check-gpu", action="store_true", help="Print GPU capability report and exit")

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
