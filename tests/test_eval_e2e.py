"""Evaluation against a real rendered file: black and silence are found."""

import os
import shutil
import subprocess
import tempfile
import unittest

from src import eval as evaluation

CONFIG = {"lufs_target": -14}


def _render(directory, seconds=3.0, audio=True):
    path = os.path.join(directory, "black.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
           "-i", f"color=c=black:s=160x120:r=15:d={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=mono",
                "-shortest", "-c:a", "aac"]
    cmd += ["-pix_fmt", "yuv420p", path]
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    return path


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not available")
class EvaluationTests(unittest.TestCase):
    def test_black_picture_is_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = evaluation.evaluate(_render(tmp, audio=False), CONFIG,
                                           has_audio=False)
        rules = [f.rule for f in findings]
        self.assertIn("black", rules)
        self.assertTrue(all(f.severity == evaluation.WARNING for f in findings))

    def test_silent_audio_is_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = evaluation.evaluate(_render(tmp), CONFIG, has_audio=True)
        rules = [f.rule for f in findings]
        self.assertIn("silence", rules)

    def test_strict_mode_blocks_the_same_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = evaluation.evaluate(_render(tmp, audio=False), CONFIG,
                                           has_audio=False)
        self.assertTrue(evaluation.blocking(findings) == [])
        self.assertTrue(evaluation.blocking(evaluation.promote(findings)))

    def test_loudness_is_measured_not_assumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tone.mp4")
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y",
                 "-f", "lavfi", "-i", "color=c=gray:s=160x120:r=15:d=3",
                 "-f", "lavfi", "-i", "sine=f=440:d=3",
                 "-shortest", "-pix_fmt", "yuv420p", "-c:a", "aac", path],
                check=True, capture_output=True, timeout=300)
            stderr = evaluation._audio_pass(path, evaluation.EVAL_DEFAULTS)
        measured = evaluation.parse_ebur128(stderr)
        self.assertIsNotNone(measured["integrated"])
        self.assertIsNotNone(measured["true_peak"])


if __name__ == "__main__":
    unittest.main()
