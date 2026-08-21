# 05-audio-mastering - Proposal

## Problem

Audio is a static 30 percent duck (main.py line 252) with no dynamics, no loudness target, and no cleanup. improve.md section 4 demands dynamic sidechain ducking, R128 loudness normalization, and voice cleanup.

## User Stories

- As a user, I want music to duck smoothly only while I am speaking, not a fixed 30 percent for the whole track.
- As a user, I want output at about -14 LUFS so it matches streaming platforms.
- As a user, I want hum and room noise stripped from my voiceover.

## Risks

- loudnorm has two-pass and dynamic modes. Dynamic mode is simpler and adequate; verify with ebur128 and accept plus or minus 1 LUFS tolerance in tests.
- sidechaincompress threshold depends on voiceover loudness. Duck depth and threshold must be theme values, not hardcoded.
- All processing must live in the graph. No post-hoc Python audio processing may sneak back in.
