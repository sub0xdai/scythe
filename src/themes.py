"""Theme profile loading (Spec C).

A theme is a JSON object of flat config keys (the same keys the engine
reads everywhere). load_theme validates keys strictly and returns the
overrides; main.load_config merges them between DEFAULTS and the
project config, so explicit project settings beat theme defaults.
"""

import json
import os

THEME_KEYS = {
    # core style
    "resolution", "fps", "font", "font_size", "stroke_width", "stroke_color",
    "text_color", "audio_offset",
    # audio mastering
    "lufs_target", "voice_cleanup", "duck_threshold", "duck_ratio",
    # typography
    "text_box_width", "safe_zone_top", "safe_zone_bottom",
    # theming-only
    "lut", "transition_mode", "transition_duration", "ken_burns_easing",
    "default_filter", "default_effect",
}


class ThemeError(Exception):
    """Raised for unknown fields or unresolvable theme references."""


def load_theme(theme_ref, base_dir=None):
    """Load a theme by name (themes/<name>.json) or by path."""
    if os.path.exists(theme_ref):
        path = theme_ref
    elif base_dir and os.path.exists(os.path.join(base_dir, theme_ref)):
        path = os.path.join(base_dir, theme_ref)
    else:
        name = theme_ref[:-5] if theme_ref.endswith(".json") else theme_ref
        path = os.path.join("themes", name + ".json")
        if not os.path.exists(path):
            raise ThemeError(f"theme not found: {theme_ref}")

    with open(path) as f:
        data = json.load(f)
    assert isinstance(data, dict), f"theme must be a JSON object: {path}"
    unknown = sorted(set(data) - THEME_KEYS)
    if unknown:
        raise ThemeError(f"unknown theme fields in {path}: {unknown}")
    return data
