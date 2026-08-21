# 07-gpu-acceleration - Proposal

## Problem

Renders are CPU-only libx264. improve.md section 1 demands auto-detection of GPU encoding and decoding (NVENC, VideoToolbox, QuickSync, VAAPI). The filtergraph compiler from Spec B must accept a hardware profile from day one, or retrofitting upload and download nodes into a CPU-only graph later is a rewrite.

## User Stories

- As a user on a GPU machine, I want renders to use NVENC, VAAPI, QSV, or VideoToolbox automatically.
- As a user on CPU-only hardware, I want the exact current behavior, untouched.
- As an operator, I want a `--check-gpu` command that reports capability, so I can debug container GPU passthrough.

## Risks

- Container GPU access is runtime infrastructure, not code. podman needs `--gpus all` for NVIDIA and `/dev/dri` for VAAPI and QSV. render.sh must expose flags, and `--check-gpu` must fail loudly when a claimed encoder cannot be invoked.
- Vendor chains differ. nvenc wants scale_cuda and nv12; vaapi wants scale_vaapi. The hardware profile must carry the chain, not just the encoder name.
- CI cannot assume a GPU. Automated tests run the CPU fallback path; GPU paths are verified by `--check-gpu` on GPU machines only.
