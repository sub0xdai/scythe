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

import numpy as np
from PIL import Image

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
        # Fresh interpreter: suite-level imports from other test modules
        # must not mask what main.py itself pulls in.
        result = subprocess.run(
            [sys.executable, "-c",
             "import main, sys; "
             "heavy = [m for m in ('moviepy', 'PIL', 'numpy') if m in sys.modules]; "
             "assert heavy == [], heavy"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


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


class TextBurnE2ETests(unittest.TestCase):
    """Text must render through the .ass burn, not drawtext/TextClip (R1 S2)."""

    SEGMENTS = [
        {"start": 0.0, "end": 1.0, "phase": "hook",
         "text": "THE PROBLEM", "asset": None,
         "filter": "white_flash", "effect": None},
        {"start": 1.0, "end": 3.0, "phase": "kinetic_cut",
         "text": "THE FIX IS HERE", "asset": None,
         "filter": "grayscale", "effect": "word_flash"},
        {"start": 3.0, "end": 4.0, "phase": "kinetic_cut",
         "text": None, "asset": None, "filter": "white_flash",
         "effect": None,
         "lower_third": {"title": "DR. NOX",
                         "subtitle": "SYSTEMS ENGINEER"}},
    ]

    def _render_project(self, tmp):
        prompts = Path(tmp, "prompts")
        prompts.mkdir(parents=True)
        (prompts / "cutlist.json").write_text(json.dumps(self.SEGMENTS))
        (Path(tmp) / "config.json").write_text(json.dumps({
            "resolution": [360, 640], "fps": 15,
            "font": "LiberationSerif-Bold", "font_size": 28,
        }))
        result = subprocess.run(
            [sys.executable, "main.py", "--project", tmp],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        return Path(tmp, "output")

    @staticmethod
    def _dark_pixel_count(media, t):
        frame = subprocess.run(
            ["ffmpeg", "-y", "-ss", str(t), "-i", str(media),
             "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-"],
            capture_output=True, check=True,
        )
        img = np.array(Image.open(__import__("io").BytesIO(frame.stdout)))
        gray = np.dot(img[..., :3], [0.2989, 0.5870, 0.1140])
        return int((gray < 128).sum())

    def test_ass_generated_and_text_burned(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._render_project(tmp)
            ass = out / "subtitles.ass"
            self.assertTrue(ass.exists())
            content = ass.read_text()
            for style in ("Default", "Karaoke", "LowerThird"):
                self.assertIn(style, content)
            self.assertIn("\\k", content)
            self.assertIn("\\fad(150,150)", content)
            render = out / "render.mp4"
            dark = self._dark_pixel_count(render, 0.5)
            self.assertGreater(dark, 0, "no dark pixels at a text timestamp")

    def test_textless_render_stays_white(self):
        with tempfile.TemporaryDirectory() as tmp:
            segments = [{"start": 0.0, "end": 2.0, "phase": "hook",
                         "text": None, "asset": None,
                         "filter": "white_flash", "effect": None}]
            prompts = Path(tmp, "prompts")
            prompts.mkdir(parents=True)
            (prompts / "cutlist.json").write_text(json.dumps(segments))
            (Path(tmp) / "config.json").write_text(json.dumps({
                "resolution": [360, 640], "fps": 15,
                "font": "LiberationSerif-Bold", "font_size": 28,
            }))
            result = subprocess.run(
                [sys.executable, "main.py", "--project", tmp],
                cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            render = Path(tmp, "output", "render.mp4")
            dark = self._dark_pixel_count(render, 0.5)
            self.assertEqual(dark, 0, "textless white render has dark pixels")


if __name__ == "__main__":
    unittest.main()
