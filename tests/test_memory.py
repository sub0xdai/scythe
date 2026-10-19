"""Project memory: header creation, append, findings and notes."""

import os
import tempfile
import unittest

from src.memory import MEMORY_FILE, record
from src.tracks import parse_document

CONFIG = {
    "resolution": [1920, 1080],
    "fps": 30,
    "theme": None,
    "transition_mode": "cross_dissolve",
}

TIMELINE = parse_document([
    {"start": 0.0, "end": 1.0, "asset": "raw/a.mp4"},
    {"start": 1.0, "end": 2.5, "asset": "raw/b.mp4"},
])


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def _read(self):
        with open(os.path.join(self.dir, MEMORY_FILE)) as f:
            return f.read()

    def test_first_record_writes_header(self):
        record(self.dir, outputs=["out/master.mp4"], duration=2.5,
               timeline=TIMELINE, config=CONFIG)
        text = self._read()
        self.assertTrue(text.startswith("# project log"))
        self.assertIn("master.mp4", text)
        self.assertIn("duration: 2.500s", text)

    def test_shape_line_reports_tracks_and_transitions(self):
        record(self.dir, outputs=["out/master.mp4"], duration=2.5,
               timeline=TIMELINE, config=CONFIG)
        self.assertIn("1920x1080 @ 30fps", self._read())
        self.assertIn("transitions cross_dissolve", self._read())
        self.assertIn("1 video track(s), 0 audio track(s)", self._read())

    def test_second_record_appends(self):
        record(self.dir, outputs=["a.mp4"], duration=1.0,
               timeline=TIMELINE, config=CONFIG, note="first")
        record(self.dir, outputs=["b.mp4"], duration=2.0,
               timeline=TIMELINE, config=CONFIG, note="second")
        text = self._read()
        self.assertIn("note: first", text)
        self.assertIn("note: second", text)
        self.assertEqual(text.count("# project log"), 1)
        self.assertEqual(text.count("## 20"), 2)

    def test_findings_are_recorded_with_severity(self):
        findings = [
            _finding("warning", "freeze", "frozen picture 1.0s-2.0s"),
            _finding("error", "loudness", "off target"),
        ]
        record(self.dir, outputs=["a.mp4"], duration=1.0,
               timeline=TIMELINE, config=CONFIG, findings=findings)
        text = self._read()
        self.assertIn("1 error(s), 1 warning(s)", text)
        self.assertIn("warning freeze: frozen picture 1.0s-2.0s", text)
        self.assertIn("error loudness: off target", text)

    def test_no_findings_reports_zero(self):
        record(self.dir, outputs=["a.mp4"], duration=1.0,
               timeline=TIMELINE, config=CONFIG)
        self.assertIn("0 error(s), 0 warning(s)", self._read())


def _finding(severity, rule, message):
    from src.eval import Finding
    return Finding(severity, rule, message)


if __name__ == "__main__":
    unittest.main()
