"""Render integration tests (Spec B, CP-2).

Requires the fixture project (tests/fixtures/generate_fixture.sh) and
ffmpeg. Runs inside the container.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = "tests/fixtures/synthetic_project"
OUTPUT = REPO_ROOT / FIXTURE / "output" / "render.mp4"


def _render():
    return subprocess.run(
        [sys.executable, "main.py", "--project", FIXTURE],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300,
    )


def _probe(show_entries):
    return subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", show_entries,
         "-of", "json", str(OUTPUT)],
        capture_output=True, text=True, check=True,
    )


class ImportHygieneTests(unittest.TestCase):
    def test_no_heavy_imports_at_top_level(self):
        import main  # noqa: F401
        heavy = [m for m in ("moviepy", "PIL", "numpy") if m in sys.modules]
        self.assertEqual(heavy, [])


class RenderContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = _render()

    def test_render_succeeds_single_ffmpeg_pass(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr[-2000:])
        self.assertIn("-filter_complex", self.result.stdout)
        self.assertIn("ffmpeg", self.result.stdout)

    def test_output_exists(self):
        self.assertTrue(OUTPUT.exists())
        self.assertGreater(OUTPUT.stat().st_size, 0)

    def test_output_contract(self):
        probe = _probe("stream=codec_type,codec_name,width,height,r_frame_rate")
        data = json.loads(probe.stdout)
        video = next(s for s in data["streams"] if s["codec_type"] == "video")
        audio = next(s for s in data["streams"] if s["codec_type"] == "audio")
        self.assertEqual((video["width"], video["height"]), (360, 640))
        self.assertEqual(video["codec_name"], "h264")
        self.assertEqual(video["r_frame_rate"], "15/1")
        self.assertEqual(audio["codec_name"], "aac")

    def test_duration_matches_cutlist_span(self):
        probe = _probe("format=duration")
        duration = float(json.loads(probe.stdout)["format"]["duration"])
        self.assertAlmostEqual(duration, 4.0, delta=0.1)


class DeterminismTests(unittest.TestCase):
    def test_rerender_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a.mp4"
            second = Path(tmp) / "b.mp4"
            for out in (first, second):
                result = _render()
                self.assertEqual(result.returncode, 0, result.stderr[-2000:])
                shutil.copy2(OUTPUT, out)
            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
