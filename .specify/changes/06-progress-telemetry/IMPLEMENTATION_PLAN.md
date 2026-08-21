# 06-progress-telemetry - Implementation Plan

## Delta Summary

Greenfield change. Touches living domain `observability` (does not exist yet, created at archive): 3 ADDED requirements, 4 scenarios.

- R1 Progress stream (1 scenario)
- R2 JSON telemetry (2 scenarios)
- R3 ETA calculation (1 scenario)

## Current State Summary

main.py invokes ffmpeg with `subprocess.run(cmd, capture_output=True, text=True)`, waits silently, then prints "Done". Every informational print (project info, audio detection, probe, ass path, the "Running:" command line) goes to stdout. There is no `-progress` flag, no machine-readable output, and no way for a dashboard to consume render state.

`-progress pipe:1` makes ffmpeg write `key=value` blocks (frame, out_time_ms, speed, progress=continue/end) to stdout. The design: run ffmpeg with Popen, stream stdout line-by-line into a parser, route emitted events to a sink (JSON lines on stdout in machine mode, a stderr progress line in human mode). The parser throttles to one event per second and forces a final event on `progress=end`. Events are skipped until speed is available so every emitted progress event carries a finite eta.

Machine mode (`--json` or `NOX_JSON=1`) requires JSON events to be the ONLY stdout content, so every informational print in main.py routes through a `log()` helper that writes stderr in machine mode. Pre-flight and ffmpeg failures emit `{type: error}` events on stdout and exit non-zero.

## Checkpoints

### CP-1: Progress parser, telemetry events, and machine mode ✅

- **Touches**: `src/telemetry.py` (new), `main.py`, `tests/test_telemetry.py` (new)
- **Tasks**:
  1. Create `src/telemetry.py` with a `ProgressParser(duration, emit, min_interval=1.0)` that ingests ffmpeg progress lines (`key=value`, block-terminated by `progress=continue|end`) and emits dict events: `{type, percent, frame, out_time, speed, eta_seconds}`. percent = clamp(out_time/duration*100); eta = (duration - out_time)/speed. Throttle to one emit per second; force emit on the end block; skip emission while speed is absent (guarantees finite eta on every emitted progress event). out_time parsed from `out_time_us` (microseconds) or the `out_time` HH:MM:SS.ffffff field.
  2. main.py: add `-progress pipe:1` to the ffmpeg command; run via `subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, text=True)`, feed stdout lines to the parser, read stderr after EOF. Sinks: machine mode emits `json.dumps(event)` to stdout; human mode prints a `Progress: X% frame=N speed=Yx eta=Zs` line to stderr. On returncode != 0, emit `{type: error, message: <stderr tail>}` (machine) or the current failure print (human) and exit. On success, emit `{type: done}` (machine) after the final progress event.
  3. Add `--json` CLI flag (argparse). Machine mode = `--json` or `NOX_JSON=1`. Add a `log()` helper in main.py that routes informational prints to stderr in machine mode; replace every direct print in the render path with it. Validation failures emit `{type: error, message: ...}` on stdout in machine mode.
  4. Tests (`tests/test_telemetry.py`): parser unit tests with canned progress blocks (percent/eta computation, throttle, forced end emit, speed-absent skip); machine-mode E2E on the fixture (every stdout line parses as JSON, first event type progress, last type done, at least one progress event with percent strictly inside (0, 100), every progress event has finite eta_seconds); human-mode E2E (stderr contains progress lines with percents that are non-decreasing and end at 100); error-event E2E (a project whose asset is a valid audio-only file that passes pre-flight probing but cannot feed the video graph -> ffmpeg fails -> stdout ends with `{type: error}` and exit non-zero).
- **Verification**: `podman run --rm --entrypoint python -v "$(pwd):/app:Z" kinetic-renderer -m unittest discover -s tests -v` prints `OK` including `test_telemetry`; `tests/verify.sh` exits 0 (ALL GATES PASSED).
- **Commit message**: `feat: ffmpeg progress telemetry with JSON events`
- Completed 2026-06-01 by /skill:vox build.

## Risks & Open Questions

1. **ffmpeg progress is bursty.** The parser receives blocks in clumps; the 1-second throttle absorbs that. The forced end-block emit guarantees the final 100 percent line.
2. **speed can be absent or zero early in the render.** Skipping emission until speed is available satisfies the delta's "every progress event carries a finite eta_seconds" strictly. The fixture renders fast enough that speed appears within the first block.
3. **stderr pipe reads after stdout EOF.** ffmpeg's own logging is a handful of lines; the stderr pipe cannot fill before stdout completes for normal renders. Error paths read stderr after exit.
4. **Error-event test uses an audio-only file as a video asset.** It passes the ffprobe-based pre-flight (valid media stream) and fails in the video filtergraph, exercising the real error-event path without crafted mid-render failures.
5. **Machine mode changes stdout content.** The existing "Running: ..." and "Done" prints move to stderr in machine mode; human-mode stdout is unchanged. The render contract tests (which assert "-filter_complex" in stdout) run in human mode and stay green.

Plan ready: 1 checkpoint, ~2.5 hours total. Run `/skill:vox build 06-progress-telemetry` to start CP-1.
