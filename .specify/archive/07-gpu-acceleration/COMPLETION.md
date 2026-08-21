# 07-gpu-acceleration - Completion

- Date completed: 2026-06-01
- Final commit range: `7586d28..c44d9fe` (3 commits, one per CP)

## Files changed

CP-1 (probe + hardware-aware graph):
- `src/gpu.py` (new) - HardwareProfile dataclass, parse_encoders, dry-run invokability probe with preference order (nvenc, qsv, vaapi, videotoolbox), vendor profile table
- `src/compiler/graph.py` - `profile` param; non-empty hw_chain appended pre-encode (`[vtN]format=nv12,hwupload_cuda[vout]`); CPU/None unchanged
- `main.py` - `_select_profile` with NOX_GPU=off / NOX_ENCODER overrides; encoder from profile in ffmpeg cmd
- `tests/test_gpu.py` (new) - parse, selection injection, degrade-to-CPU, compiler hw insertion, live probe, forced-encoder abort

CP-2 (--check-gpu):
- `main.py` - `_resolve_profile` returning (profile, error); `check_gpu()` JSON report (encoders/decoders/hwaccels/chosen); `--check-gpu` flag
- `tests/test_gpu.py` - 2 CLI tests (CPU exit 0, forced broken exit 1)

CP-3 (runner + docs):
- `render.sh` - `--gpu nvidia|vaapi|qsv` -> podman flags; NOX_DRY_RUN=1 print mode
- `tests/verify.sh` - 5/5 --check-gpu smoke step
- `README.md` - GPU Acceleration section

## Notes

- Selection is dry-run based: 0.2s null encode per candidate. No device access -> libx264 fallback, byte-identical to pre-Spec-G behavior.
- Verified on this machine: probe -> libx264; NOX_ENCODER=h264_nvenc --check-gpu -> exit 1 with dry_run_ok false (compiled but no GPU).
- VAAPI/QSV chains are documented-pattern best-effort data, validated per-machine by --check-gpu.
- Living spec created: `.specify/specs/hardware-acceleration/spec.md` (5 requirements, 11 scenarios).
- The NOX_ENCODER podman gotcha: env vars must pass via `-e`, not on the podman CLI.
