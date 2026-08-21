# 01-validation-gate - Completion

- Date completed: 2026-06-01
- Final commit range: `2387529` (single commit covering CP-1 and CP-2)

## Files changed

CP-1 (validation gate):
- `schemas/cutlist.schema.json` - removed non-standard `$data` allOf block; added `$comment` noting cross-field rules live in the validator
- `src/validator.py` (new) - schema shape check gates timeline (end > start, continuity @ 1e-3, filter adjacency) and asset passes (exists, non-zero, ffprobe)
- `main.py` - validation hook after cutlist load; prints every violation, exits 1
- `Containerfile` - added jsonschema
- `tests/test_validator.py` (new) - 13 unit + end-to-end tests

CP-2 (fixture + gate):
- `tests/fixtures/generate_fixture.sh` (new) - deterministic ffmpeg asset generation
- `tests/fixtures/synthetic_project/` (new) - config.json, prompts/cutlist.json, .gitkeep dirs
- `tests/verify.sh` (new) - the single verification command
- `.gitignore` - generated fixture media + output excluded

## Notes

- Generated fixture media (wav, mp4, png, render output) were accidentally committed in `2387529`; untracked and gitignored afterward. Follow-up commit needed for the untracking + archive move.
- Archive move (`.specify/changes/01-validation-gate/` to `.specify/archive/`) pending commit.
- Living spec created: `.specify/specs/validation/spec.md` (4 requirements, 10 scenarios).
