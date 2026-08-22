"""Audio mastering chain tests (Spec E, CP-1).

Structural: the compiled graph must carry sidechaincompress, loudnorm,
and the configurable voice-cleanup chain. End-to-end audio behavior
tests land in CP-2.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

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

REPO_ROOT = Path(__file__).resolve().parent.parent


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


class _AudioProjectMixin:
    """Temp project with crafted wavs; no video assets needed."""

    def _make_project(self, tmp, soundtrack_spec, voiceover_spec):
        prompts = Path(tmp, "prompts")
        prompts.mkdir(parents=True)
        audio_dir = Path(tmp, "audio")
        audio_dir.mkdir()
        (prompts / "cutlist.json").write_text(json.dumps([
            {"start": 0.0, "end": 4.0, "phase": "hook", "text": None,
             "asset": None, "filter": "white_flash", "effect": "strobe"},
        ]))
        (Path(tmp) / "config.json").write_text(json.dumps({
            "resolution": [360, 640], "fps": 15,
            "font": "LiberationSerif-Bold", "font_size": 28,
        }))
        for name, spec in (("soundtrack.wav", soundtrack_spec),
                           ("voiceover.wav", voiceover_spec)):
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", spec,
                 "-c:a", "pcm_s16le", str(audio_dir / name)],
                check=True, capture_output=True,
            )
        return tmp

    def _render(self, tmp):
        result = subprocess.run(
            [sys.executable, "main.py", "--project", tmp],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        return Path(tmp, "output", "master.mp4")


def _mean_volume(media, start, duration):
    result = subprocess.run(
        ["ffmpeg", "-ss", str(start), "-t", str(duration), "-i", media,
         "-vn", "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )
    for line in result.stderr.splitlines():
        if "mean_volume" in line:
            return float(line.split("mean_volume:")[1].strip().split()[0])
    raise AssertionError("no mean_volume in ffmpeg output")


def _integrated_loudness(media):
    result = subprocess.run(
        ["ffmpeg", "-i", media, "-vn", "-af", "ebur128", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )
    for line in result.stderr.splitlines():
        if line.strip().startswith("I:"):
            return float(line.split("I:")[1].strip().split()[0])
    raise AssertionError("no integrated loudness in ebur128 output")


def _wav_samples(path):
    import wave

    with wave.open(str(path), "rb") as wav:
        rate = wav.getframerate()
        data = wav.readframes(wav.getnframes())
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float64) / 32768.0
    return samples, rate


def _noise_floor_ratio(samples, rate):
    """Noise-floor band energy (800-1200Hz) over voice band energy (420-460Hz)."""
    fft = np.fft.rfft(samples)
    freqs = np.fft.rfftfreq(len(samples), 1.0 / rate)
    noise = np.sum(np.abs(fft[(freqs >= 800) & (freqs <= 1200)]) ** 2)
    signal = np.sum(np.abs(fft[(freqs >= 420) & (freqs <= 460)]) ** 2)
    return noise / signal


class EndToEndAudioTests(_AudioProjectMixin, unittest.TestCase):
    def test_ducking_follows_speech(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_project(
                tmp,
                soundtrack_spec="aevalsrc='0.5*sin(2*PI*200*t)':s=44100:d=4",
                voiceover_spec=(
                    "aevalsrc='if(between(t,1.5,2.5),0,0.1*sin(2*PI*440*t))'"
                    ":s=44100:d=4"),
            )
            render = self._render(tmp)
            gap = _mean_volume(str(render), 1.6, 0.8)
            voice = _mean_volume(str(render), 0.2, 1.0)
            self.assertGreater(gap, voice + 3.0,
                               f"gap {gap}dB not louder than voice {voice}dB")

    def test_output_meets_lufs_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_project(
                tmp,
                soundtrack_spec="aevalsrc='0.5*sin(2*PI*200*t)':s=44100:d=4",
                voiceover_spec="aevalsrc='0.5*sin(2*PI*440*t)':s=44100:d=4",
            )
            render = self._render(tmp)
            lufs = _integrated_loudness(str(render))
            self.assertGreater(lufs, -15.0, f"too quiet: {lufs} LUFS")
            self.assertLess(lufs, -13.0, f"too loud: {lufs} LUFS")

    def test_hum_reduced(self):
        # afftdn is a broadband denoiser, not a tone notch: the scenario's
        # "hum" is realized as low-level ambient hiss, and the assertion
        # measures the noise-floor band energy (800-1200Hz, signal-free)
        # relative to the voice band.
        with tempfile.TemporaryDirectory() as tmp:
            self._make_project(
                tmp,
                soundtrack_spec="aevalsrc='0.5*sin(2*PI*200*t)':s=44100:d=4",
                voiceover_spec=(
                    "aevalsrc='0.1*sin(2*PI*440*t)+0.01*(random(0)-0.5)'"
                    ":s=44100:d=4"),
            )
            render = self._render(tmp)
            out_wav = Path(tmp, "out.wav")
            subprocess.run(
                ["ffmpeg", "-y", "-ss", "0.3", "-t", "1.0", "-i", str(render),
                 "-vn", "-c:a", "pcm_s16le", str(out_wav)],
                check=True, capture_output=True,
            )
            out_samples, out_rate = _wav_samples(out_wav)
            out_ratio = _noise_floor_ratio(out_samples, out_rate)
            src_samples, src_rate = _wav_samples(Path(tmp, "audio", "voiceover.wav"))
            src_ratio = _noise_floor_ratio(src_samples, src_rate)
            self.assertLess(out_ratio, src_ratio * 0.7,
                            f"noise floor not reduced: {out_ratio} vs {src_ratio}")


if __name__ == "__main__":
    unittest.main()
