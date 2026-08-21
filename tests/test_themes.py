"""Theme loader, LUT, and registry tests (Spec C, CP-1)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.compiler import compile_graph
from src.themes import ThemeError, load_theme

REPO_ROOT = Path(__file__).resolve().parent.parent

BASE_CONFIG = {
    "resolution": [360, 640],
    "fps": 15,
    "font": "LiberationSerif-Bold",
    "font_size": 28,
    "stroke_width": 4,
    "stroke_color": "black",
    "text_color": "white",
    "lufs_target": -14,
    "voice_cleanup": True,
    "duck_threshold": 0.02,
    "duck_ratio": 2,
    "text_box_width": 0.8,
    "safe_zone_top": 0.12,
    "safe_zone_bottom": 0.25,
    "default_filter": None,
    "default_effect": None,
    "transition_mode": "hard_cut",
    "transition_duration": 0.5,
    "ken_burns_easing": "linear",
}

SEGMENTS = [
    {"start": 0.0, "end": 2.0, "phase": "hook", "text": "THE HOOK",
     "asset": "raw_footage/clip.mp4", "filter": "grayscale",
     "effect": "ken_burns_slow"},
    {"start": 2.0, "end": 4.0, "phase": "kinetic_cut", "text": None,
     "asset": "raw_footage/photo.png"},
]

AUDIO = None

WHITE_FLASH_SEGMENT = [
    {"start": 0.0, "end": 2.0, "phase": "hook", "text": None,
     "asset": None, "filter": "white_flash", "effect": "strobe"},
]


class ThemeLoaderTests(unittest.TestCase):
    def test_loads_bundled_theme_by_name(self):
        theme = load_theme("brutalist")
        self.assertIsInstance(theme, dict)

    def test_unknown_theme_raises(self):
        with self.assertRaises(ThemeError):
            load_theme("no_such_theme")

    def test_invalid_theme_field_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "bad.json")
            path.write_text(json.dumps({"font": "X", "bogus_key": 1}))
            with self.assertRaises(ThemeError) as ctx:
                load_theme(str(path))
            self.assertIn("bogus_key", str(ctx.exception))

    def test_loads_theme_by_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "custom.json")
            path.write_text(json.dumps({"font": "LiberationSans-Bold"}))
            self.assertEqual(load_theme(str(path))["font"], "LiberationSans-Bold")


class ThemeIntegrationTests(unittest.TestCase):
    def test_theme_applied_through_load_config(self):
        from main import load_config
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "config.json").write_text(json.dumps(
                {"theme": "clean_editorial"}))
            prompts = Path(tmp, "prompts")
            prompts.mkdir(parents=True)
            segments = [{"start": 0.0, "end": 2.0, "phase": "hook",
                         "text": "THE HOOK", "asset": "raw_footage/clip.mp4"}]
            (prompts / "cutlist.json").write_text(json.dumps(segments))
            config = load_config(tmp)
            self.assertEqual(config["transition_mode"], "cross_dissolve")
            graph = compile_graph(config, segments, None, tmp)
            self.assertIn("hue=s=0", graph.filter_complex)  # theme default filter

    def test_brutalist_parity(self):
        base = compile_graph(BASE_CONFIG, SEGMENTS, AUDIO, ".")
        themed_config = dict(BASE_CONFIG)
        themed_config.update(load_theme("brutalist"))
        themed = compile_graph(themed_config, SEGMENTS, AUDIO, ".")
        self.assertEqual(base.filter_complex, themed.filter_complex)

    def test_lut_node_in_graph(self):
        config = dict(BASE_CONFIG, lut="grade/teal.cube")
        graph = compile_graph(config, SEGMENTS, AUDIO, ".")
        self.assertIn("lut3d=file=", graph.filter_complex)
        self.assertIn("teal.cube", graph.filter_complex)
        self.assertIn("interp=tetrahedral", graph.filter_complex)

    def test_missing_lut_aborts_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompts = Path(tmp, "prompts")
            prompts.mkdir(parents=True)
            (prompts / "cutlist.json").write_text(json.dumps(WHITE_FLASH_SEGMENT))
            (Path(tmp) / "config.json").write_text(json.dumps(
                {"lut": "grade/nope.cube"}))
            result = subprocess.run(
                [sys.executable, "main.py", "--project", tmp],
                cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nope.cube", result.stdout)

    def test_unknown_filter_rejected_with_theme(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompts = Path(tmp, "prompts")
            prompts.mkdir(parents=True)
            (prompts / "cutlist.json").write_text(json.dumps([
                {"start": 0.0, "end": 1.0, "phase": "hook", "text": None,
                 "asset": None, "filter": "sepia", "effect": None}]))
            (Path(tmp) / "config.json").write_text(json.dumps(
                {"theme": "clean_editorial"}))
            result = subprocess.run(
                [sys.executable, "main.py", "--project", tmp],
                cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schema", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
