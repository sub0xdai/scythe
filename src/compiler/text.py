"""ASS subtitle generation (Spec D).

Pure builder: build_ass(segments, config) -> str | None. The caller
writes the file and the graph burns it via the subtitles filter.
"""

_FONT_WIDTH_FACTOR = 0.55
_KARAOKE_COLOR = "&H0000FF00"


def _ts(seconds):
    centis = int(round(seconds * 100))
    hours, rem = divmod(centis, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, centis = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _wrap(text, box_chars):
    lines = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > box_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\\N".join(lines)


def _karaoke(text, duration):
    words = text.split()
    if not words:
        return ""
    per_word = max(1, int(round(duration * 100 / len(words))))
    return " ".join(f"{{\\k{per_word}}}{word}" for word in words)


def _style_line(name, font, size, outline, margin_l, margin_r, margin_v):
    return (f"Style: {name},{font},{size},&H00FFFFFF,{_KARAOKE_COLOR},"
            f"&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{outline},0,2,"
            f"{margin_l},{margin_r},{margin_v},1")


def build_ass(segments, config):
    """Return the .ass script, or None when no text is present."""
    width, height = config["resolution"]
    box_width = config.get("text_box_width", 0.8)
    safe_top = config.get("safe_zone_top", 0.12)
    safe_bottom = config.get("safe_zone_bottom", 0.25)
    # ponytail: horizontal safe zones are internal constants; landscape
    # (16:9 desktop) is the default, vertical opt-in presets tighten them.
    if width > height:
        safe_top, safe_bottom = 0.08, 0.15

    margin_v = round(safe_bottom * height)
    margin_l = margin_r = round((1 - box_width) * width / 2)
    box_chars = max(1, int(width * box_width
                           / (config["font_size"] * _FONT_WIDTH_FACTOR)))

    events = []
    for seg in segments:
        lower = seg.get("lower_third")
        if lower:
            events.append(
                f"Dialogue: 0,{_ts(seg['start'])},{_ts(seg['end'])},"
                f"LowerThird,,0,0,0,,{{\\fad(150,150)}}"
                f"{lower['title']}\\N{lower['subtitle']}")
        elif seg.get("text"):
            if seg.get("effect") == "word_flash":
                text = _karaoke(seg["text"], seg["end"] - seg["start"])
                style = "Karaoke"
            else:
                text = _wrap(seg["text"], box_chars)
                style = "Default"
            events.append(
                f"Dialogue: 0,{_ts(seg['start'])},{_ts(seg['end'])},"
                f"{style},,0,0,0,,{text}")
    if not events:
        return None

    font = config["font"]
    size = config["font_size"]
    outline = config["stroke_width"]
    styles = "\n".join([
        _style_line("Default", font, size, outline, margin_l, margin_r, margin_v),
        _style_line("Karaoke", font, size, outline, margin_l, margin_r, margin_v),
        _style_line("LowerThird", font, size, outline, margin_l, margin_r, margin_v),
    ])
    header = (
        "[Script Info]\n"
        "Script Type: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{styles}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    return header + "\n".join(events) + "\n"
