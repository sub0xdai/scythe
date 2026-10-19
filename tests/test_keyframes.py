"""Keyframe interpolation: expression shape, defaults, degenerate lists."""

import unittest

from src.compiler.keyframes import keyframe_chain


class KeyframeChainTests(unittest.TestCase):
    def test_empty_list_is_identity(self):
        self.assertEqual(keyframe_chain(None, 640, 360, 30), "")
        self.assertEqual(keyframe_chain([], 640, 360, 30), "")

    def test_single_static_keyframe_is_identity(self):
        kfs = [{"at": 0.0, "scale": 1.0, "x": 0, "y": 0}]
        self.assertEqual(keyframe_chain(kfs, 640, 360, 30), "")

    def test_zoom_builds_scale_and_crop(self):
        kfs = [{"at": 0.0, "scale": 1.0}, {"at": 1.0, "scale": 1.4}]
        chain = keyframe_chain(kfs, 640, 360, 60)
        self.assertIn("scale=w='640*", chain)
        self.assertIn("eval=frame", chain)
        self.assertIn("crop=w=640:h=360", chain)
        self.assertIn("lerp(1,1.4", chain)

    def test_pan_only_still_scales(self):
        kfs = [{"at": 0.0, "x": 0}, {"at": 1.0, "x": -80}]
        chain = keyframe_chain(kfs, 640, 360, 30)
        self.assertIn("(iw-640)/2+", chain)
        self.assertIn("lerp(0,-80", chain)

    def test_hold_after_last_keyframe(self):
        kfs = [{"at": 0.0, "scale": 1.0}, {"at": 0.5, "scale": 1.2}]
        chain = keyframe_chain(kfs, 640, 360, 30)
        self.assertIn("if(lt(", chain)
        self.assertIn(",1.2)", chain)

    def test_three_keyframes_nest(self):
        kfs = [
            {"at": 0.0, "scale": 1.0},
            {"at": 0.5, "scale": 1.2},
            {"at": 1.0, "scale": 1.0},
        ]
        chain = keyframe_chain(kfs, 640, 360, 30)
        self.assertEqual(chain.count("if(lt("), 4)

    def test_each_axis_gets_its_own_expression(self):
        kfs = [
            {"at": 0.0, "scale": 1.0, "x": 0, "y": 0},
            {"at": 0.5, "scale": 1.2, "x": 10, "y": -10},
            {"at": 1.0, "scale": 1.0, "x": 0, "y": 0},
        ]
        chain = keyframe_chain(kfs, 640, 360, 30)
        self.assertEqual(chain.count("if(lt("), 8)
        self.assertIn("lerp(0,10", chain)
        self.assertIn("lerp(0,-10", chain)

    def test_zero_frame_count_is_guarded(self):
        kfs = [{"at": 0.0, "scale": 1.0}, {"at": 1.0, "scale": 1.2}]
        self.assertIn("n/1)", keyframe_chain(kfs, 640, 360, 0))

    def test_deterministic(self):
        kfs = [{"at": 0.0, "scale": 1.0, "x": 0}, {"at": 1.0, "scale": 1.3, "x": 40}]
        first = keyframe_chain(kfs, 1920, 1080, 90)
        second = keyframe_chain(kfs, 1920, 1080, 90)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
