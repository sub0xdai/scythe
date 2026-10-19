"""Keyframe interpolation compiled to libavfilter expressions.

A keyframe list is ``[{at: 0..1, scale?, x?, y?}]``. ``at`` is a fraction
of the segment, so a cutlist survives a change of duration or framerate.
Values between keyframes interpolate with ffmpeg's lerp; values outside
hold the nearest keyframe. x/y are pixel offsets from center.
"""


def _fmt(value):
    return f"{float(value):g}"


def _sorted_points(keyframes, name, default):
    points = [(float(kf["at"]), float(kf[name]))
              for kf in keyframes
              if kf.get(name) is not None]
    if not points:
        return [(0.0, default), (1.0, default)]
    return points


def _interp(t_var, points):
    """Nested if/lerp over normalized time: hold, lerp, hold."""
    if len({value for _, value in points}) == 1:
        return _fmt(points[0][1])
    expr = _fmt(points[-1][1])
    for i in range(len(points) - 2, -1, -1):
        at0, val0 = points[i]
        at1, val1 = points[i + 1]
        span = at1 - at0
        if span <= 0:
            inner = _fmt(val1)
        else:
            inner = f"lerp({_fmt(val0)},{_fmt(val1)},({t_var}-{_fmt(at0)})/{_fmt(span)})"
        expr = f"if(lt({t_var},{_fmt(at1)}),{inner},{expr})"
    return expr


def keyframe_chain(keyframes, width, height, frame_count):
    """Return the scale+crop chain for a keyframe list, or "" when static."""
    if not keyframes:
        return ""
    t_var = f"(n/{max(1, frame_count)})"
    scale_expr = _interp(t_var, _sorted_points(keyframes, "scale", 1.0))
    dx = _interp(t_var, _sorted_points(keyframes, "x", 0.0))
    dy = _interp(t_var, _sorted_points(keyframes, "y", 0.0))
    if scale_expr == "1" and dx == "0" and dy == "0":
        return ""
    return (f"scale=w='{width}*{scale_expr}':h='{height}*{scale_expr}':eval=frame,"
            f"crop=w={width}:h={height}"
            f":x='(iw-{width})/2+{dx}':y='(ih-{height})/2+{dy}'")
