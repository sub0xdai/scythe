"""Tests for the filtergraph compiler (Spec B, CP-1).

Verifies the emitted -filter_complex structure against the delta spec
scenarios. Runs inside the container where the full suite executes.
"""

import unittest

from src.compiler.graph import AudioSpec, compile_graph

CONFIG = {
    "resolution": [360, 640],
    "fps": 15,
    "font": "LiberationSerif-Bold",
    "font_size": 28,
    "stroke_width": 4,
    "stroke_color": "black",
    "text_color": "white",
}

# Mirrors tests/fixtures/synthetic_project/prompts/cutlist.json
SEGMENTS = [
    {"start": 0.0, "end": 2.0, "phase": "hook", "text": "THE PROBLEM",
     "asset": "raw_footage/clip.mp4", "filter": "grayscale", "effect": "ken_burns_slow"},
    {"start": 2.0, "end": 2.08, "phase": "drop_transition", "text": None,
     "asset": None, "filter": "white_flash", "effect": "strobe"},
    {"start": 2.08, "end": 3.08, "phase": "kinetic_cut", "text": "THE FIX",
     "asset": "raw_footage/photo.png", "filter": "high_contrast_green", "effect": "snap_zoom"},
    {"start": 3.08, "end": 4.0, "phase": "kinetic_cut", "text": "BUILD NOW",
     "asset": "raw_footage/clip.mp4", "filter": "chromatic_aberration", "effect": "ken_burns_fast"},
]

AUDIO = AudioSpec(soundtrack="audio/soundtrack.wav", voiceover="audio/voiceover.wav")


def _graph(audio=AUDIO, segments=SEGMENTS, ass_path=None):
    return compile_graph(CONFIG, segments, audio, ".", None, ass_path)


class GraphStructureTests(unittest.TestCase):
    def test_single_filter_complex(self):
        graph = _graph()
        self.assertIsInstance(graph.filter_complex, str)
        self.assertGreater(len(graph.filter_complex), 0)
        self.assertEqual(graph.filter_complex.count("concat="), 1)

    def test_filter_nodes_present(self):
        graph = _graph()
        self.assertIn("rgbashift", graph.filter_complex)
        self.assertIn("hue=s=0", graph.filter_complex)
        self.assertIn("lutrgb", graph.filter_complex)

    def test_film_grain_seeded(self):
        segments = [{"start": 0.0, "end": 1.0, "phase": "hook",
                     "text": None, "asset": "raw_footage/clip.mp4",
                     "filter": "film_grain", "effect": None}]
        graph = compile_graph(CONFIG, segments, None)
        self.assertIn("noise=alls=4:allf=t:seed=1234", graph.filter_complex)

    def test_white_flash_color_segment(self):
        graph = _graph()
        self.assertIn("color=c=white", graph.filter_complex)

    def test_zoompan_for_ken_burns(self):
        graph = _graph()
        self.assertIn("zoompan", graph.filter_complex)
        self.assertIn("1+0.08*in/30", graph.filter_complex)
        self.assertIn("1+0.15*in/14", graph.filter_complex)

    def test_snap_zoom_steps_at_midpoint(self):
        graph = _graph()
        self.assertIn("if(gt(in,15/2),1.3,1)", graph.filter_complex)

    def test_drawtext_carries_text(self):
        graph = _graph(ass_path="output/subtitles.ass")
        self.assertIn("subtitles=filename=output/subtitles.ass", graph.filter_complex)
        self.assertNotIn("drawtext", graph.filter_complex)

    def test_ducking_nodes(self):
        graph = _graph()
        self.assertIn("sidechaincompress", graph.filter_complex)
        self.assertIn("amix=inputs=2:normalize=0", graph.filter_complex)

    def test_audio_absent_when_none(self):
        graph = _graph(audio=None)
        self.assertIsNone(graph.audio_maps)
        self.assertNotIn("amix", graph.filter_complex)

    def test_concat_count(self):
        graph = _graph()
        self.assertIn("concat=n=4:v=1:a=0", graph.filter_complex)

    def test_input_dedup_and_labels(self):
        graph = _graph()
        clip_inputs = [a for a in graph.input_args if "clip.mp4" in " ".join(a)]
        self.assertEqual(len(clip_inputs), 1)
        self.assertEqual(len(graph.input_args), 4)  # clip.mp4, photo.png, soundtrack, voiceover
        self.assertIn("split=2", graph.filter_complex)

    def test_image_input_looped(self):
        graph = _graph()
        image_args = [a for a in graph.input_args if "photo.png" in " ".join(a)][0]
        self.assertIn("-loop", image_args)
        self.assertIn("-framerate", image_args)

    def test_deterministic(self):
        self.assertEqual(_graph().filter_complex, _graph().filter_complex)

    def test_video_map_label(self):
        graph = _graph()
        self.assertTrue(graph.outputs[0].label.startswith("["))
        self.assertTrue(graph.outputs[0].label.endswith("]"))

    def test_duration_from_cutlist(self):
        graph = _graph()
        self.assertAlmostEqual(graph.duration, 4.0)
        self.assertIn("trim=duration=4", graph.filter_complex)

    def test_segment_labels_tight(self):
        """Input labels must be directly followed by the first filter (no comma)."""
        graph = _graph()
        self.assertIn("[v0_0]trim=", graph.filter_complex)
        self.assertIn("[1:v]trim=", graph.filter_complex)
        self.assertIn("[2:a]atrim=", graph.filter_complex)


if __name__ == "__main__":
    unittest.main()
