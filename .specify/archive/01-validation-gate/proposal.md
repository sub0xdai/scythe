# 01-validation-gate - Proposal

## Problem

main.py loads `prompts/cutlist.json` raw with `json.load` (line 287) and never validates it, even though `schemas/cutlist.schema.json` already defines the segment contract, including no-gaps, filter adjacency, white_flash constraints, and uppercase text rules.

Missing assets degrade to silent black frames mid-render instead of failing up front.

No test fixture exists, so no spec can be verified end to end. Every later spec (B through G) needs a stable project to render.

## User Stories

- As a user, I want broken cutlists to fail with a precise list of violations before a long render, so I do not waste time on bad input.
- As a user, I want missing and corrupt assets reported up front, so I do not discover them mid-render.
- As a developer, I want a synthetic fixture project plus a verification command, so later specs have a harness.

## Risks

- The schema's cross-item rules (no-gaps, filter adjacency) cannot be expressed in pure JSON Schema. jsonschema handles per-segment shape; continuity and adjacency need a small code pass. Both must ship in this spec.
- The fixture needs real media. Committing binaries is noise; instead the fixture generator produces assets with ffmpeg (testsrc video, sine audio), which is deterministic and reproducible.
- The fixture must be small enough for fast CI but must exercise ken_burns, white_flash, text, and audio so later specs can reuse it.
