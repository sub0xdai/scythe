"""ASS subtitle generation tests (Spec D, CP-1).

build_ass is pure: input segments + config, output .ass content. The
scenario assertions target the generator output (events, wrapping,
safe-zone margins, karaoke tags, lower-thirds).
"""

import re
import unittest

from src.compiler.text import build_ass

CONFIG = {
    "resolution": [1080, 1920],
    "fps": 30,
    "font": "LiberationSerif-Bold",
    "font_size": 72,
    "stroke_width": 4,
    "stroke_color": "black",
    "text_color": "white",
    "text_box_width": 0.8,
    "safe_zone_top": 0.12,
    "safe_zone_bottom": 0.25,
}

TEXT_SEGMENTS = [
    {"start": 0.0, "end": 2.0, "phase": "hook", "text": "THE PROBLEM",
     "asset": None, "filter": "white_flash", "effect": None},
    {"start": 2.0, "end": 4.0, "phase": "kinetic_cut", "text": "THE FIX",
     "asset": None, "filter": "white_flash", "effect": None},
]


class AssGenerationTests(unittest.TestCase):
    def test_plain_text_event_emitted(self):
        content = build_ass(TEXT_SEGMENTS, CONFIG)
        self.assertIn("[Events]", content)
        self.assertIn("Dialogue: 0,0:00:00.00,0:00:02.00,Default", content)
        self.assertIn("THE PROBLEM", content)
        self.assertIn("THE FIX", content)

    def test_no_text_returns_none(self):
        segments = [{"start": 0.0, "end": 1.0, "phase": "hook",
                     "text": None, "asset": None,
                     "filter": "white_flash", "effect": None}]
        self.assertIsNone(build_ass(segments, CONFIG))

    def test_long_text_wraps_within_box(self):
        text = " ".join(["SUPERCALIFRAGILISTIC"] * 4)  # 4 x 21 chars
        segments = [{"start": 0.0, "end": 2.0, "phase": "hook", "text": text,
                     "asset": None, "filter": "white_flash", "effect": None}]
        content = build_ass(segments, CONFIG)
        # 1080*0.8 / (72*0.55) = 21 chars per line; 84 chars -> 4+ lines
        event = next(l for l in content.splitlines()
                     if l.startswith("Dialogue:"))
        lines = event.split(",,")[2].split("\\N")
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(len(line) <= 21 for line in lines))

    def test_safe_zone_margin_v(self):
        content = build_ass(TEXT_SEGMENTS, CONFIG)
        # 1080x1920, bottom 25% -> MarginV 480; L/R = (1-0.8)*1080/2 = 108
        self.assertIn("2,108,108,480,1", content)

    def test_safe_zones_configurable(self):
        config = dict(CONFIG, safe_zone_bottom=0.1)
        content = build_ass(TEXT_SEGMENTS, config)
        self.assertIn("2,108,108,192,1", content)

    def test_word_flash_karaoke_tags(self):
        segments = [{"start": 0.0, "end": 2.0, "phase": "hook",
                     "text": "THE PROBLEM IS REAL", "asset": None,
                     "filter": "white_flash", "effect": "word_flash"}]
        content = build_ass(segments, CONFIG)
        event = next(l for l in content.splitlines()
                     if l.startswith("Dialogue:"))
        tags = [int(m) for m in re.findall(r"\\k(\d+)", event)]
        self.assertEqual(len(tags), 4)
        self.assertEqual(sum(tags), 200)  # 2.0s = 200 centiseconds

    def test_lower_third_emitted(self):
        segments = [{"start": 0.0, "end": 3.0, "phase": "kinetic_cut",
                     "text": None, "asset": None,
                     "filter": "white_flash", "effect": None,
                     "lower_third": {"title": "DR. NOX",
                                     "subtitle": "SYSTEMS ENGINEER"}}]
        content = build_ass(segments, CONFIG)
        self.assertIn("LowerThird", content)
        self.assertIn("DR. NOX\\N SYSTEMS ENGINEER".replace(" ", ""),
                      content.replace(" ", ""))
        self.assertIn("\\fad(150,150)", content)

    def test_deterministic(self):
        self.assertEqual(build_ass(TEXT_SEGMENTS, CONFIG),
                         build_ass(TEXT_SEGMENTS, CONFIG))


if __name__ == "__main__":
    unittest.main()
