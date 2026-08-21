"""GPU probe and hardware profile tests (Spec G, CP-1).

Environment note: the standard test container has no GPU device access,
so every hardware dry-run fails and probe() degrades to libx264. That is
what the integration tests assert. GPU-positive behavior is covered by
injection tests below.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.compiler import compile_graph
from src.gpu import (
    CPU_PROFILE,
    HardwareProfile,
    PROFILE_TABLE,
    parse_encoders,
    probe,
    profile_for,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

CONFIG = {
    "resolution": [360, 640],
    "fps": 15,
    "font": "LiberationSerif-Bold",
    "font_size": 28,
    "stroke_width": 4,
    "stroke_color": "black",
    "text_color": "white",
}

SEGMENTS = [
    {"start": 0.0, "end": 2.0, "phase": "hook", "text": "THE PROBLEM",
     "asset": "raw_footage/clip.mp4", "filter": "grayscale", "effect": "ken_burns_slow"},
    {"start": 2.0, "end": 2.08, "phase": "drop_transition", "text": None,
     "asset": None, "filter": "white_flash", "effect": "strobe"},
    {"start": 2.08, "end": 4.0, "phase": "kinetic_cut", "text": "THE FIX",
     "asset": "raw_footage/photo.png", "filter": "high_contrast_green", "effect": "snap_zoom"},
]

AUDIO = None


class ParseEncoderTests(unittest.TestCase):
    def test_parses_encoder_names(self):
        output = (
            "Encoders:\n"
            " V....D av1_nvenc           NVIDIA NVENC av1 encoder\n"
            " V..... h264_qsv            H.264 QSV encoder\n"
            " V....D libx264             libx264 H.264 encoder\n"
        )
        self.assertEqual(parse_encoders(output), {"av1_nvenc", "h264_qsv", "libx264"})

    def test_ignores_non_encoder_lines(self):
        self.assertEqual(parse_encoders("Encoders:\n------\n"), set())


class ProbeSelectionTests(unittest.TestCase):
    def test_preference_order_picks_first_invokable(self):
        encoders = {"h264_qsv", "h264_vaapi", "h264_nvenc"}
        chosen = probe(
            encoder_list=encoders,
            dry_run_fn=lambda name, args: name == "h264_nvenc",
        )
        self.assertEqual(chosen.encoder, "h264_nvenc")

    def test_skips_present_but_not_invokable(self):
        encoders = {"h264_nvenc", "h264_vaapi"}
        chosen = probe(
            encoder_list=encoders,
            dry_run_fn=lambda name, args: name == "h264_vaapi",
        )
        self.assertEqual(chosen.encoder, "h264_vaapi")

    def test_all_unavailable_degrades_to_cpu(self):
        chosen = probe(
            encoder_list={"h264_nvenc"},
            dry_run_fn=lambda name, args: False,
        )
        self.assertEqual(chosen, CPU_PROFILE)

    def test_no_encoders_degrades_to_cpu(self):
        self.assertEqual(
            probe(encoder_list=set(), dry_run_fn=lambda name, args: True),
            CPU_PROFILE,
        )


class ProfileTableTests(unittest.TestCase):
    def test_vendor_chains(self):
        self.assertEqual(PROFILE_TABLE["h264_nvenc"].hw_chain, "format=nv12,hwupload_cuda")
        self.assertEqual(PROFILE_TABLE["h264_vaapi"].hw_chain, "format=nv12,hwupload")
        self.assertEqual(PROFILE_TABLE["h264_qsv"].extra_args[:2], ("-init_hw_device", "qsv=hw"))
        self.assertEqual(PROFILE_TABLE["h264_videotoolbox"].hw_chain, "format=nv12")

    def test_profile_for_unknown(self):
        self.assertIsNone(profile_for("h264_bogus"))

    def test_cpu_profile_shape(self):
        self.assertEqual(CPU_PROFILE.encoder, "libx264")
        self.assertEqual(CPU_PROFILE.hw_chain, "")


class CompilerProfileTests(unittest.TestCase):
    def test_cpu_profile_graph_unchanged(self):
        base = compile_graph(CONFIG, SEGMENTS, AUDIO, ".")
        cpu = compile_graph(CONFIG, SEGMENTS, AUDIO, ".", CPU_PROFILE)
        self.assertEqual(base.filter_complex, cpu.filter_complex)
        self.assertNotIn("hwupload", cpu.filter_complex)

    def test_nvenc_profile_adds_hw_chain(self):
        graph = compile_graph(CONFIG, SEGMENTS, AUDIO, ".", PROFILE_TABLE["h264_nvenc"])
        self.assertIn("format=nv12,hwupload_cuda", graph.filter_complex)
        self.assertEqual(graph.video_map, "[vout]")

    def test_hw_chain_appended_after_text(self):
        graph = compile_graph(CONFIG, SEGMENTS, AUDIO, ".",
                              PROFILE_TABLE["h264_nvenc"],
                              ass_path="output/subtitles.ass")
        self.assertIn("[vsub]format=nv12,hwupload_cuda[vout]", graph.filter_complex)


class IntegrationTests(unittest.TestCase):
    def test_probe_degrades_to_cpu_without_gpu_device(self):
        self.assertEqual(probe(), CPU_PROFILE)

    def test_forced_unavailable_encoder_aborts_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompts = Path(tmp, "prompts")
            prompts.mkdir(parents=True)
            (prompts / "cutlist.json").write_text(json.dumps([
                {"start": 0.0, "end": 1.0, "phase": "hook", "text": None,
                 "asset": None, "filter": "white_flash", "effect": "strobe"},
            ]))
            env = dict(os.environ, NOX_ENCODER="h264_nvenc")
            result = subprocess.run(
                [sys.executable, "main.py", "--project", tmp],
                cwd=str(REPO_ROOT), capture_output=True, text=True,
                env=env, timeout=120,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not invokable", result.stdout)


class CheckGpuCliTests(unittest.TestCase):
    def _check_gpu(self, env_extra=None):
        env = dict(os.environ)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, "main.py", "--check-gpu"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            env=env, timeout=120,
        )

    def test_check_gpu_reports_cpu_and_exits_zero(self):
        result = self._check_gpu()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["chosen"]["encoder"], "libx264")
        self.assertTrue(report["chosen"]["dry_run_ok"])
        self.assertIn("libx264", report["encoders"])

    def test_check_gpu_reports_broken_passthrough(self):
        result = self._check_gpu({"NOX_ENCODER": "h264_nvenc"})
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["chosen"]["encoder"], "h264_nvenc")
        self.assertFalse(report["chosen"]["dry_run_ok"])
        self.assertIn("not invokable", report["chosen"]["error"])


if __name__ == "__main__":
    unittest.main()
