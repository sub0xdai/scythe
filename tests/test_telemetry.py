"""Progress telemetry tests (Spec F, CP-1)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.telemetry import ProgressParser

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = "tests/fixtures/synthetic_project"


def _events(duration, blocks, min_interval=1.0):
    out = []
    parser = ProgressParser(duration, out.append, min_interval=min_interval)
    for line in blocks:
        parser.feed_line(line)
    return out


class ProgressParserTests(unittest.TestCase):
    def test_emits_progress_with_eta(self):
        blocks = [
            "frame=60", "out_time_us=2000000", "speed=2x", "progress=continue",
            "frame=120", "out_time_us=4000000", "speed=2x", "progress=end",
        ]
        events = _events(4.0, blocks, min_interval=0)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["percent"], 50.0)
        self.assertAlmostEqual(events[0]["eta_seconds"], 1.0)  # (4-2)/2
        self.assertEqual(events[1]["percent"], 100.0)
        self.assertIsNotNone(events[1]["eta_seconds"])

    def test_throttles_bursts(self):
        blocks = []
        for i in range(5):
            blocks += [f"frame={i}", f"out_time_us={i * 1000000}",
                       "speed=1x", "progress=continue"]
        events = _events(10.0, blocks, min_interval=60.0)
        self.assertEqual(len(events), 1)

    def test_forced_emit_on_end(self):
        blocks = ["frame=10", "out_time_us=500000", "speed=1x", "progress=continue",
                  "frame=20", "out_time_us=1000000", "speed=1x", "progress=end"]
        events = _events(1.0, blocks, min_interval=60.0)
        self.assertEqual(len(events), 2)

    def test_skips_until_speed_known(self):
        blocks = ["frame=1", "out_time_us=100000", "progress=continue",
                  "frame=10", "out_time_us=1000000", "speed=1x", "progress=end"]
        events = _events(2.0, blocks, min_interval=0)
        self.assertEqual(len(events), 1)
        self.assertIsNotNone(events[0]["eta_seconds"])

    def test_parses_out_time_hms(self):
        blocks = ["out_time=00:00:02.500000", "speed=1x", "progress=end"]
        events = _events(5.0, blocks, min_interval=0)
        self.assertAlmostEqual(events[0]["out_time"], 2.5)


class TelemetryE2ETests(unittest.TestCase):
    def test_machine_stream_parseable(self):
        env = dict(os.environ, NOX_JSON="1")
        result = subprocess.run(
            [sys.executable, "main.py", "--project", FIXTURE],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            env=env, timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        lines = [json.loads(l) for l in result.stdout.splitlines() if l.strip()]
        self.assertGreater(len(lines), 0)
        self.assertEqual(lines[-1]["type"], "done")
        progress = [e for e in lines if e["type"] == "progress"]
        self.assertGreater(len(progress), 0)
        for event in progress:
            self.assertTrue(0 <= event["percent"] <= 100, event)
            self.assertIsNotNone(event["eta_seconds"], event)
        self.assertNotIn("Project:", result.stdout)  # machine: JSON only

    def test_human_progress_monotonic(self):
        result = subprocess.run(
            [sys.executable, "main.py", "--project", FIXTURE],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        percents = [float(line.split("%")[0].split()[-1])
                    for line in result.stderr.splitlines()
                    if "Progress:" in line]
        self.assertGreater(len(percents), 0)
        self.assertEqual(percents[-1], 100.0)
        self.assertEqual(percents, sorted(percents))

    def test_error_event_on_ffmpeg_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompts = Path(tmp, "prompts")
            prompts.mkdir(parents=True)
            raw = Path(tmp, "raw_footage")
            raw.mkdir()
            # audio-only file: valid media (passes pre-flight), no video stream
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i",
                 "sine=frequency=440:duration=1", "-c:a", "pcm_s16le",
                 str(raw / "clip.wav")],
                check=True, capture_output=True,
            )
            (prompts / "cutlist.json").write_text(json.dumps([
                {"start": 0.0, "end": 1.0, "phase": "hook", "text": None,
                 "asset": "raw_footage/clip.wav", "filter": "grayscale",
                 "effect": None}]))
            (Path(tmp) / "config.json").write_text(json.dumps({
                "resolution": [360, 640], "fps": 15}))
            env = dict(os.environ, NOX_JSON="1")
            result = subprocess.run(
                [sys.executable, "main.py", "--project", tmp],
                cwd=str(REPO_ROOT), capture_output=True, text=True,
                env=env, timeout=300,
            )
            self.assertNotEqual(result.returncode, 0)
            lines = [json.loads(l) for l in result.stdout.splitlines() if l.strip()]
            self.assertGreater(len(lines), 0)
            self.assertEqual(lines[-1]["type"], "error")


if __name__ == "__main__":
    unittest.main()
