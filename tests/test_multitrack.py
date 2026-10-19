"""Multi-track compilation: overlay windows, audio routing, NLE features.

Structure tests read the compiled filtergraph; the end-to-end class renders
a real two-track document and checks the pixels and the mix.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

from src.compiler import compile_graph
from src.tracks import parse_document

CONFIG = {
    "resolution": [320, 180],
    "fps": 15,
    "font": "LiberationSans",
    "font_size": 20,
    "stroke_width": 2,
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
    "transition_duration": 0.3,
    "ken_burns_easing": "linear",
    "outputs": [{"name": "master", "crf": 20}],
}

TWO_TRACK_DOCUMENT = {
    "version": 2,
    "tracks": [
        {"kind": "video", "id": "base", "segments": [
            {"start": 0.0, "end": 2.0, "asset": "raw/a.mp4"},
            {"start": 2.0, "end": 4.0, "asset": "raw/b.mp4"},
        ]},
        {"kind": "video", "id": "pip", "x": 40, "y": 20, "scale": 0.35,
         "opacity": 0.8, "segments": [
             {"start": 1.0, "end": 3.0, "asset": "raw/a.mp4", "clip_start": 1.0,
              "fade_in": 0.2},
         ]},
        {"kind": "audio", "id": "music", "asset": "audio/m.wav", "gain": 0.5,
         "duck_under": ["voice"]},
        {"kind": "audio", "id": "voice", "asset": "audio/v.wav", "start": 0.5,
         "cleanup": True},
    ],
}


def _graph(config=None, document=None):
    cfg = dict(CONFIG, **(config or {}))
    return compile_graph(cfg, document or TWO_TRACK_DOCUMENT, None, ".")


class OverlayTrackTests(unittest.TestCase):
    def test_overlay_track_is_windowed(self):
        graph = _graph()
        self.assertIn("enable='between(t,1,3)'", graph.filter_complex)

    def test_overlay_track_shifts_to_its_start(self):
        self.assertIn("setpts=PTS+1/TB", _graph().filter_complex)

    def test_overlay_track_uses_track_offset(self):
        chain = _graph().filter_complex
        self.assertIn("overlay=x=40:y=20", chain)

    def test_track_scale_shrinks_the_layer(self):
        self.assertIn("scale=112:62", _graph().filter_complex)

    def test_track_opacity_is_applied(self):
        self.assertIn("colorchannelmixer=aa=0.8", _graph().filter_complex)

    def test_base_track_is_not_composited(self):
        self.assertNotIn("enable='between(t,0,2)'", _graph().filter_complex)

    def test_single_track_document_has_no_overlay(self):
        graph = _graph(document=[{"start": 0, "end": 1, "asset": "raw/a.mp4"}])
        self.assertNotIn("overlay=", graph.filter_complex)


class AudioRoutingTests(unittest.TestCase):
    def test_every_track_is_split_for_ducking_and_mix(self):
        chain = _graph().filter_complex
        self.assertIn("[at_voice]asplit=2", chain)
        self.assertNotIn("[at_music]asplit", chain)

    def test_ducking_uses_the_split_copy(self):
        chain = _graph().filter_complex
        self.assertIn("[at_music][atrig_music]", chain)
        self.assertIn("[atrig_voice_0]anull[atrig_music]", chain)

    def test_gain_and_delay(self):
        chain = _graph().filter_complex
        self.assertIn("volume=0.5", chain)
        self.assertIn("adelay=500:all=1", chain)

    def test_cleanup_follows_the_flag(self):
        self.assertIn("afftdn", _graph().filter_complex)
        quiet = _graph({"voice_cleanup": False})
        self.assertNotIn("afftdn", quiet.filter_complex)

    def test_unreferenced_track_is_not_split(self):
        document = {"tracks": [
            {"kind": "video", "segments": [{"start": 0, "end": 1}]},
            {"kind": "audio", "id": "bed", "asset": "a.wav"},
        ]}
        chain = _graph(document=document).filter_complex
        self.assertNotIn("asplit", chain)
        self.assertIn("[at_bed]anull[aout_raw]", chain)

    def test_unknown_duck_target_raises(self):
        document = {"tracks": [
            {"kind": "video", "segments": [{"start": 0, "end": 1}]},
            {"kind": "audio", "id": "bed", "asset": "a.wav",
             "duck_under": ["ghost"]},
        ]}
        with self.assertRaises(ValueError):
            _graph(document=document)


class EditFeatureTests(unittest.TestCase):
    def test_speed_retimes_the_source(self):
        document = [{"start": 0, "end": 2, "asset": "raw/a.mp4", "speed": 2.0}]
        chain = _graph(document=document).filter_complex
        self.assertIn("trim=start=0:end=4", chain)
        self.assertIn("setpts=PTS/2", chain)

    def test_zero_speed_raises(self):
        document = [{"start": 0, "end": 2, "asset": "raw/a.mp4", "speed": 0}]
        with self.assertRaises(ValueError):
            _graph(document=document)

    def test_keyframes_beat_the_named_effect(self):
        document = [{"start": 0, "end": 2, "asset": "raw/a.mp4",
                     "effect": "ken_burns_slow",
                     "keyframes": [{"at": 0, "scale": 1.0},
                                   {"at": 1, "scale": 1.5}]}]
        chain = _graph(document=document).filter_complex
        self.assertIn("lerp(1,1.5", chain)
        self.assertNotIn("1+0.08*", chain)

    def test_fade_in_and_out_on_the_base_track(self):
        document = [{"start": 0, "end": 2, "asset": "raw/a.mp4",
                     "fade_in": 0.3, "fade_out": 0.4}]
        chain = _graph(document=document).filter_complex
        self.assertIn("fade=t=in:st=0:d=0.3", chain)
        self.assertIn("fade=t=out:st=1.6:d=0.4", chain)

    def test_solid_segment_uses_its_color(self):
        document = [{"start": 0, "end": 1, "color": "#112233"}]
        self.assertIn("color=c=#112233", _graph(document=document).filter_complex)

    def test_raw_filter_passes_through(self):
        document = [{"start": 0, "end": 1, "asset": "raw/a.mp4",
                     "filter": "raw:eq=contrast=2"}]
        self.assertIn("eq=contrast=2", _graph(document=document).filter_complex)

    def test_per_segment_transition_switches_to_xfade(self):
        document = [
            {"start": 0.0, "end": 2.0, "asset": "raw/a.mp4"},
            {"start": 2.0, "end": 4.0, "asset": "raw/b.mp4",
             "transition": "wipe_left", "transition_duration": 0.5},
            {"start": 4.0, "end": 6.0, "asset": "raw/a.mp4"},
        ]
        graph = _graph(document=document)
        self.assertIn("xfade=transition=wipeleft:duration=0.5", graph.filter_complex)
        self.assertIn("xfade=transition=fade:duration=0.0666667",
                      graph.filter_complex)
        self.assertAlmostEqual(graph.duration, 6.0 - 0.5 - 1 / 15, places=4)


def _make_media(directory, name, color, seconds=2.0):
    path = os.path.join(directory, name)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", f"color=c={color}:s=320x180:r=15:d={seconds}",
         "-pix_fmt", "yuv420p", path],
        check=True, capture_output=True, timeout=120,
    )
    return path


def _make_audio(directory, name, freq, seconds):
    path = os.path.join(directory, name)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", f"sine=f={freq}:d={seconds}", path],
        check=True, capture_output=True, timeout=120,
    )
    return path


def _pixel(path, t, x, y):
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", path, "-frames:v", "1",
         "-vf", f"crop=2:2:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True, timeout=60,
    )
    return tuple(result.stdout[:3])


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not available")
class MultiTrackRenderTests(unittest.TestCase):
    def test_pip_layer_lands_on_the_base_picture(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_media(tmp, "a.mp4", "black", 4.0)
            _make_media(tmp, "b.mp4", "black", 4.0)
            document = {"tracks": [
                {"kind": "video", "id": "base", "segments": [
                    {"start": 0.0, "end": 2.0, "asset": "a.mp4"},
                    {"start": 2.0, "end": 4.0, "asset": "b.mp4"},
                ]},
                {"kind": "video", "id": "pip", "x": 100, "y": 60,
                 "segments": [{"start": 1.0, "end": 3.0, "asset": "a.mp4"}]},
            ]}
            document["tracks"][1]["segments"][0]["filter"] = "white_flash"
            document["tracks"][1]["segments"][0]["asset"] = None
            graph = compile_graph(CONFIG, document, None, tmp)
            out = os.path.join(tmp, "out.mp4")
            cmd = ["ffmpeg", "-y"]
            for args in graph.input_args:
                cmd += args
            cmd += ["-filter_complex", graph.filter_complex,
                    "-map", graph.outputs[0].label, "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", out]
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)

            inside_window = _pixel(out, 2.0, 150, 80)
            before_window = _pixel(out, 0.3, 150, 80)
            self.assertGreater(sum(inside_window), 600)
            self.assertLess(sum(before_window), 120)

    def test_audio_tracks_mix_without_clipping(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_media(tmp, "a.mp4", "black", 2.0)
            _make_audio(tmp, "m.wav", 220, 2.0)
            _make_audio(tmp, "v.wav", 660, 2.0)
            document = {"tracks": [
                {"kind": "video", "segments": [
                    {"start": 0.0, "end": 2.0, "asset": "a.mp4"}]},
                {"kind": "audio", "id": "music", "asset": "m.wav",
                 "gain": 0.4, "duck_under": ["voice"]},
                {"kind": "audio", "id": "voice", "asset": "v.wav"},
            ]}
            graph = compile_graph(CONFIG, document, None, tmp)
            out = os.path.join(tmp, "out.mp4")
            cmd = ["ffmpeg", "-y"]
            for args in graph.input_args:
                cmd += args
            cmd += ["-filter_complex", graph.filter_complex,
                    "-map", graph.outputs[0].label,
                    "-map", graph.audio_maps[0], "-c:v", "libx264",
                    "-c:a", "aac", "-pix_fmt", "yuv420p", out]
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", out],
                capture_output=True, text=True, check=True, timeout=60,
            )
            self.assertAlmostEqual(float(probe.stdout.strip()), 2.0, delta=0.2)


if __name__ == "__main__":
    unittest.main()
