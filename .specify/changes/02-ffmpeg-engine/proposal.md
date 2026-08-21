# 02-ffmpeg-engine - Proposal

## Problem

The render loop is per-frame Python. `_contrast_crush`, `_chromatic_aberration`, and `_film_grain` touch every pixel of every frame through NumPy. MoviePy, Pillow, and NumPy ride in the container for this work. improve.md section 1 demands a compiled, single-pass libavfilter pipeline with hardware encoding support.

## User Stories

- As a user, I want renders to run as one ffmpeg pass instead of a Python pixel loop, so renders are faster and the container is lighter.
- As a user, I want every existing filter and effect to behave the same as today, so nothing regresses.
- As a developer, I want a filtergraph compiler module that takes a hardware profile, so Spec G hooks in without restructuring.

## Risks

- Visual parity is hard to prove with pixel equality. Verify structurally: the emitted `filter_complex` string contains the expected nodes, and the fixture render (Spec A) completes with correct duration, resolution, and fps.
- zoompan interacts badly with fps; ken_burns parity needs frame-accurate tests.
- Dropping MoviePy changes the container and the beat-detect mode. Beat-detect mode (librosa) is legacy; this spec keeps it working but does not convert it.
- word_flash is text-domain. Implementing it in the graph here would duplicate Spec D. It stays a passthrough in this spec.
