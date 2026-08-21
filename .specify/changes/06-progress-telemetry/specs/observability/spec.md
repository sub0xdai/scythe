# observability - Delta Spec

## ADDED Requirements

### Requirement: Progress stream

The engine MUST invoke ffmpeg with `-progress pipe:1` and parse `out_time`, `frame`, and `speed`. Human-readable progress MUST print to stderr at least once per second, showing percent, frame, speed, and ETA, ending with a final 100 percent line.

#### Scenario: Monotonic progress

- GIVEN the fixture render
- WHEN the render runs
- THEN percent values increase monotonically from 0 to 100 and the final line reports 100 percent

### Requirement: JSON telemetry

With `--json` or `NOX_JSON=1`, stdout MUST emit newline-delimited JSON events of the form `{type, percent, frame, out_time, speed, eta_seconds}` with type in progress, done, error. In machine mode, JSON events MUST be the only stdout content. Human progress stays on stderr.

#### Scenario: Parseable stream

- GIVEN a render with `--json`
- WHEN the render runs
- THEN every stdout line parses as JSON and the final event has type done

#### Scenario: Error event

- GIVEN a render that fails mid-flight
- WHEN the render runs with `--json`
- THEN the stream ends with an error event carrying a message

### Requirement: ETA calculation

ETA MUST be computed from the cutlist span, elapsed time, and speed: `eta = (cutlist_duration - out_time) / speed`. The cutlist span is the sum of segment durations.

#### Scenario: ETA present

- GIVEN a fixture with a known cutlist duration
- WHEN progress events are observed
- THEN every progress event carries a finite eta_seconds value
