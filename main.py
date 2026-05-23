"""
Kinetic Video Rendering Engine — project-aware entry point.

Drop videos + images + audio into a project, define a cut-list, get an MP4.

Two modes:
  1. Cut-list mode:  python main.py --project projects/my-video
     Reads config.json (style) + prompts/cutlist.json (timeline).
     Applies filters, effects, text overlays.
     Mixes soundtrack + voiceover from audio/.
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
import sys

import numpy as np
from PIL import Image
from moviepy import (
    VideoFileClip,
    AudioFileClip,
    ImageClip,
    CompositeVideoClip,
    CompositeAudioClip,
    concatenate_videoclips,
    TextClip,
    ColorClip,
    vfx,
    afx,
)


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
    """Merge defaults ← config.json ← CLI overrides. Returns resolved config dict."""
    config = dict(DEFAULTS)

    # Load project config.json if present
    config_path = os.path.join(project_dir, "config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            project_config = json.load(f)

        # Apply preset if specified
        preset_name = project_config.pop("preset", None)
        if preset_name and preset_name in PRESETS:
            config.update(PRESETS[preset_name])

        config.update(project_config)

    # CLI overrides take highest priority
    if cli_overrides:
        config.update({k: v for k, v in cli_overrides.items() if v is not None})

    return config


# ── Helpers ───────────────────────────────────────────────────────────────

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".m4a"}


def _load_asset(path, duration, target_size):
    """Load a clip from path. Handles video, image, and missing files.
    Videos are center-cropped to target_size (not stretched).
    """
    if not os.path.exists(path):
        print(f"    WARNING: asset not found: {path}, using black frame")
        return ColorClip(size=target_size, color=(0, 0, 0), duration=duration)

    ext = os.path.splitext(path)[1].lower()

    if ext in IMAGE_EXTS:
        pil_img = Image.open(path).convert("RGB")
        # Center-crop to target ratio
        img_w, img_h = pil_img.size
        target_w, target_h = target_size
        target_ratio = target_w / target_h
        img_ratio = img_w / img_h
        if img_ratio > target_ratio:
            new_w = int(img_h * target_ratio)
            left = (img_w - new_w) // 2
            pil_img = pil_img.crop((left, 0, left + new_w, img_h))
        else:
            new_h = int(img_w / target_ratio)
            top = (img_h - new_h) // 2
            pil_img = pil_img.crop((0, top, img_w, top + new_h))
        pil_img = pil_img.resize(target_size, Image.LANCZOS)
        img = np.array(pil_img)
        return ImageClip(img, duration=duration)

    if ext in VIDEO_EXTS:
        clip = VideoFileClip(path)
        # Center-crop to target ratio
        clip = clip.resized(height=target_size[1])
        if clip.w > target_size[0]:
            clip = clip.cropped(x_center=clip.w / 2, width=target_size[0])
        else:
            clip = clip.resized(width=target_size[0])
        return clip.subclipped(0, min(duration, clip.duration))

    print(f"    WARNING: unknown format '{ext}' for {path}, using black frame")
    return ColorClip(size=target_size, color=(0, 0, 0), duration=duration)


# ── Filter/Effect Registry ────────────────────────────────────────────────

def apply_filter(clip, filter_name):
    """Apply a named visual filter to a clip. Returns modified clip."""
    if filter_name == "grayscale":
        return clip.with_effects([vfx.BlackAndWhite()])
    elif filter_name == "color_invert":
        return clip.with_effects([vfx.InvertColors()])
    elif filter_name == "high_contrast_green":
        return clip.image_transform(lambda frame: _contrast_crush(frame, accent=(0, 255, 0)))
    elif filter_name == "high_contrast_red":
        return clip.image_transform(lambda frame: _contrast_crush(frame, accent=(255, 0, 0)))
    elif filter_name == "white_flash":
        return ColorClip(size=clip.size, color=(255, 255, 255), duration=clip.duration)
    elif filter_name == "chromatic_aberration":
        return clip.image_transform(_chromatic_aberration)
    elif filter_name == "film_grain":
        return clip.image_transform(_film_grain)
    elif filter_name == "color_crush":
        return clip.image_transform(lambda frame: _contrast_crush(frame))
    return clip


def _contrast_crush(frame, accent=None):
    """Destroy midtones: push darks to black, brights to white."""
    gray = np.dot(frame[..., :3], [0.2989, 0.5870, 0.1140])
    mask = gray > 128
    crushed = np.zeros_like(frame)
    if accent:
        crushed[mask] = accent
    else:
        crushed[mask] = [255, 255, 255]
    return crushed


def _chromatic_aberration(frame):
    """Offset R and B channels horizontally for aberration effect."""
    shifted = frame.copy()
    shifted[:, :-2, 0] = frame[:, 2:, 0]
    shifted[:, 2:, 2] = frame[:, :-2, 2]
    return shifted


def _film_grain(frame):
    """Overlay 4% monochrome noise."""
    noise = np.random.randint(0, 11, frame.shape, dtype="uint8")
    return np.clip(frame.astype("int16") + noise - 5, 0, 255).astype("uint8")


def apply_effect(clip, effect_name):
    """Apply a named motion effect. Returns modified clip."""
    if effect_name in ("ken_burns_slow", "ken_burns_fast"):
        zoom_ratio = 1.08 if "slow" in effect_name else 1.15
        return clip.resized(lambda t: 1 + (zoom_ratio - 1) * t / clip.duration)
    elif effect_name == "snap_zoom":
        mid = clip.duration / 2
        def snap_resize(t):
            return 1.0 if t < mid else 1.3
        return clip.resized(snap_resize)
    elif effect_name in ("strobe", "word_flash"):
        return clip
    return clip


# ── Audio Mixing ──────────────────────────────────────────────────────────

def _mix_audio(project_dir, video_duration, audio_offset=0.0):
    """
    Load soundtrack + voiceover from audio/, mix them.
    Soundtrack is ducked to 30% under voiceover.
    audio_offset: start N seconds into the audio track.
    """
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

    if audio_offset > 0:
        print(f"  Offset:   {audio_offset:.1f}s")

    if not vo_file and len(audio_files) == 1:
        return AudioFileClip(os.path.join(audio_dir, audio_files[0])).subclipped(audio_offset, audio_offset + video_duration)

    if not vo_file:
        print(f"  Soundtrack: {soundtrack_files[0]}")
        return AudioFileClip(os.path.join(audio_dir, soundtrack_files[0])).subclipped(audio_offset, audio_offset + video_duration)

    print(f"  Soundtrack: {soundtrack_files[0] if soundtrack_files else '(none)'}")
    print(f"  Voiceover:  {vo_file}")

    vo = AudioFileClip(os.path.join(audio_dir, vo_file)).subclipped(audio_offset, audio_offset + video_duration)

    if soundtrack_files:
        st = AudioFileClip(os.path.join(audio_dir, soundtrack_files[0])).subclipped(audio_offset, audio_offset + video_duration)
        st = st.with_effects([afx.MultiplyVolume(0.3)])
        return CompositeAudioClip([st, vo])
    else:
        return vo


# ── Cut-List Mode ─────────────────────────────────────────────────────────

def generate_from_cutlist(project_dir, audio_offset=None, resolution=None, fps=None,
                          font=None, font_size=None, stroke_width=None,
                          stroke_color=None, text_color=None):
    """Read cutlist.json and config.json, render the full video."""

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
    audio_offset_val = config["audio_offset"]

    # Load cutlist
    cutlist_path = os.path.join(project_dir, "prompts", "cutlist.json")
    if not os.path.exists(cutlist_path):
        print(f"ERROR: No cutlist found at {cutlist_path}")
        print("Feed prompts/brutalist-video-prompt.md to an LLM to generate one.")
        sys.exit(1)

    with open(cutlist_path) as f:
        segments = json.load(f)

    output_dir = os.path.join(project_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "render.mp4")

    print(f"Project:  {project_dir}")
    print(f"Config:   {target_size[0]}×{target_size[1]} @ {config['fps']}fps | {config['font']} {config['font_size']}px")
    print(f"Output:   {output_path}")
    print(f"Segments: {len(segments)}")
    print("─" * 50)

    clips = []
    for i, seg in enumerate(segments):
        start = seg["start"]
        end = seg["end"]
        duration = end - start
        phase = seg["phase"]
        asset_path = seg.get("asset")
        filter_name = seg.get("filter")
        effect_name = seg.get("effect")

        print(f"  [{start:6.2f}s → {end:6.2f}s] {phase:16s} | {filter_name or '-':20s} | {effect_name or '-'}")

        if asset_path:
            full_asset = os.path.join(project_dir, asset_path)
            clip = _load_asset(full_asset, duration, target_size)
            # Sub-clip from specific timestamp if specified
            clip_start = seg.get("clip_start", 0)
            if clip_start > 0 and hasattr(clip, 'subclipped'):
                clip_end_val = seg.get("clip_end", clip_start + duration)
                clip = clip.subclipped(clip_start, min(clip_end_val, clip.duration))
        else:
            clip = ColorClip(size=target_size, color=(0, 0, 0), duration=duration)

        if filter_name:
            clip = apply_filter(clip, filter_name)

        if effect_name:
            clip = apply_effect(clip, effect_name)

        # Force consistent dimensions after all transforms
        clip = clip.resized(target_size)

        # Text overlay
        text = seg.get("text")
        if text:
            # Pad with newlines to prevent Pillow bounding-box stroke clipping
            txt = TextClip(
                text=f"\n{text}\n",
                font_size=config["font_size"],
                font=config["font"],
                color=config["text_color"],
                stroke_color=config["stroke_color"],
                stroke_width=config["stroke_width"],
                method="label",
            ).with_position("center").with_duration(duration)
            clip = CompositeVideoClip([clip, txt])

        clips.append(clip)

    print("─" * 50)
    print("Assembling timeline...")
    final = concatenate_videoclips(clips)

    print("Mixing audio...")
    audio = _mix_audio(project_dir, final.duration, audio_offset_val)
    if audio:
        final = final.with_audio(audio)
    else:
        print("  → No audio, output will be silent")

    print(f"Rendering {output_path} ({final.duration:.1f}s)...")
    final.write_videofile(
        output_path,
        fps=config["fps"],
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    )
    print(f"Done → {output_path}")


# ── Beat-Detect Mode (legacy) ─────────────────────────────────────────────

def generate_kinetic_sequence(audio_path, asset_dir, output_path):
    import librosa
    import glob

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

    if args.project:
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
