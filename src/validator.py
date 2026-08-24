"""Pre-render validation gate (Spec A).

Validates a cutlist against schemas/cutlist.schema.json plus the
cross-field rules JSON Schema cannot express: end > start, timeline
continuity, filter adjacency, and asset pre-flight probing.

The schema check runs first and gates the timeline and asset passes,
so those can assume structurally valid segments.
"""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import jsonschema

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


def _schema_violations(segments, schema):
    validator = jsonschema.Draft202012Validator(schema)
    violations = []
    for error in validator.iter_errors(segments):
        segment_index = None
        for part in error.absolute_path:
            if isinstance(part, int):
                segment_index = part
                break
        violations.append(Violation("schema", error.message, segment_index))
    return violations


def _timeline_violations(segments):
    violations = []
    for i, seg in enumerate(segments):
        if seg["end"] <= seg["start"]:
            violations.append(Violation(
                "end_after_start",
                f"segment {i}: end {seg['end']} <= start {seg['start']}", i))
    for i in range(len(segments) - 1):
        gap = abs(segments[i]["end"] - segments[i + 1]["start"])
        if gap > CONTINUITY_EPSILON_SEC:
            violations.append(Violation(
                "continuity",
                f"segment {i} end {segments[i]['end']} does not meet "
                f"segment {i + 1} start {segments[i + 1]['start']}", i))
        filter_a = segments[i].get("filter")
        filter_b = segments[i + 1].get("filter")
        if filter_a is not None and filter_a == filter_b:
            violations.append(Violation(
                "filter_adjacency",
                f"segments {i} and {i + 1} both use filter {filter_a}", i))
    return violations


def _probes_as_media(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-i", path],
        capture_output=True, timeout=30,
    )
    return result.returncode == 0


def _asset_violations(segments, project_dir):
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

    for i, seg in enumerate(segments):
        asset = seg.get("asset")
        if asset is not None:
            check(asset, i, "asset")
        for ov in seg.get("overlays", []):
            check(ov["asset"], i, "overlay asset")
    return violations


def validate(segments, project_dir, config=None):
    """Return every Violation in the cutlist, or an empty list when valid."""
    assert isinstance(segments, list), "cutlist must be a JSON array"
    schema_violations = _schema_violations(segments, _load_schema())
    if schema_violations:
        return schema_violations
    violations = _timeline_violations(segments) + _asset_violations(segments, project_dir)
    if config is not None:
        lut = config.get("lut")
        if lut and not os.path.exists(os.path.join(project_dir, lut)):
            violations.append(Violation(
                "lut_missing", f"LUT file not found: {lut}"))
    return violations
