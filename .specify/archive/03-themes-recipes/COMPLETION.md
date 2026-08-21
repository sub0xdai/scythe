# 03-themes-recipes - Completion

- Date completed: 2026-06-01
- Final commit range: `23a5845..df0210b` (2 commits, one per CP)

## Files changed

CP-1 (themes + LUT):
- `src/themes.py` (new) - load_theme with strict flat-key validation (ThemeError on unknown fields), name/path resolution
- `themes/` (new) - brutalist ({} parity), clean_editorial, documentary, minimalist
- `main.py` - theme merge layer (DEFAULTS < theme < config.json < CLI); 7 new DEFAULTS keys
- `src/compiler/graph.py` - lut3d node before subtitles; theme default_filter/default_effect applied to asset segments
- `src/validator.py` - validate(segments, project_dir, config=None) emits lut_missing violation
- `tests/test_themes.py` (new) - 9 loader/integration tests

CP-2 (transitions + easing):
- `src/compiler/video.py` - zoompan easing: linear / cubic / bezier (smoothstep)
- `src/compiler/graph.py` - chained xfade replacing concat (offset_k = T_k - k*d), duration recomputed T_N - (N-1)*d into audio trim + output clamp; cross_dissolve/dip_to_black/dip_to_white/luma_wipe (nullsrc+geq map); duration guard; unknown-mode error
- `tests/test_themes.py` - 11 transition/easing tests incl. E2E cross_dissolve render (3.7s)

## Notes

- Brutalist parity proven: compile with theme brutalist == compile without theme (byte-identical).
- Hard-cut default stays byte-identical; E2E cross_dissolve render confirms xfade executes (duration 3.7 = 4.0 - 0.3).
- Accent colors stay hardcoded in high_contrast filters; palette = text/stroke flat keys.
- luma_wipe implemented via nullsrc+geq gradient map; not exercised by scenario tests (flagged in plan).
- Living spec created: `.specify/specs/theming/spec.md` (5 requirements, 9 scenarios).
