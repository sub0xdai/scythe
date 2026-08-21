# 06-progress-telemetry - Proposal

## Problem

main.py prints a few lines, then goes silent for minutes while write_videofile runs. improve.md section 5 wants machine-readable progress: percent complete, current frame, and estimated time remaining.

## User Stories

- As a user, I want a progress line with percent, frame, speed, and ETA during renders.
- As a tool integrator, I want a JSON event stream on stdout so dashboards can consume it.

## Risks

- `-progress` writes ffmpeg progress to a file descriptor. The parent must interleave its own output without corrupting the JSON stream. Design: JSON events are the only stdout content in machine mode; human progress goes to stderr.
- ETA needs total duration up front. The cutlist span provides it. ETA is elapsed plus remaining divided by speed.
- ffmpeg progress emits in bursts. The parser must tolerate irregular event cadence and emit at most one summary per second.
