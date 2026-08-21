# 05-audio-mastering - Implementation Plan

## Delta Summary

Greenfield change. Touches living domain `audio` (does not exist yet, created at archive): 4 ADDED requirements, 5 scenarios.

- R1 Dynamic sidechain ducking (1 scenario)
- R2 Loudness normalization (1 scenario)
- R3 Voice cleanup (2 scenarios)
- R4 Audio processing in the graph (1 scenario)

## Current State Summary

`_audio_chains` in `src/compiler/graph.py` mixes with a static `volume=0.3` on the soundtrack plus `amix=inputs=2:normalize=0`, then `asetpts`. There is no loudness target, no sidechain, no cleanup. main.py `DEFAULTS` has no audio-mastering keys; `load_config` flat-merges, so new keys must be flat scalars to inherit the merge behavior. The Spec B compiler test `test_ducking_nodes` asserts the old `volume=0.3` node and must be updated to the new chain (Spec E removes static ducking by design).

Container ffmpeg 7.1.4 has `sidechaincompress`, `loudnorm`, `afftdn`, `agate`, and `ebur128` (verified in the Spec B filter scan). The fixture soundtrack/voiceover are both constant sines; the ducking and hum scenarios need crafted test signals in their own temp project (fixture stays unchanged).

## Checkpoints

### CP-1: Audio mastering chain in the compiler ✅

- **Touches**: `src/compiler/graph.py`, `main.py`, `tests/test_compiler.py`, `tests/test_audio.py` (new)
- **Tasks**:
  1. Add flat config keys to main.py `DEFAULTS`: `lufs_target: -14`, `voice_cleanup: True`, `duck_threshold: 0.05`, `duck_ratio: 8`. Flat keys so the existing `config.update` merge works untouched.
  2. Rewrite `_audio_chains` to take `config` instead of just `audio_offset`. Both-files case: `[st]atrim+asetpts[st_t]; [vo]cleanup,atrim+asetpts[vo0]; [vo0]asplit=2[vo_sc][vo_mix]; [st_t][vo_sc]sidechaincompress=threshold={duck_threshold}:ratio={duck_ratio}:attack=20:release=500:makeup=1[st_ducked]; [st_ducked][vo_mix]amix=inputs=2:normalize=0:duration=first[aout_raw]; [aout_raw]loudnorm=I={lufs_target}:TP=-1.5:LRA=11,aresample=48000[aout]`. Cleanup chain (when `voice_cleanup`): `afftdn=nf=-40:nt=w,agate=threshold=0.02:attack=20:release=250`; when disabled, no afftdn/agate nodes. Single-file case: `atrim+asetpts,loudnorm=I=...:TP=-1.5:LRA=11,aresample=48000`. No audio: unchanged.
  3. Update `tests/test_compiler.py` `test_ducking_nodes` to assert `sidechaincompress`, `loudnorm`, and `amix=inputs=2:normalize=0` instead of `volume=0.3`.
  4. Create `tests/test_audio.py` structural tests: both-files graph contains `sidechaincompress` and `loudnorm` (R4 S1); `voice_cleanup: False` graph contains neither `afftdn` nor `agate` (R3 S2); single-file graph contains `loudnorm`.
- **Verification**: `podman run --rm --entrypoint python -v "$(pwd):/app:Z" kinetic-renderer -m unittest discover -s tests -v` prints `OK` including `test_audio`.
- **Commit message**: `feat: sidechain ducking, loudnorm, and voice cleanup in the audio chain`
- Completed 2026-06-01 by /skill:vox build.

### CP-2: End-to-end audio verification

- **Touches**: `tests/test_audio.py`
- **Tasks**:
  1. `test_ducking_follows_speech` (R1 S1): temp project with `soundtrack.wav` = 200Hz constant tone at -6dBFS and `voiceover.wav` = 440Hz at -20dBFS with a silent gap (tone 0-1.5s, silence 1.5-2.5s, tone 2.5-4s). Render via main.py. Extract output audio, measure `mean_volume` with `volumedetect` in the silent-gap window vs the active-voice window. Assert gap-window volume exceeds voice-window volume by at least 3dB. The voice is quiet enough that the gap window (full music) clearly beats the voice window (ducked music + quiet voice) even after loudnorm's single-pass gain.
  2. `test_output_meets_lufs_target` (R2 S1): render the fixture, extract audio, measure integrated loudness with `ebur128` (`I:` summary line). Assert it lands in [target-1, target+1] = [-15, -13].
  3. `test_hum_reduced` (R3 S1): temp project with voiceover = 440Hz tone plus a stationary 60Hz hum at -45dBFS; soundtrack constant tone. Render, extract the voice-active window from output and from the source wav, compare 50-70Hz band energy via numpy FFT. Assert the output band energy is below the source band energy. If `afftdn=nf=-40` does not suppress the hum, tune `nf`/`nt` in this checkpoint (the chain data in gpu-style is a constant, not a pipeline change).
- **Verification**: `podman run --rm --entrypoint python -v "$(pwd):/app:Z" kinetic-renderer -m unittest discover -s tests -v` prints `OK` including the three E2E tests; `tests/verify.sh` exits 0 (ALL GATES PASSED).
- **Commit message**: `test: end-to-end audio mastering verification`

## Risks & Open Questions

1. **loudnorm single-pass accuracy.** Dynamic-mode loudnorm is approximate; with flat sine content (LRA near 0) it lands close to target. The ±1 LUFS tolerance may need verification in build. If it flunks on the constant tones, the fallback is two-pass loudnorm (measure then linear-apply), which is more code; default is single-pass.
2. **loudnorm dynamic gain vs the ducking measurement.** Dynamic loudnorm applies time-varying gain that could partially flatten the ducking difference. The test uses a 10dB+ ducking delta with a 3dB assertion margin; if loudnorm flattens it below 3dB, the test signals get adjusted (louder music bed) rather than the chain changing.
3. **afftdn hum suppression is the flakiest test.** A -45dBFS stationary tone sits below the configured -40dB noise floor and should be suppressed. If it is not, tune `nf` in build. The scenario stays as written; the test signal design is adjustable.
4. **agate on the voiceover** gates room silence; on a synthetic gap it may gate the gap (fine) or clip attack edges (cosmetic). Threshold 0.02 with 20ms attack/release is conservative.
5. **Behavior change vs Spec B.** The static 30% duck is removed (spec-mandated). The old `test_ducking_nodes` assertion changes in CP-1. Renders without voiceover keep loudnorm, so single-track output level shifts to -14 LUFS - intended.

Plan ready: 2 checkpoints, ~4 hours total. Run `/skill:vox build 05-audio-mastering` to start CP-1.
