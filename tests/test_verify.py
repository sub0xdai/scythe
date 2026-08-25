"""Verification gate tests (render-performance CP-4).

The gate runs after a render, before the tmp output is renamed into place:
container duration must equal the cutlist span within one frame, the video
frame count must equal duration * fps, and adjacent cutlist segments must
sample to different frame fingerprints (no frozen picture).
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from src.verify import VerificationError, fingerprint_at, verify

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = "tests/fixtures/synthetic_project"


def _make_media(tmp, seconds, fps=15, color="black", name="clip.mp4"):
    """Render a solid-color video of exactly `seconds` at `fps`."""
    out = Path(tmp) / name
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"color=c={color}:s=640x360:r={fps}:d={seconds}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", str(out)],
        capture_output=True, check=True,
    )
    return out


def _make_two_tone(tmp, fps=15):
    """A 2s video: black for the first second, white for the second."""
    out = Path(tmp) / "twotone.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         "color=c=black:s=640x360:r={}:d=1".format(fps),
         "-f", "lavfi", "-i",
         "color=c=white:s=640x360:r={}:d=1".format(fps),
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", str(out)],
        capture_output=True, check=True,
    )
    return out


class FingerprintTests(unittest.TestCase):
    def test_fingerprint_stable_and_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            black = _make_media(tmp, 2.0, color="black", name="black.mp4")
            white = _make_media(tmp, 2.0, color="white", name="white.mp4")
            fp_black = fingerprint_at(black, 1.0)
            fp_black2 = fingerprint_at(black, 1.0)
            fp_white = fingerprint_at(white, 1.0)
            self.assertEqual(fp_black, fp_black2)
            self.assertNotEqual(fp_black, fp_white)

    def test_fingerprint_at_midpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = _make_media(tmp, 1.0)
            self.assertIsInstance(fingerprint_at(media, 0.5), str)
            self.assertGreater(len(fingerprint_at(media, 0.5)), 0)


class VerifyTests(unittest.TestCase):
    def test_healthy_render_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = _make_two_tone(tmp)
            segments = [
                {"start": 0.0, "end": 1.0, "phase": "hook", "text": None},
                {"start": 1.0, "end": 2.0, "phase": "hook", "text": None},
            ]
            report = verify(media, segments, 15)
            self.assertEqual(report["frame_count"], 30)
            self.assertAlmostEqual(report["duration"], 2.0, delta=0.1)
            self.assertEqual(len(report["fingerprints"]), 2)

    def test_short_render_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = _make_media(tmp, 1.0)  # 1s but cutlist says 2s
            segments = [
                {"start": 0.0, "end": 1.0, "phase": "hook", "text": None},
                {"start": 1.0, "end": 2.0, "phase": "hook", "text": None},
            ]
            with self.assertRaises(VerificationError) as ctx:
                verify(media, segments, 15)
            self.assertIn("duration", str(ctx.exception).lower())

    def test_frozen_picture_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = _make_media(tmp, 2.0, color="black")  # all frames identical
            segments = [
                {"start": 0.0, "end": 1.0, "phase": "hook", "text": None},
                {"start": 1.0, "end": 2.0, "phase": "hook", "text": None},
            ]
            with self.assertRaises(VerificationError) as ctx:
                verify(media, segments, 15)
            self.assertIn("freeze", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
