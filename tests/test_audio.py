"""Audio mastering chain tests (Spec E, CP-1).

Structural: the compiled graph must carry sidechaincompress, loudnorm,
and the configurable voice-cleanup chain. End-to-end audio behavior
tests land in CP-2.
"""

import unittest

from src.compiler import compile_graph
from src.compiler.graph import AudioSpec

CONFIG = {
    "resolution": [360, 640],
    "fps": 15,
    "font": "LiberationSerif-Bold",
    "font_size": 28,
    "stroke_width": 4,
    "stroke_color": "black",
    "text_color": "white",
    "lufs_target": -14,
    "voice_cleanup": True,
    "duck_threshold": 0.05,
    "duck_ratio": 8,
}

SEGMENTS = [
    {"start": 0.0, "end": 2.0, "phase": "hook", "text": None,
     "asset": "raw_footage/clip.mp4", "filter": "grayscale", "effect": "ken_burns_slow"},
    {"start": 2.0, "end": 4.0, "phase": "kinetic_cut", "text": None,
     "asset": "raw_footage/clip.mp4", "filter": "color_invert", "effect": None},
]

AUDIO = AudioSpec(soundtrack="audio/soundtrack.wav", voiceover="audio/voiceover.wav")


class AudioChainStructureTests(unittest.TestCase):
    def test_sidechain_and_loudnorm_present(self):
        graph = compile_graph(CONFIG, SEGMENTS, AUDIO, ".")
        self.assertIn("sidechaincompress", graph.filter_complex)
        self.assertIn("loudnorm=I=-14:TP=-1.5:LRA=11", graph.filter_complex)
        self.assertIn("amix=inputs=2:normalize=0", graph.filter_complex)

    def test_cleanup_nodes_present_by_default(self):
        graph = compile_graph(CONFIG, SEGMENTS, AUDIO, ".")
        self.assertIn("afftdn", graph.filter_complex)
        self.assertIn("agate", graph.filter_complex)

    def test_cleanup_disabled_removes_nodes(self):
        config = dict(CONFIG, voice_cleanup=False)
        graph = compile_graph(config, SEGMENTS, AUDIO, ".")
        self.assertNotIn("afftdn", graph.filter_complex)
        self.assertNotIn("agate", graph.filter_complex)
        self.assertIn("sidechaincompress", graph.filter_complex)

    def test_static_ducking_removed(self):
        graph = compile_graph(CONFIG, SEGMENTS, AUDIO, ".")
        self.assertNotIn("volume=0.3", graph.filter_complex)

    def test_single_track_gets_loudnorm(self):
        graph = compile_graph(CONFIG, SEGMENTS, AudioSpec(soundtrack="audio/music.wav"), ".")
        self.assertIn("loudnorm=I=-14:TP=-1.5:LRA=11", graph.filter_complex)
        self.assertNotIn("sidechaincompress", graph.filter_complex)

    def test_lufs_target_configurable(self):
        config = dict(CONFIG, lufs_target=-16)
        graph = compile_graph(config, SEGMENTS, AUDIO, ".")
        self.assertIn("loudnorm=I=-16:TP=-1.5:LRA=11", graph.filter_complex)

    def test_audio_offset_still_applied(self):
        config = dict(CONFIG, audio_offset=0.5)
        graph = compile_graph(config, SEGMENTS, AUDIO, ".")
        self.assertIn("atrim=start=0.5:end=4.5", graph.filter_complex)


if __name__ == "__main__":
    unittest.main()
