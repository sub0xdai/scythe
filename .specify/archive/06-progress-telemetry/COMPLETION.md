# 06-progress-telemetry - Completion

- Date completed: 2026-06-01
- Final commit range: `7ae9a27` (single commit)

## Files changed

CP-1 (progress + telemetry):
- `src/telemetry.py` (new) - ProgressParser: throttled 1/sec emits, forced end-block emit, skip-until-speed-known (finite eta guarantee), out_time_us + HH:MM:SS parsing
- `main.py` - `-progress pipe:1` on the ffmpeg command, Popen line-streaming runner, `log()` routing (stderr in machine mode), `--json` flag + `NOX_JSON=1`, error/done JSON events
- `tests/test_telemetry.py` (new) - 8 tests (5 parser unit, 3 E2E)

## Notes

- Machine mode proven: stdout carries only JSON events (`progress` + `done`); all informational prints route to stderr.
- Fast renders (<1s wall) emit only the final 100% progress event due to the 1-second throttle; intermediate percents are proven by the parser unit tests.
- Live verification: `NOX_JSON=1` renders emit `{"type": "progress", ...}` then `{"type": "done"}`, exit 0; broken renders end with `{"type": "error"}`.
- The NOX_JSON podman gotcha (env must pass via `-e`) applies as with NOX_ENCODER.
- Living spec created: `.specify/specs/observability/spec.md` (3 requirements, 4 scenarios).
