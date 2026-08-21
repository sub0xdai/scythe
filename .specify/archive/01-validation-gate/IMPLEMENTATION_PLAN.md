# 01-validation-gate - Implementation Plan

## Delta Summary

Greenfield change. Touches living domain `validation` (does not exist yet, created at archive): 4 ADDED requirements, 10 scenarios.

- R1 Cutlist schema enforcement (3 scenarios)
- R2 Pre-flight asset validation (3 scenarios)
- R3 Synthetic fixture project (2 scenarios)
- R4 Fixture verification command (2 scenarios)

## Current State Summary

main.py loads `prompts/cutlist.json` with raw `json.load` at line 288 and never validates it. A missing cutlist file exits 1 (line 282), but an invalid cutlist proceeds into the render loop. Missing assets degrade to silent black frames via `_load_asset` (line 103), never failing up front.

`schemas/cutlist.schema.json` exists and documents the contract, but it contains a non-standard `$data` construct in its `allOf` block (an ajv extension). Python's jsonschema lib raises `SchemaError` when loading this schema, so it cannot be used as-is. The per-segment `end > start` rule it tries to express must move to the code pass. The other documented rules (uppercase text, white_flash constraints, asset-required-unless-generated) live only as `$defs` documentation and are not enforceable in standard JSON Schema; they are out of scope for this change.

No test harness exists. `projects/` is empty; the only scaffold is `templates/project/`. The container (`Containerfile`) installs librosa, moviepy, pillow, numpy but not jsonschema. ffprobe ships with the ffmpeg system package, so it is available in the container for asset probing.

The render entry point is `generate_from_cutlist` in main.py. It is the only caller of the cutlist path; beat-detect mode does not use cutlists. This gives a single integration point for the validation gate.

## Checkpoints

### CP-1: Validation gate wired into the render path ✅

- **Touches**: `schemas/cutlist.schema.json`, `Containerfile`, `src/validator.py` (new), `main.py`, `tests/test_validator.py` (new), `.gitignore`
- **Tasks**:
  1. Repair `schemas/cutlist.schema.json`: delete the `allOf` block that uses `$data`. Replace it with a `$comment` stating the `end > start` rule is enforced by the validator code pass. Verify the schema loads cleanly under jsonschema draft 2020-12.
  2. Add `jsonschema` to the Containerfile uv install line.
  3. Create `src/validator.py` with one public entry `validate(segments, project_dir) -> list[str]` returning all violations (never fail-fast). Rules in scope: jsonschema shape check (required fields, types, enums, minItems), per-segment `end > start`, cross-segment continuity with 1e-3 epsilon tolerance, cross-segment filter adjacency (violation only when both consecutive filters are non-null and equal), and asset pre-flight (exists, non-zero byte, ffprobe-probes a valid stream; images also pass ffprobe via the image demuxer, no PIL).
  4. Hook into main.py `generate_from_cutlist` immediately after `json.load`: call `validate`, print every violation, exit 1. Keep the existing missing-cutlist exit path.
  5. Create `tests/test_validator.py` (stdlib unittest) covering: valid cutlist passes; `end < start` flags segment index 1; gap flags offending timestamps; overlap flags offending timestamps; adjacency violation flagged; unknown enum value flagged; missing asset flagged; zero-byte asset flagged; corrupt file flagged; valid generated clip passes. One subprocess end-to-end test: a temp project with a broken cutlist, `python main.py --project` exits non-zero and prints the violation.
- **Verification**: `podman run --rm --entrypoint python -v "$(pwd):/app:Z" kinetic-renderer -m unittest discover -s tests -v` prints `OK` and all tests pass; and a manual `python3 -c` jsonschema load of the repaired schema succeeds.
- **Commit message**: `feat: validate cutlist and assets before render`
- Completed 2026-06-01 by /skill:vox build.

### CP-2: Synthetic fixture project and verification command ✅

- **Touches**: `tests/fixtures/generate_fixture.sh` (new), `tests/fixtures/synthetic_project/config.json`, `tests/fixtures/synthetic_project/prompts/cutlist.json`, `tests/fixtures/synthetic_project/audio/.gitkeep`, `tests/fixtures/synthetic_project/raw_footage/.gitkeep`, `tests/fixtures/synthetic_project/overlays/.gitkeep`, `tests/verify.sh` (new), `.gitignore`
- **Tasks**:
  1. Create `tests/fixtures/generate_fixture.sh`: deterministic ffmpeg generation of `raw_footage/clip.mp4` (testsrc2 360x640@15fps, 2s), `raw_footage/photo.png` (color source, 1 frame), `audio/soundtrack.wav` (sine 220Hz, 4s), `audio/voiceover.wav` (sine 440Hz, 4s). Idempotent re-run.
  2. Create the fixture project files: `config.json` with `resolution [360, 640]`, `fps 15`, `font LiberationSerif-Bold`, `font_size 28`; `prompts/cutlist.json` with 4 segments covering hook (grayscale + ken_burns_slow + text), drop_transition (white_flash, null text), and two kinetic_cut segments (high_contrast_green + snap_zoom, chromatic_aberration + ken_burns_fast) referencing the video and the image, continuous from 0.0 to 4.08s. Names `voiceover.wav` so the ducking path triggers.
  3. Create `tests/verify.sh`, the single verification command: regenerate fixture assets, run the CP-1 unit tests inside the container, render the fixture via `./render.sh tests/fixtures/synthetic_project`, assert the output exists and ffprobe reports duration greater than zero, then run a negative gate test against a temp copy of the fixture whose cutlist references a missing asset, asserting non-zero exit. Any failure exits non-zero.
  4. Update `.gitignore` to exclude generated fixture media (mp4, wav, png under `tests/fixtures/`).
- **Verification**: `tests/verify.sh` exits 0; and a manual `tests/verify.sh` run after corrupting the fixture cutlist (temporarily) exits non-zero with the missing asset named.
- **Commit message**: `test: add synthetic fixture project and verification gate`
- Completed 2026-06-01 by /skill:vox build.

## Risks & Open Questions

1. **Schema `$data` repair is mandatory, not optional.** Python jsonschema raises SchemaError on the current schema. The plan removes the block and enforces `end > start` in code. Confirm you accept editing `schemas/cutlist.schema.json` (it is currently the documented contract; the edit keeps its meaning).
2. **Documented rules not enforced in this change.** The schema `$defs` also documents uppercase 2-5 word text, white_flash text-null, asset-required-unless-generated, and filter-effect compatibility. Standard JSON Schema cannot express them and the delta spec only requires continuity and adjacency in the code pass. Default: not enforced in Spec A. Add later if cutlist quality demands it.
3. **Behavior change: missing assets now abort.** Today a missing asset renders a black frame. After CP-1 the render aborts with the file named. The `_load_asset` fallback stays in the code but becomes unreachable through the pre-flight gate. Confirm this matches intent (the delta spec says abort).
4. **Continuity tolerance.** Float drift in LLM-generated cutlists is real. The plan uses 1e-3 epsilon for the `end == next.start` check. Exact equality would reject valid LLM output.
5. **Fixture resolution is 360x640 at 15fps.** Chosen so the MoviePy render stays fast in CI. Full 1080x1920 renders are the real-world path and are not covered by the fixture until Spec B lands.
6. **Verification requires podman.** The unit tests and fixture render run inside the rebuilt container because the host may lack moviepy, jsonschema, and fonts-liberation. Host iteration is possible only with those installed.
7. **TB-08 exists in main.py.** `generate_from_cutlist` is already over 70 lines. This change adds about 6 lines. The module split that fixes TB-08 is Spec B scope; not expanded here.

Plan ready: 2 checkpoints, ~4 hours total. Run `/skill:vox build 01-validation-gate` to start CP-1.
