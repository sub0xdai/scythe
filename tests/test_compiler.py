"""Tests for the filtergraph compiler (Spec B, CP-1).

Verifies the emitted -filter_complex structure against the delta spec
scenarios. Runs inside the container where the full suite executes.
"""

import unittest

from src.compiler.graph import AudioSpec, compile_graph, snap_timeline

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
        self.assertIn("noise=alls=4:allf=t:all_seed=1234", graph.filter_complex)

    def test_white_flash_color_segment(self):
        graph = _graph()
        self.assertIn("color=c=white", graph.filter_complex)

    def test_ken_burns_uses_scale_crop(self):
        graph = _graph()
        self.assertNotIn("zoompan", graph.filter_complex)
        self.assertIn("eval=frame", graph.filter_complex)
        self.assertIn("1+0.08*n/30", graph.filter_complex)
        self.assertIn("1+0.15*n/14", graph.filter_complex)

    def test_snap_zoom_steps_at_midpoint(self):
        graph = _graph()
        self.assertIn("if(gt(n,15/2),1.3,1)", graph.filter_complex)

    def test_overlay_composite(self):
        segments = [{"start": 0.0, "end": 1.0, "phase": "hook", "text": None,
                     "asset": "raw_footage/clip.mp4", "filter": None, "effect": None,
                     "overlays": [{"asset": "overlays/logo.png", "opacity": 0.5,
                                   "x": 100, "dy": -100}]}]
        graph = compile_graph(CONFIG, segments, None)
        self.assertIn("overlay=x='100':y='-100*t'", graph.filter_complex)
        self.assertIn("colorchannelmixer=aa=0.5", graph.filter_complex)
        logo_inputs = [a for a in graph.input_args if "logo.png" in " ".join(a)]
        self.assertEqual(len(logo_inputs), 1)
        self.assertNotIn("-loop", logo_inputs[0])

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

    def test_per_reference_inputs_no_loop_no_split(self):
        """Each segment reference registers its own finite input; no -loop 1,
        no split=N fan-out anywhere in the graph (render-performance CP-1)."""
        graph = _graph()
        clip_inputs = [a for a in graph.input_args if "clip.mp4" in " ".join(a)]
        self.assertEqual(len(clip_inputs), 2)  # one input per reference, no dedup
        self.assertEqual(len(graph.input_args), 5)  # clip x2, photo, soundtrack, voiceover
        for args in graph.input_args:
            self.assertNotIn("-loop", args)
            self.assertNotIn("-framerate", args)
        self.assertNotIn("]split=", graph.filter_complex)  # no video fan-out; asplit for audio ducking is fine

    def test_snap_timeline_rounds_to_frame_boundary(self):
        segments = [
            {"start": 0.0, "end": 2.08, "phase": "hook", "text": None},
            {"start": 2.08, "end": 4.0, "phase": "hook", "text": None},
        ]
        snapped = snap_timeline(segments, 15)
        self.assertEqual(snapped[0]["end"], 31 / 15)  # round(2.08*15)/15
        self.assertEqual(snapped[1]["start"], 31 / 15)
        self.assertEqual(snapped[-1]["end"], 4.0)

    def test_snap_timeline_preserves_continuity(self):
        segments = [
            {"start": 0.0, "end": 1.07, "phase": "hook", "text": None},
            {"start": 1.07, "end": 2.0, "phase": "hook", "text": None},
        ]
        snapped = snap_timeline(segments, 15)
        self.assertEqual(snapped[0]["end"], snapped[1]["start"])

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
        self.assertIn("[0:v]trim=", graph.filter_complex)
        self.assertIn("[1:v]trim=", graph.filter_complex)
        self.assertIn("[2:v]trim=", graph.filter_complex)
        self.assertIn("[3:a]atrim=", graph.filter_complex)


if __name__ == "__main__":
    unittest.main()
