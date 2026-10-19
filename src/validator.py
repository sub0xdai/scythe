"""Pre-render validation gate.

Validates a cutlist document against schemas/cutlist.schema.json, then
applies the rules JSON Schema cannot express: track structure, timeline
continuity of the base track, resolvable filter/effect/transition names,
keyframe sanity, and asset pre-flight probing.

The gate reports correctness only. Pacing, casing, filter variety and
structure are the author's choices and are never rejected.
"""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import jsonschema

from src.compiler.graph import resolve_transition
from src.compiler.video import filter_chain, ken_burns_chain
from src.tracks import TimelineError, parse_document

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "schemas" / "cutlist.schema.json"
CONTINUITY_EPSILON_SEC = 1e-3


@dataclass(frozen=True)
class Violation:
    """One validation failure. rule is a stable machine-readable key."""
    rule: str
    message: str
    segment_index: int | None = None


def _load_schema():
    with open(SCHEMA_FILE) as f:
        schema = json.load(f)
    assert isinstance(schema, dict), "cutlist.schema.json must contain a schema object"
    return schema


def _schema_violations(document, schema):
    validator = jsonschema.Draft202012Validator(schema)
    violations = []
    for error in validator.iter_errors(document):
        segment_index = None
        for part in error.absolute_path:
            if isinstance(part, int):
                segment_index = part
                break
        violations.append(Violation("schema", error.message, segment_index))
    return violations


def _is_generated(seg):
    return seg.get("asset") is None or seg.get("filter") == "white_flash"


def _resolve_chain(name, kind):
    if name is None:
        return
    if kind == "filter":
        filter_chain(name)
    else:
        ken_burns_chain(name, 2, 2, 1, 1)


def _segment_violations(segments, track_label):
    violations = []
    for i, seg in enumerate(segments):
        where = f"{track_label} segment {i}"
        if seg["end"] <= seg["start"]:
            violations.append(Violation(
                "end_after_start",
                f"{where}: end {seg['end']} <= start {seg['start']}", i))
        for kind in ("filter", "effect"):
            try:
                _resolve_chain(seg.get(kind), kind)
            except ValueError as e:
                violations.append(Violation("unknown_name", f"{where}: {e}", i))
        ats = [kf.get("at") for kf in seg.get("keyframes") or []]
        if ats != sorted(ats):
            violations.append(Violation(
                "keyframes_order", f"{where}: keyframes must ascend on 'at'", i))
        transition = seg.get("transition")
        if transition and transition != "hard_cut":
            try:
                resolve_transition(transition)
            except ValueError:
                violations.append(Violation(
                    "unknown_transition", f"{where}: unknown transition "
                    f"'{transition}'", i))
    return violations


def _timeline_violations(timeline):
    violations = []
    base = timeline.base
    base_label = f"track '{base.id}'"
    violations.extend(_segment_violations(base.segments, base_label))
    if base.segments[0]["start"] > CONTINUITY_EPSILON_SEC:
        violations.append(Violation(
            "base_start", f"{base_label} must start at 0, "
            f"got {base.segments[0]['start']}", 0))
    for i in range(len(base.segments) - 1):
        gap = abs(base.segments[i]["end"] - base.segments[i + 1]["start"])
        if gap > CONTINUITY_EPSILON_SEC:
            violations.append(Violation(
                "continuity",
                f"segment {i} end {base.segments[i]['end']} does not meet "
                f"segment {i + 1} start {base.segments[i + 1]['start']}", i))

    for track in timeline.video[1:]:
        label = f"track '{track.id}'"
        violations.extend(_segment_violations(track.segments, label))
        for i, seg in enumerate(track.segments):
            if seg["end"] > timeline.duration + CONTINUITY_EPSILON_SEC:
                violations.append(Violation(
                    "track_overflow",
                    f"{label} segment {i}: ends at {seg['end']}s, past the "
                    f"timeline ({timeline.duration}s)", i))
            if seg["start"] < 0:
                violations.append(Violation(
                    "track_underflow", f"{label} segment {i}: starts before 0", i))
    return violations


def _probes_as_media(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-i", path],
        capture_output=True, timeout=30,
    )
    return result.returncode == 0


def _asset_violations(timeline, project_dir):
    violations = []

    def check(asset, i, label):
        full_path = os.path.join(project_dir, asset)
        if not os.path.exists(full_path):
            violations.append(Violation("asset_missing", f"{label} not found: {asset}", i))
        elif os.path.getsize(full_path) == 0:
            violations.append(Violation("asset_empty", f"{label} is zero bytes: {asset}", i))
        elif not _probes_as_media(full_path):
            violations.append(Violation(
                "asset_corrupt", f"{label} does not probe as media: {asset}", i))

    for track in timeline.video:
        for i, seg in enumerate(track.segments):
            if seg.get("asset") is not None:
                check(seg["asset"], i, "asset")
            for ov in seg.get("overlays", []):
                check(ov["asset"], i, "overlay asset")
    for track in timeline.audio:
        check(track.asset, None, f"audio track '{track.id}'")
    return violations


def validate(document, project_dir, config=None):
    """Return every Violation in the cutlist document, or [] when valid."""
    if not isinstance(document, (list, dict)):
        return [Violation("schema", "cutlist must be an array or an object with 'tracks'")]
    schema_violations = _schema_violations(document, _load_schema())
    if schema_violations:
        return schema_violations
    try:
        timeline = parse_document(document)
    except TimelineError as e:
        return [Violation("structure", str(e))]

    violations = _timeline_violations(timeline) + _asset_violations(timeline, project_dir)
    if config is not None:
        lut = config.get("lut")
        if lut and not os.path.exists(os.path.join(project_dir, lut)):
            violations.append(Violation("lut_missing", f"LUT file not found: {lut}"))
        mode = config.get("transition_mode", "hard_cut")
        if mode != "hard_cut":
            try:
                resolve_transition(mode)
            except ValueError:
                violations.append(Violation(
                    "unknown_transition", f"unknown transition_mode: {mode}"))
    return violations
