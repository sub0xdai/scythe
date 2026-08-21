# 02-ffmpeg-engine - Completion

- Date completed: 2026-06-01
- Final commit range: `2387529..8ae932f`

## Files changed

CP-1 (filtergraph compiler):
- `src/compiler/__init__.py` (new) - public API: compile_graph, CompiledGraph, AudioSpec
- `src/compiler/video.py` (new) - filter chain builders (hue, negate, lutrgb threshold crush, rgbashift, seeded noise) + zoompan chains (ken_burns 8%/15% linear, snap_zoom midpoint step)
- `src/compiler/graph.py` (new) - pure compile_graph: input dedup via split, looped image inputs, per-segment trim/setpts/fps/cover-crop chains, concat, drawtext overlays with enable windows, amix normalize=0 ducking, audio_offset, trim=duration clamp
- `tests/test_compiler.py` (new) - 17 structural tests

CP-2 (single-pass integration):
- `main.py` - MoviePy cutlist path replaced with compile + one ffmpeg run; deleted _load_asset, apply_filter, apply_effect, _contrast_crush, _chromatic_aberration, _film_grain, _mix_audio; moviepy/PIL/numpy imports lazy in beat-detect mode; _detect_audio -> AudioSpec
- `tests/test_render.py` (new) - import hygiene, output contract (h264 360x640@15, aac, 4.0s), byte-identical determinism
- `tests/verify.sh` - JSON stream assertions added

## Notes

- Live render: `tests/verify.sh` -> ALL GATES PASSED, Render OK: 4.000000s (h264 360x640@15, aac), 35 tests OK.
- Determinism verified byte-identical across re-renders (seeded noise, fixed x264 threads/crf).
- Living spec created: `.specify/specs/rendering/spec.md` (7 requirements, 11 scenarios).
- Container diet reconciled: moviepy/librosa/pillow/numpy stay installed for beat-detect mode; the cutlist path no longer imports them (import hygiene test enforces this).
