# 04-text-layout - Completion

- Date completed: 2026-06-01
- Final commit range: `2ec3c23..4b0c7f0` (2 commits, one per CP)

## Files changed

CP-1 (.ass pipeline):
- `src/compiler/text.py` (new) - pure build_ass: v4.00+ script, PlayResX/Y = canvas, Default/Karaoke/LowerThird styles, greedy word-wrap (0.55*font_size char estimate), safe-zone MarginV (Alignment=2), karaoke {\kD} tags, \fad lower-thirds
- `src/compiler/graph.py` - drawtext chain loop replaced with one subtitles=filename node; ass_path param; deleted dead _escape_text/_font_file/FONT_FILES
- `main.py` - writes output/subtitles.ass; DEFAULTS: text_box_width 0.8, safe_zone_top 0.12, safe_zone_bottom 0.25
- `schemas/cutlist.schema.json` - optional lower_third object
- `tests/test_text.py` (new) - 8 unit tests; test_compiler/test_gpu drawtext assertions updated

CP-2 (E2E):
- `tests/test_render.py` - TextBurnE2ETests: .ass content assertions + dark-pixel proof of actual libass burn; textless render stays white

## Notes

- The Spec A validation gate caught an invalid test cutlist (three consecutive white_flash segments violate filter adjacency) - gate working as designed.
- Dialogue line parsing gotcha: three ",," separators; text lives at split index [2].
- Horizontal safe zones remain internal constants (0.08/0.15); vertical is the primary orientation.
- Burn proven visually: dark outline pixels present at a text timestamp, absent in textless render.
- Living spec created: `.specify/specs/typography/spec.md` (5 requirements, 7 scenarios).
