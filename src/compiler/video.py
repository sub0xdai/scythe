"""Per-filter and per-effect libavfilter chain builders (Spec B).

Each builder returns a comma-joined filter string, or an empty string
for identity. Deterministic: no randomness, no environment dependence.
"""

NOISE_SEED = 1234


def filter_chain(filter_name):
    """Map a cutlist filter name to a libavfilter node chain."""
    if filter_name is None:
        return ""
    if filter_name == "grayscale":
        return "hue=s=0"
    if filter_name == "color_invert":
        return "negate"
    if filter_name == "color_crush":
        return ("hue=s=0,lutrgb=r='if(gte(val,128),255,0)'"
                ":g='if(gte(val,128),255,0)':b='if(gte(val,128),255,0)'")
    if filter_name == "high_contrast_green":
        return ("hue=s=0,lutrgb=r='if(gte(val,128),0,0)'"
                ":g='if(gte(val,128),255,0)':b='if(gte(val,128),0,0)'")
    if filter_name == "high_contrast_red":
        return ("hue=s=0,lutrgb=r='if(gte(val,128),255,0)'"
                ":g='if(gte(val,128),0,0)':b='if(gte(val,128),0,0)'")
    if filter_name == "chromatic_aberration":
        return "rgbashift=rh=2:bh=-2"
    if filter_name == "film_grain":
        return f"noise=alls=4:allf=t:seed={NOISE_SEED}"
    if filter_name == "white_flash":
        return ""  # generated color segment, handled in graph.py
    raise ValueError(f"unknown filter: {filter_name}")


def zoompan_chain(effect_name, width, height, fps, frame_count, easing="linear"):
    """Return the zoompan node for a motion effect, or "" for identity."""
    if effect_name in (None, "strobe", "word_flash"):
        return ""
    t = f"in/{frame_count}"
    if easing in ("cubic", "bezier"):
        eased = f"({t}*{t}*(3-2*{t}))"  # smoothstep
    else:
        eased = t
    if effect_name == "ken_burns_slow":
        zoom = f"1+0.08*{eased}"
    elif effect_name == "ken_burns_fast":
        zoom = f"1+0.15*{eased}"
    elif effect_name == "snap_zoom":
        zoom = f"if(gt(in,{frame_count}/2),1.3,1)"
    else:
        raise ValueError(f"unknown effect: {effect_name}")
    return ("zoompan=z='%s':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            "d=1:fps=%d:s=%dx%d" % (zoom, fps, width, height))
