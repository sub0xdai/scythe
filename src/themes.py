"""Theme profile loading.

A theme is a JSON object of flat config keys (the same keys the engine
reads everywhere). load_theme validates keys strictly and returns the
overrides; main.load_config merges them between DEFAULTS and the
project config, so explicit project settings beat theme defaults.

The engine defaults are neutral. Every opinion - typeface, stroke, filter,
transition, pacing - lives in a theme file.
"""

import json
import os

PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

THEME_KEYS = {
    "resolution", "fps", "font", "font_size", "stroke_width", "stroke_color",
    "text_color", "audio_offset",
    "lufs_target", "voice_cleanup", "duck_threshold", "duck_ratio",
    "text_box_width", "safe_zone_top", "safe_zone_bottom",
    "lut", "transition_mode", "transition_duration", "ken_burns_easing",
    "default_filter", "default_effect", "outputs",
    "eval_freeze_min", "eval_black_min", "eval_silence_min",
    "eval_lufs_tolerance", "eval_true_peak_max",
}


class ThemeError(Exception):
    """Raised for unknown fields or unresolvable theme references."""


def load_theme(theme_ref, base_dir=None):
    """Load a theme by name (themes/<name>.json) or by path."""
    name = theme_ref[:-5] if theme_ref.endswith(".json") else theme_ref
    candidates = [theme_ref, os.path.join(PACKAGE_ROOT, "themes", name + ".json")]
    if base_dir:
        candidates.insert(1, os.path.join(base_dir, theme_ref))
        candidates.insert(2, os.path.join(base_dir, "themes", name + ".json"))
    path = next((c for c in candidates if os.path.exists(c)), None)
    if path is None:
        raise ThemeError(f"theme not found: {theme_ref}")

    with open(path) as f:
        data = json.load(f)
    assert isinstance(data, dict), f"theme must be a JSON object: {path}"
    unknown = sorted(set(data) - THEME_KEYS)
    if unknown:
        raise ThemeError(f"unknown theme fields in {path}: {unknown}")
    return data
