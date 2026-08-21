# 05-audio-mastering - Completion

- Date completed: 2026-06-01
- Final commit range: `d7604e3..886ef38` (2 commits, one per CP)

## Files changed

CP-1 (audio mastering chain):
- `src/compiler/graph.py` - `_audio_chains` rewritten: voice cleanup (afftdn nf=-40:nt=w + agate), asplit, sidechaincompress (configurable threshold/ratio), amix normalize=0, loudnorm (configurable LUFS target) + aresample; single-track gets loudnorm too; static volume=0.3 removed
- `main.py` - DEFAULTS: lufs_target -14, voice_cleanup True, duck_threshold 0.02, duck_ratio 2
- `tests/test_audio.py` (new) - 7 structural chain tests
- `tests/test_compiler.py` - 2 stale Spec B assertions updated

CP-2 (E2E verification):
- `tests/test_audio.py` - 3 E2E tests: ducking follows speech (silent-gap windows), integrated loudness in [-15,-13] via ebur128, ambient noise-floor suppression via FFT band energy
- `tests/test_render.py` - import hygiene test moved to fresh subprocess (was order-dependent once test_audio imported numpy)

## Notes

- Defaults tuned during build: duck_threshold 0.02 / duck_ratio 2 (threshold 0.05/ratio 8 gave 0.75dB ducking on a -20dB voice; ratio 2 gives ~7dB - real musical ducking).
- ffmpeg `sine` filter outputs at -18dBFS peak, not 0dB; test signals use `aevalsrc` for exact amplitude control.
- afftdn is a broadband denoiser, not a tone notch (pure 60Hz tone reduced only 11%). R3 S1 verified as ambient noise-floor suppression (53% reduction of the 800-1200Hz band) - the chain keeps afftdn + agate per spec.
- Dynamic loudnorm's time-varying gain can partially flatten ducking; the E2E ducking test uses signals with a 10dB+ delta so the 3dB assertion margin survives.
- Living spec created: `.specify/specs/audio/spec.md` (4 requirements, 5 scenarios).
