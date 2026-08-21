# 04-text-layout - Implementation Plan

## Delta Summary

Greenfield change. Touches living domain `typography` (does not exist yet, created at archive): 5 ADDED requirements, 7 scenarios.

- R1 .ass subtitle pipeline (2 scenarios)
- R2 Bounding-box wrapping (1 scenario)
- R3 Platform safe zones (2 scenarios)
- R4 Per-word kinetic timing (1 scenario)
- R5 Lower-thirds (1 scenario)

## Current State Summary

Text is burned via drawtext overlays in `src/compiler/graph.py`: a chain of drawtext nodes after concat, each with `enable='between(t,start,end)'`, centered, styled from config (font, size, color, stroke). No wrapping, no safe zones, no per-word timing, no lower-thirds. `word_flash` is an identity effect (Spec B deferred it here). The compiler is pure (no file writes).

Container ffmpeg 7.1.4 has the `subtitles` and `ass` filters (libass, verified), and fontconfig resolves LiberationSerif-Bold. So the .ass burn path is `subtitles=filename=...` after the concat/fps chain. The validation schema (`schemas/cutlist.schema.json`) has no `lower_third` field; JSON Schema allows additional properties by default, so adding it is optional but explicit.

The .ass coordinate space is set by PlayResX/PlayResY (canvas size), which makes safe-zone positioning and wrapping directly computable in the generator.

## Checkpoints

### CP-1: .ass generator and subtitles burn ✅

- **Touches**: `src/compiler/text.py` (new), `src/compiler/graph.py`, `main.py`, `schemas/cutlist.schema.json`, `tests/test_text.py` (new), `tests/test_compiler.py`, `tests/test_gpu.py`
- **Tasks**:
  1. Create `src/compiler/text.py` with a pure `build_ass(segments, config) -> str | None` (None when no text/lower_third segments). Emits a v4.00+ script with PlayResX/Y = canvas, three styles (Default, Karaoke with a distinct SecondaryColour for \k highlights, LowerThird), and Dialogue events at absolute times. Timestamps as H:MM:SS.CC. Deterministic.
  2. Wrapping (R2): config key `text_box_width` (fraction of canvas width, default 0.8). Greedy word-wrap using estimated char width `font_size * 0.55`; lines joined with `\N`. No line's estimate may exceed the box.
  3. Safe zones (R3): config keys `safe_zone_top` (0.12) and `safe_zone_bottom` (0.25), the vertical 9:16 defaults. Horizontal orientation uses internal constants 0.08/0.15 with a `ponytail:` comment (vertical is the product's primary orientation). Alignment=2 (bottom-center), MarginV = safe_zone_bottom * height, so the caption bottom sits at (1 - safe_zone_bottom) * height. Margins L/R derived from text_box_width.
  4. word_flash (R4): for a segment with `effect == "word_flash"`, wrap each word with `{\kD}` tags where D = segment_duration_cs / word_count per word. Sum of \k durations equals the segment duration.
  5. Lower-thirds (R5): a segment carrying `lower_third: {title, subtitle}` emits a two-line event (title on line 1, subtitle on line 2 with `\N`), LowerThird style, same safe-zone MarginV, `\fad(150,150)` entrance at segment start.
  6. Compiler: `compile_graph(..., ass_path=None)`. When ass_path is given, replace the drawtext chain loop with one `[vfps]subtitles=filename={ass_path}[vsub]` node; video_map becomes `[vsub]` (or `[vout]` after a hw chain). No text segments -> no subtitles node, video_map `[vfps]` (byte-identical to current for textless renders).
  7. main.py: `build_ass` -> write `output/subtitles.ass` when non-None; pass the path to compile_graph. Add the four config keys to DEFAULTS.
  8. Schema: add an optional `lower_third` object property (title, subtitle strings) to `schemas/cutlist.schema.json`.
  9. Update tests: `test_compiler.test_drawtext_carries_text` -> asserts `subtitles=filename=` and no drawtext; `test_gpu.test_hw_chain_appended_after_text` -> the hw chain now appends after `[vsub]`.
- **Verification**: `podman run --rm --entrypoint python -v "$(pwd):/app:Z" kinetic-renderer -m unittest discover -s tests -v` prints `OK` including `test_text`.
- **Commit message**: `feat: .ass subtitle pipeline with wrapping, safe zones, and karaoke`
- Completed 2026-06-01 by /skill:vox build.

### CP-2: End-to-end text render verification ✅

- **Touches**: `tests/test_render.py`, `tests/verify.sh` (no change expected)
- **Tasks**:
  1. Add an E2E test: render a temp project with one plain-text segment, one word_flash segment, and one lower_third segment; assert the render succeeds, `output/subtitles.ass` exists with the expected styles and events, and ffprobe shows the video unchanged in contract (R1 S2 - no MoviePy TextClip path is already enforced by the import-hygiene test; the .ass burn replaces drawtext).
  2. Assert the burned output differs from a no-text render (text actually rendered - compare file size or frame bytes at a text timestamp).
- **Verification**: `podman run --rm --entrypoint python -v "$(pwd):/app:Z" kinetic-renderer -m unittest discover -s tests -v` prints `OK`; `tests/verify.sh` exits 0 (ALL GATES PASSED, fixture render now burns subtitles).
- **Commit message**: `test: end-to-end .ass text burn verification`
- Completed 2026-06-01 by /skill:vox build.

## Risks & Open Questions

1. **Char-width estimate drives wrapping.** `font_size * 0.55` is an approximation; libass may break lines differently than the estimate. The R2 scenario asserts the GENERATOR's output (multi-line, estimated width within box), not pixel-level libass layout. If actual renders overflow in build, the factor gets tuned.
2. **Alignment changes the look.** Spec D moves captions from center to bottom safe-zone (Alignment=2). This is the spec's intent (captions must not sit under platform UI), but it changes the fixture's visual. Accepted.
3. **Karaoke highlight color** defaults to green in the SecondaryColour; not configurable until Spec C themes land.
4. **Horizontal safe zones are internal constants** (0.08/0.15), not config keys. Vertical is the primary orientation; if horizontal becomes first-class, the keys get added then.
5. **subtitles filter filename escaping.** The output path is `output/subtitles.ass` (no special chars), so `filename=` needs no escaping; if that changes, an escape function is required.
6. **libass burn cost** is a per-frame text render; negligible at 360x640 fixture size, fine at 1080x1920.

Plan ready: 2 checkpoints, ~4 hours total. Run `/skill:vox build 04-text-layout` to start CP-1.
