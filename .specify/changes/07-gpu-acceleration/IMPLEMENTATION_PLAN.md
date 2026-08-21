# 07-gpu-acceleration - Implementation Plan

## Delta Summary

Greenfield change. Touches living domain `hardware-acceleration` (does not exist yet, created at archive): 5 ADDED requirements, 11 scenarios.

- R1 GPU capability probe (2 scenarios)
- R2 Encoder decision (3 scenarios)
- R3 Hardware-aware graph (2 scenarios)
- R4 --check-gpu CLI (2 scenarios)
- R5 Container and runner support (2 scenarios)

## Current State Summary

main.py hardcodes the encoder: `-c:v libx264` (single-pass ffmpeg from Spec B). The compiler (`src/compiler/graph.py`) emits a pure CPU graph with no hardware concept; `compile_graph(config, segments, audio, project_dir)` has no profile parameter. There is no `--check-gpu` flag, and render.sh runs podman with no GPU passthrough.

The container ffmpeg 7.1.4 has `h264_nvenc`, `h264_qsv`, and `h264_vaapi` compiled in, plus cuda, vaapi, qsv, vdpau, drm, opencl, vulkan hwaccels and h264_cuvid/h264_qsv decoders. Compiled presence does not mean invokable: this host has no NVIDIA GPU (nvenc dry-run will fail) but does expose `/dev/dri/renderD128`, so VAAPI and QSV become invokable only when podman passes the device through.

The design decision that makes probe selection self-healing: selection is not "first encoder present in -encoders" but "first encoder that passes a 0.2s dry-run encode to null output". No device passthrough -> every hw dry-run fails -> libx264, exactly the current behavior. Device present -> the matching hw encoder is selected. Forced selection (`NOX_ENCODER`) that fails its dry-run aborts with a clear error. A dry-run is one subprocess of ~0.3s per render, pre-flight only.

## Checkpoints

### CP-1: Probe, hardware profile, and hardware-aware graph ✅

- **Touches**: `src/gpu.py` (new), `src/compiler/graph.py`, `main.py`, `tests/test_gpu.py` (new), `tests/test_compiler.py`
- **Tasks**:
  1. Create `src/gpu.py` with a frozen `HardwareProfile(encoder, hw_chain, extra_args)` tagged by encoder name, a pure `parse_encoders(output) -> set[str]` for `ffmpeg -hide_banner -encoders` output, and `probe() -> HardwareProfile`. Preference order: h264_nvenc, h264_qsv, h264_vaapi, h264_videotoolbox. Each candidate is selected only if it appears in -encoders AND its dry-run (`ffmpeg -f lavfi -i color=64x64 -c:v <enc> -f null -` with the profile extra_args) exits 0. All fail -> `HardwareProfile("libx264", "", ())`.
  2. Vendor chains: nvenc -> `hw_chain="format=nv12,hwupload_cuda"`, extra_args `()`; qsv -> `hw_chain="format=nv12,hwupload=extra_hw_frames=64"`, extra_args `("-init_hw_device","qsv=hw","-filter_hw_device","hw")`; vaapi -> `hw_chain="format=nv12,hwupload"`, extra_args `("-init_hw_device","vaapi=va:/dev/dri/renderD128","-filter_hw_device","va")`; videotoolbox -> `hw_chain="format=nv12"`, extra_args `()`. HW decode stays software; the upload-at-end pattern needs no decode changes.
  3. Extend `compile_graph` with a `profile=None` parameter (None = CPU, existing behavior byte-identical). When a profile with a non-empty hw_chain is given, append `{video_map}{hw_chain}[vout]` after the drawtext chains and return `[vout]` as video_map.
  4. In `generate_from_cutlist`: resolve the profile via env overrides first (`NOX_GPU=off` forces CPU; `NOX_ENCODER=<name>` forces a named encoder and aborts with a clear error when its dry-run fails), else `probe()`. Pass the profile to compile_graph, prepend `profile.extra_args` to the ffmpeg cmd, use `-c:v profile.encoder`, and print `Encoder: <name>`.
- **Verification**: `podman run --rm --entrypoint python -v "$(pwd):/app:Z" kinetic-renderer -m unittest discover -s tests -v` prints `OK` including `test_gpu`; and a direct probe on this machine (no GPU flags) reports libx264.
- **Commit message**: `feat: auto-detect GPU encoders with dry-run validation`
- Completed 2026-06-01 by /skill:vox build.

### CP-2: --check-gpu CLI ✅

- **Touches**: `main.py`, `tests/test_gpu.py`
- **Tasks**:
  1. Add `--check-gpu` to the CLI. Without --project, run the full probe and print a JSON report: available encoders, decoders, hwaccels (from ffmpeg capability scans), and `chosen` with encoder, invokable, and dry_run_ok. Honor `NOX_GPU` and `NOX_ENCODER` so it reflects exactly what a render would select. Exit 0 when the chosen encoder's dry-run succeeded, non-zero otherwise.
  2. Tests: `--check-gpu` on the CPU container exits 0 and JSON `chosen.encoder == "libx264"`; `NOX_ENCODER=h264_nvenc --check-gpu` on this host (compiled but no GPU) exits non-zero and JSON reports dry_run_ok false.
- **Verification**: `podman run --rm --entrypoint python -v "$(pwd):/app:Z" kinetic-renderer main.py --check-gpu` prints parseable JSON with libx264 chosen and exits 0; `NOX_ENCODER=h264_nvenc podman run ... main.py --check-gpu` exits non-zero.
- **Commit message**: `feat: add --check-gpu capability report`
- Completed 2026-06-01 by /skill:vox build.

### CP-3: Container runner passthrough and docs

- **Touches**: `render.sh`, `tests/verify.sh`, `README.md`
- **Tasks**:
  1. Add `--gpu nvidia|vaapi|qsv` to render.sh mapping to podman flags: nvidia -> `--gpus all`; vaapi and qsv -> `--device /dev/dri/renderD128`. Unknown values exit 1. Add `NOX_DRY_RUN=1` mode that prints the podman command without executing (testable in CI).
  2. Add a `--check-gpu` smoke step to tests/verify.sh: run it in the container, assert exit 0 and `libx264` in the JSON output.
  3. Document the three GPU setups in README (nvidia runtime, VAAPI device, QSV device) plus the `NOX_GPU` / `NOX_ENCODER` overrides and the renderD128 path assumption.
- **Verification**: `NOX_DRY_RUN=1 ./render.sh tests/fixtures/synthetic_project --gpu vaapi` prints a podman command containing `--device /dev/dri/renderD128`; `tests/verify.sh` exits 0 (ALL GATES PASSED).
- **Commit message**: `feat: GPU passthrough flags in render.sh and docs`

## Risks & Open Questions

1. **VAAPI/QSV chains are best-effort data.** The nvenc upload-at-end pattern is battle-tested; qsv and vaapi chains follow the documented `-init_hw_device` + `-filter_hw_device` + `hwupload` pattern but are not testable here without a real GPU on both. The safety net is `--check-gpu`: a broken chain fails its dry-run loudly before any render. If a vendor chain proves wrong on real hardware, it is a data fix in `src/gpu.py`, not a pipeline change.
2. **Dry-run latency.** One ~0.3s subprocess per render pre-flight. Acceptable; it is what makes selection self-healing.
3. **GPU renders are not guaranteed byte-deterministic.** The rendering spec's determinism requirement (R5) is verified on the CPU path in CI. NVENC is deterministic in practice but this is not guaranteed; note it and move on.
4. **/dev/dri/renderD128 is hardcoded** in the vaapi/qsv profiles and the render.sh device flag. Hosts with a different render node will fail `--check-gpu` and must force via `NOX_ENCODER` or edit the profile. Flagged in README.
5. **HW decode is out of scope.** The profile reports decoder availability; the render path keeps software decode + upload-at-end. The delta spec's scenarios never exercise hw decode in the graph.
6. **QSV on this host is likely dead** (no Intel GPU); it will fall through to CPU or vaapi. No action needed; the decision order handles it.

Plan ready: 3 checkpoints, ~4.5 hours total. Run `/skill:vox build 07-gpu-acceleration` to start CP-1.
