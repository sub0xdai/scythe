# 03-themes-recipes - Implementation Plan

## Delta Summary

Greenfield change. Touches living domain `theming` (does not exist yet, created at archive): 5 ADDED requirements, 9 scenarios.

- R1 Theme schema and loader (2 scenarios)
- R2 Bundled themes (1 scenario)
- R3 LUT color grading (2 scenarios)
- R4 Parameterized transitions (3 scenarios)
- R5 Filter registry extension (1 scenario)

## Current State Summary

config.json is flat-key merged in `load_config` (DEFAULTS <- project_config <- CLI overrides). There is no theme concept, no LUT support, no transitions (hard cuts only via `concat=n=N`), and no easing choice (zoompan uses linear `in/N`). Filters and effects are hardcoded in `src/compiler/video.py`; `schemas/filter-effect-matrix.json` documents compatibility, and the Spec A validator already rejects unknown filter names via the cutlist schema enum (tested in `test_unknown_filter_flagged`).

The compiler chain is: per-segment chains -> `concat=n=N` -> fps/trim clamp -> [subtitles] -> [hw chain] -> encoder. Audio trims to `segments[-1]["end"]`. Text and audio read their style/audio keys straight from config, so a theme that overrides flat keys reaches everything with zero downstream changes.

Key design decisions:
- A theme is a JSON object of the SAME flat config keys the engine already reads (font, font_size, text_color, stroke_color, lufs_target, duck_*, voice_cleanup, text_box_width, safe_zone_*, plus `lut`, `transition_mode`, `transition_duration`, `ken_burns_easing`, `default_filter`, `default_effect`). This reuses the existing merge machinery; no nested palette schema needed (palette = the flat color keys; accent colors stay hardcoded in the high-contrast filters).
- Precedence: DEFAULTS < theme < config.json < CLI. Explicit project config beats the theme.
- Transitions via chained `xfade`: offset_k = T_k - k*d for segment k, final duration = T_N - (N-1)*d. This keeps the timeline contiguous by construction and shrinks the output exactly by the overlap; the audio trim follows the new duration.

## Checkpoints

### CP-1: Theme loader, bundled themes, and LUT grading ✅

- **Touches**: `src/themes.py` (new), `main.py`, `src/compiler/graph.py`, `src/validator.py`, `themes/` (new dir), `tests/test_themes.py` (new), `tests/test_validator.py`
- **Tasks**:
  1. Create `src/themes.py`: `load_theme(theme_ref, base_dir=None) -> dict`. Resolves a NAME against `themes/<name>.json` or treats the ref as a path. Validates every key against a known flat-key set (all DEFAULTS keys plus lut, transition_mode, transition_duration, ken_burns_easing, default_filter, default_effect); unknown keys raise `ThemeError` naming them. Pure function, no rendering side effects.
  2. main.py `load_config`: insert the theme layer between DEFAULTS and project_config. config.json `theme` field (name or path, project-relative paths resolved against the project dir) -> `load_theme` -> merge. Keep the existing CLI override layer on top. DEFAULTS gains: `theme: None`, `lut: None`, `default_filter: None`, `default_effect: None`, `transition_mode: "hard_cut"`, `transition_duration: 0.5`, `ken_burns_easing: "linear"`.
  3. Create bundled themes: `themes/brutalist.json` (empty overrides - current behavior), `themes/clean_editorial.json`, `themes/documentary.json`, `themes/minimalist.json`. Each sets font, palette colors, safe zones, audio keys, and transitions sensibly for its name.
  4. Compiler: when `config["lut"]` is set, resolve against project_dir and insert `[vfps]lut3d=file={path}:interp=tetrahedral[vlut]` before the subtitles node; video_map chain becomes `[vfps] -> [vlut] -> [vsub] -> [vout]`. Apply `default_filter`/`default_effect` to asset segments that omit them (generated color segments are exempt).
  5. Validator: extend `validate(segments, project_dir, config=None)`; when config has a `lut`, emit an `asset_missing`-style violation if the file does not exist relative to project_dir. Existing callers pass no config and are unaffected.
  6. Tests (`tests/test_themes.py`): theme name resolution, path resolution, unknown-key abort naming the field, theme overrides applied to the compiled graph (font/lufs/transition keys flow through), brutalist parity (compile with theme brutalist == compile without any theme), LUT node in the graph, missing LUT aborts the render end-to-end, unknown filter via cutlist still rejected with a theme present.
- **Verification**: `podman run --rm --entrypoint python -v "$(pwd):/app:Z" kinetic-renderer -m unittest discover -s tests -v` prints `OK` including `test_themes`.
- **Commit message**: `feat: theme profiles with LUT grading`
- Completed 2026-06-01 by /skill:vox build.

### CP-2: Parameterized transitions and easing

- **Touches**: `src/compiler/graph.py`, `src/compiler/video.py`, `tests/test_compiler.py`, `tests/test_themes.py`
- **Tasks**:
  1. Compiler: when `config["transition_mode"] != "hard_cut"` and there are 2+ segments, replace the concat chain with chained xfade nodes: `[seg{k-1}][seg{k}]xfade=transition={mode}:duration={d}:offset={T_k - k*d}[v{k}]`. Modes: cross_dissolve -> fade, dip_to_black -> fadeblack, dip_to_white -> fadewhite, luma_wipe -> luma with a third geq-generated gradient map input. `duration` becomes `T_N - (N-1)*d` and flows into the trim clamp and audio trim. Hard cut keeps the existing concat (byte-identical).
  2. Guard: `transition_duration` must be smaller than every segment duration; abort with a clear message otherwise (a negative xfade offset is nonsense).
  3. video.py `zoompan_chain` gains an easing parameter: linear -> `t`, cubic and bezier -> smoothstep `t*t*(3-2*t)`. The compiler passes `config["ken_burns_easing"]`.
  4. Tests: cross_dissolve emits `xfade=transition=fade` with the computed offset; dip_to_black emits `fadeblack`; cubic easing emits the smoothstep expression in the zoompan z; luma_wipe emits the luma transition plus the geq map input; hard-cut default still emits `concat=n=4` and the contract duration stays 4.0; too-long transition duration aborts; the fixture render with a cross_dissolve theme produces the shorter duration and passes ffprobe.
- **Verification**: `podman run --rm --entrypoint python -v "$(pwd):/app:Z" kinetic-renderer -m unittest discover -s tests -v` prints `OK`; `tests/verify.sh` exits 0 (ALL GATES PASSED, hard-cut default unchanged).
- **Commit message**: `feat: parameterized transitions and ken burns easing`

## Risks & Open Questions

1. **luma_wipe is the highest-risk transition.** It needs a third xfade input: a geq-generated gradient map (`geq=r='X*255/W':g='X*255/W':b='X*255/W'` as a lavfi input). If it proves broken in build, it is a graph-data fix in `graph.py`, not a pipeline change. The delta scenario set does not exercise luma.
2. **Theme key set must stay in sync with DEFAULTS.** New config keys added later must be added to the theme-known-key set or themes referencing them fail loudly. That is the intended behavior (fail-loud on unknown fields).
3. **Accent colors stay hardcoded.** high_contrast_green/red keep their fixed accents; a theme cannot recolor them yet. Palette is text/stroke colors only.
4. **Precedence decision: config.json beats theme.** Explicit project settings win over theme defaults. If the opposite is wanted, it is a merge-order flip in `load_config`.
5. **xfade shifts later content earlier.** The final timeline compresses by (N-1)*d; absolute cutlist times beyond the first segment are not preserved in the output. This matches standard NLE transition behavior and the delta's continuity requirement.
6. **Transition duration guard** is required because xfade with duration >= a segment's length breaks. Abort with a message rather than emit a broken graph.

Plan ready: 2 checkpoints, ~5 hours total. Run `/skill:vox build 03-themes-recipes` to start CP-1.
