"""Post-render evaluation: stderr parsers and rule severity."""

import unittest

from src import eval as evaluation

FREEZE_STDERR = """\
[freezedetect @ 0x55] lavfi.freezedetect.freeze_start: 1.2
[freezedetect @ 0x55] lavfi.freezedetect.freeze_duration: 0.8
[freezedetect @ 0x55] lavfi.freezedetect.freeze_end: 2.0
"""

BLACK_STDERR = """\
[blackdetect @ 0x55] black_start:0.4 black_end:1.1 black_duration:0.7
"""

SILENCE_STDERR = """\
[silencedetect @ 0x55] silence_start: 3.0
[silencedetect @ 0x55] silence_end: 6.5 | silence_duration: 3.5
"""

EBUR128_STDERR = """\
[Parsed_ebur128_1 @ 0x55] Summary:

  Integrated loudness:
    I:         -16.4 LUFS
    Threshold: -26.5 LUFS

  Loudness range:
    LRA:         4.2 LU

  True peak:
    Peak:        0.4 dBFS
"""


class ParserTests(unittest.TestCase):
    def test_freezedetect_spans(self):
        self.assertEqual(evaluation.parse_freezedetect(FREEZE_STDERR),
                         [(1.2, 2.0)])

    def test_blackdetect_spans(self):
        self.assertEqual(evaluation.parse_blackdetect(BLACK_STDERR), [(0.4, 1.1)])

    def test_silencedetect_spans(self):
        self.assertEqual(evaluation.parse_silencedetect(SILENCE_STDERR),
                         [(3.0, 6.5)])

    def test_ebur128_summary(self):
        values = evaluation.parse_ebur128(EBUR128_STDERR)
        self.assertEqual(values["integrated"], -16.4)
        self.assertEqual(values["lra"], 4.2)
        self.assertEqual(values["true_peak"], 0.4)

    def test_empty_stderr_is_silent(self):
        self.assertEqual(evaluation.parse_freezedetect(""), [])
        self.assertEqual(evaluation.parse_blackdetect(""), [])
        self.assertEqual(evaluation.parse_ebur128(""),
                         {"integrated": None, "lra": None, "true_peak": None})

    def test_open_ended_freeze(self):
        spans = evaluation.parse_freezedetect(
            "[freezedetect @ 0x1] lavfi.freezedetect.freeze_start: 4.0")
        self.assertEqual(spans, [(4.0, None)])


class SeverityTests(unittest.TestCase):
    def test_blocking_selects_errors_only(self):
        findings = [
            evaluation.Finding(evaluation.ERROR, "loudness", "off target"),
            evaluation.Finding(evaluation.WARNING, "freeze", "frozen"),
        ]
        self.assertEqual(len(evaluation.blocking(findings)), 1)
        self.assertEqual(evaluation.blocking(findings)[0].rule, "loudness")

    def test_promote_turns_warnings_into_errors(self):
        findings = [evaluation.Finding(evaluation.WARNING, "black", "black run")]
        promoted = evaluation.promote(findings)
        self.assertEqual(promoted[0].severity, evaluation.ERROR)
        self.assertEqual(promoted[0].message, "black run")

    def test_defaults_are_documented(self):
        for key in ("eval_freeze_min", "eval_black_min", "eval_silence_min",
                    "eval_lufs_tolerance", "eval_true_peak_max"):
            self.assertIn(key, evaluation.EVAL_DEFAULTS)


if __name__ == "__main__":
    unittest.main()
