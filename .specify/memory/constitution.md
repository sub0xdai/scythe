# n0x-content - Constitution

## Tech Stack

- Python 3.11 (container runtime).
- MoviePy v2 + Pillow + NumPy + librosa (to be removed by Spec B; librosa stays only for legacy beat-detect mode).
- ffmpeg as a system package in the container.
- Host tools: yt-dlp, wget, ia (internetarchive CLI).
- Container runtime: podman.

## Key Files

| File | Role |
|------|------|
| `main.py` | Single-file engine: config merge, filters, effects, audio, CLI (target: split per the spec pack module map) |
| `schemas/cutlist.schema.json` | Segment contract. Currently documented but NOT enforced by main.py (Spec A closes this gap) |
| `schemas/filter-effect-matrix.json` | Filter x effect compatibility source of truth. New filters register here or fail validation |
| `prompts/brutalist-video-prompt.md` | LLM cutlist generator prompt |
| `templates/project/` | Scaffold copied by bootstrap.sh |
| `Containerfile` | python:3.11-slim + ffmpeg + fonts-liberation + python deps |
| `scripts/` | fetch_audio.sh, fetch_video.sh, fetch_images.sh, preprocess.sh, install_deps.sh |
| `render.sh`, `ingest.sh`, `bootstrap.sh` | Project lifecycle scripts |

## Verification Commands

Current state: no test runner, no linter, no packaging files.

- Smoke render: `python main.py --project <project>`
- Container render: `./render.sh <project>`
- Planned gate after Spec A: fixture render of `tests/fixtures/synthetic_project` plus validation abort tests.

## Conventions

- No em dash in docs. Plain dash instead.
- Long markdown: one sentence per line.
- MIT license.
- Commit messages: no trailers (no Co-authored-by, no Signed-off-by).
- Non-trivial logic ships one runnable check (assert-based or one small test). No test frameworks beyond what the spec pack requires.

## Routing

- No AGENTS.md in this repo. `~/1-projects/AGENTS.md` applies.
- Vox workflow: `/skill:vox plan <change>` then `/skill:vox build <change>`, then `/skill:vox archive <change>`.
