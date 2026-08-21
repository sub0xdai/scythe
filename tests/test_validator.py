"""Unit and end-to-end tests for the pre-render validation gate (Spec A, CP-1).

Run inside the container where jsonschema, ffmpeg, and moviepy exist:
  podman run --rm --entrypoint python -v "$(pwd):/app:Z" kinetic-renderer -m unittest discover -s tests -v
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.validator import validate

REPO_ROOT = Path(__file__).resolve().parent.parent


def _valid_segments():
    """Three continuous segments with null assets so asset checks stay inert."""
    return [
        {"start": 0.0, "end": 1.0, "phase": "hook", "text": "THE HOOK",
         "asset": None, "filter": "grayscale", "effect": "ken_burns_slow"},
        {"start": 1.0, "end": 1.08, "phase": "drop_transition", "text": None,
         "asset": None, "filter": "white_flash", "effect": "strobe"},
        {"start": 1.08, "end": 2.08, "phase": "kinetic_cut", "text": "THE PAYOFF",
         "asset": None, "filter": "high_contrast_green", "effect": "snap_zoom"},
    ]


class TimelineRuleTests(unittest.TestCase):
    def test_valid_cutlist_passes(self):
        self.assertEqual(validate(_valid_segments(), "."), [])

    def test_end_before_start_flags_index(self):
        segments = _valid_segments()
        segments[1]["end"] = 0.5
        violations = validate(segments, ".")
        self.assertTrue(any(
            v.rule == "end_after_start" and v.segment_index == 1
            for v in violations))

    def test_gap_flags_timestamps(self):
        segments = _valid_segments()
        segments[1]["start"] = 1.2
        segments[1]["end"] = 1.28
        violations = validate(segments, ".")
        self.assertEqual(violations[0].rule, "continuity")
        self.assertIn("1.0", violations[0].message)
        self.assertIn("1.2", violations[0].message)

    def test_overlap_flags(self):
        segments = _valid_segments()
        segments[2]["start"] = 1.04
        violations = validate(segments, ".")
        self.assertEqual(violations[0].rule, "continuity")

    def test_epsilon_drift_passes(self):
        segments = _valid_segments()
        segments[1]["start"] = 1.0001
        self.assertEqual(validate(segments, "."), [])

    def test_adjacent_same_filter_flagged(self):
        segments = _valid_segments()
        segments[2].update(filter="white_flash", effect="strobe", text=None)
        violations = validate(segments, ".")
        self.assertTrue(any(v.rule == "filter_adjacency" for v in violations))

    def test_unknown_filter_flagged(self):
        segments = _valid_segments()
        segments[0]["filter"] = "sepia"
        violations = validate(segments, ".")
        self.assertEqual(violations[0].rule, "schema")


class AssetRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _segment(self, asset):
        return [{"start": 0.0, "end": 1.0, "phase": "hook",
                 "asset": asset, "filter": "grayscale"}]

    def test_missing_asset_flagged(self):
        violations = validate(self._segment("raw_footage/ghost.mp4"), self.tmp.name)
        self.assertEqual(violations[0].rule, "asset_missing")
        self.assertIn("ghost.mp4", violations[0].message)

    def test_zero_byte_flagged(self):
        empty = Path(self.tmp.name, "raw_footage", "empty.mp4")
        empty.parent.mkdir(parents=True)
        empty.touch()
        violations = validate(self._segment("raw_footage/empty.mp4"), self.tmp.name)
        self.assertEqual(violations[0].rule, "asset_empty")

    def test_corrupt_flagged(self):
        junk = Path(self.tmp.name, "raw_footage", "junk.mp4")
        junk.parent.mkdir(parents=True)
        junk.write_bytes(b"this is not media")
        violations = validate(self._segment("raw_footage/junk.mp4"), self.tmp.name)
        self.assertEqual(violations[0].rule, "asset_corrupt")

    def test_valid_asset_passes(self):
        clip = Path(self.tmp.name, "raw_footage", "clip.mp4")
        clip.parent.mkdir(parents=True)
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             "testsrc2=size=160x160:rate=10:duration=0.5",
             "-pix_fmt", "yuv420p", str(clip)],
            check=True, capture_output=True,
        )
        self.assertEqual(validate(self._segment("raw_footage/clip.mp4"), self.tmp.name), [])


class EndToEndTests(unittest.TestCase):
    """The render entry point must abort with violations before rendering."""

    def _project_with_cutlist(self, segments):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        prompts = Path(tmp.name, "prompts")
        prompts.mkdir(parents=True)
        (prompts / "cutlist.json").write_text(json.dumps(segments))
        return tmp.name

    def _run_render(self, project):
        return subprocess.run(
            [sys.executable, "main.py", "--project", project],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
        )

    def test_render_aborts_on_bad_timeline(self):
        project = self._project_with_cutlist([
            {"start": 0.0, "end": 1.0, "phase": "hook", "text": "THE HOOK",
             "asset": None, "filter": "grayscale", "effect": "ken_burns_slow"},
            {"start": 1.0, "end": 0.5, "phase": "hook", "text": "THE HOOK",
             "asset": None, "filter": "color_invert", "effect": None},
        ])
        result = self._run_render(project)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("validation failed", result.stdout.lower())

    def test_render_aborts_on_missing_asset(self):
        project = self._project_with_cutlist([
            {"start": 0.0, "end": 1.0, "phase": "hook", "text": "THE HOOK",
             "asset": "raw_footage/ghost.mp4", "filter": "grayscale",
             "effect": "ken_burns_slow"},
        ])
        result = self._run_render(project)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ghost.mp4", result.stdout)


if __name__ == "__main__":
    unittest.main()
