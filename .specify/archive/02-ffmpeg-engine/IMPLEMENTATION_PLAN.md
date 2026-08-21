# 02-ffmpeg-engine - Implementation Plan

## Delta Summary

Greenfield change. Touches living domain `rendering` (does not exist yet, created at archive): 7 ADDED requirements, 11 scenarios.

- R1 Single-pass filtergraph rendering (2 scenarios)
- R2 Filter parity (2 scenarios)
- R3 Effect parity (2 scenarios)
- R4 Text and audio parity (2 scenarios)
- R5 Deterministic output (1 scenario)
- R6 Container diet (1 scenario)
- R7 Render output contract (1 scenario)

## Current State Summary

main.py renders cutlists through MoviePy: per-segment `_load_asset` (PIL crop for images, VideoFileClip crop for video), `apply_filter` (NumPy per-pixel `_contrast_crush`, `_chromatic_aberration`, `_film_grain`), `apply_effect` (resize lambdas for ken_burns/snap_zoom, no-ops for strobe/word_flash), `TextClip` overlays, `concatenate_videoclips`, `_mix_audio` (static 0.3 volume duck), then one `write_videofile` call. MoviePy, NumPy, and PIL are imported at main.py top level (lines 29-42). Beat-detect mode (`generate_kinetic_sequence`) already lazy-imports librosa but also uses moviepy.

Container ffmpeg is 7.1.4 with every filter the parity table needs: `hue`, `negate`, `lutrgb`, `rgbashift`, `noise`, `zoompan`, `drawtext`, `color`, `amix` (supports normalize=0), `concat`. LiberationSerif-Bold.ttf is at /usr/share/fonts/truetype/liberation/. Spec A is live: cutlists are validated before render, and `tests/verify.sh` renders the 360x640 fixture (4 segments, 4.0s) as the baseline gate.

The cutlist render path is a single integration point (`generate_from_cutlist`). Every segment maps to one chain: input (video or looped image) -> trim to clip_start/clip_end -> setpts -> filter -> effect -> fps -> cover-scale/crop -> concat -> drawtext overlays -> audio mix -> encode.

## Checkpoints

### CP-1: Filtergraph compiler module ✅

- **Touches**: `src/compiler/__init__.py` (new), `src/compiler/graph.py` (new), `src/compiler/video.py` (new), `tests/test_compiler.py` (new)
- **Tasks**:
  1. Create `src/compiler/video.py` with per-filter and per-effect chain builders: `grayscale` -> `hue=s=0`; `color_invert` -> `negate`; `color_crush` -> `format=gray,lutrgb` threshold to black/white; `high_contrast_green` / `high_contrast_red` -> same threshold with the accent channel; `chromatic_aberration` -> `split` + `rgbashift=rh=2:bh=-2`; `film_grain` -> `noise=alls=4:allf=t:seed=<fixed>`; `white_flash` -> `color` source segment. Effects: `ken_burns_slow` (zoompan, 8%, linear), `ken_burns_fast` (zoompan, 15%, linear), `snap_zoom` (zoompan step at midpoint); `strobe` and `word_flash` emit no nodes (identity per delta spec R3).
  2. Create `src/compiler/graph.py` with a pure `compile_graph(config, segments, audio) -> CompiledGraph` returning input args, the `-filter_complex` string, and map labels. Design: dedupe asset inputs by path (fixture reuses clip.mp4 twice via split); images become `-loop 1 -framerate <fps>` streams; per-segment chains `trim -> setpts -> filters -> zoompan -> fps -> scale+crop (cover, center) -> setsar`; `concat=n=N:v=1:a=0`; drawtext overlays after concat with `enable='between(t,start,end)'`, center position, fontfile/color/stroke from config; audio chain `volume=0.3` (soundtrack only) -> `atrim=0:DUR` -> `amix=inputs=2:normalize=0`; output mapping with aac and yuv420p.
  3. `compile_graph` must be a pure function: no ffmpeg execution, no filesystem writes beyond reading config/segments. It must be deterministic (same inputs, same string).
  4. Create `tests/test_compiler.py` (stdlib unittest, runs in container): single `-filter_complex` present; segment chains emit the expected nodes (hue, negate, lutrgb, rgbashift, noise, color, zoompan); snap_zoom zoompan expression steps at the segment midpoint; drawtext node carries the fixture text; volume and amix nodes present when both audio files exist; white_flash segments emit a color node; dedupe: one input per unique asset path; concat count matches segment count; no upload/download nodes (CPU path, Spec G later).
- **Verification**: `podman run --rm --entrypoint python -v "$(pwd):/app:Z" kinetic-renderer -m unittest discover -s tests -v` prints `OK` including `test_compiler`.
- **Commit message**: `feat: add ffmpeg filtergraph compiler`
- Completed 2026-06-01 by /skill:vox build.

### CP-2: Single-pass render integration ✅

- **Touches**: `main.py`, `src/compiler/graph.py`, `tests/test_validator.py` (unused now? no - keep), `tests/test_render.py` (new), `tests/verify.sh`, `Containerfile` (no change expected)
- **Tasks**:
  1. Replace the MoviePy cutlist path in `generate_from_cutlist`: after validation, build the graph via `compile_graph`, execute one `ffmpeg -y ... -filter_complex ... -map [vout] -c:v libx264 -preset medium -crf 23 -threads 4 -pix_fmt yuv420p -movflags +faststart -c:a aac` subprocess. Preserve the existing CLI, config merge, audio auto-detection rules (filename contains `voice` or `vo.`), and output path.
  2. Delete the MoviePy cutlist helpers: `_load_asset`, `apply_filter`, `apply_effect`, `_contrast_crush`, `_chromatic_aberration`, `_film_grain`, `_mix_audio`. Move all moviepy imports to be lazy inside `generate_kinetic_sequence` (beat-detect keeps working). Top-level main.py imports become stdlib + `src.validator` + `src.compiler`.
  3. Containerfile: keep the four Python packages installed (beat-detect mode needs moviepy and librosa; pillow/numpy are moviepy dependencies). The diet is the import graph, not the installed set.
  4. Create `tests/test_render.py`: (a) determinism - render the fixture twice into temp files, assert byte-identical; (b) import hygiene - `import main` in a fresh interpreter and assert `moviepy`, `PIL`, `numpy` are absent from `sys.modules`; (c) output contract - render fixture, ffprobe asserts resolution 360x640, fps 15, duration 4.0, h264 video stream, aac audio stream.
  5. Update `tests/verify.sh` to run the new tests and to ffprobe resolution/fps/streams in addition to duration.
- **Verification**: `tests/verify.sh` exits 0 (ALL GATES PASSED) including the determinism, import-hygiene, and contract checks; and `podman run ... -m unittest discover -s tests -v` prints `OK`.
- **Commit message**: `feat: render cutlists via single-pass ffmpeg`
- Completed 2026-06-01 by /skill:vox build.

## Risks & Open Questions

1. **zoompan on video input is frame-rate sensitive.** Design uses looped-image streams for images (uniform `in`-based zoom expressions) and per-frame zoompan for video. If zoompan produces jittery output in build, fallback is crop-with-frame-eval, which changes the CP-1 scenario check ("filter_complex contains zoompan") and requires a plan amendment. Default: zoompan first.
2. **Container diet is scoped to the import graph, not the installed set.** The delta spec R6 says drop moviepy/librosa/pillow/numpy from the install, but beat-detect mode needs moviepy and librosa to keep working. Literal package removal requires removing or converting beat-detect mode, which is out of this change's scope. Default: lazy imports, packages stay. If you want the literal removal, beat-detect becomes a follow-up decision.
3. **amix normalize=0** is required to match the current CompositeAudioClip summing behavior. Confirmed supported in container ffmpeg 7.1.4.
4. **Determinism is byte-level.** x264 with fixed threads/crf and seeded noise is deterministic in practice. If the byte-identical check flakes in build, relax to stream-hash comparison and note it.
5. **Text escaping.** drawtext inline text must escape `:`, `'`, `%`, `\`. Fixture text is simple; a small escape function covers real cutlists. Escaping bugs surface as ffmpeg syntax errors, caught by the render test.
6. **Font path is container-specific.** The compiler emits the LiberationSerif-Bold.ttf absolute path. Host-only iteration without fonts-liberation will fail drawtext; verification stays container-based.
7. **Strobe/word_flash emit nothing** in the graph (identity per delta spec R3). white_flash segments produce the flash frames via the color node. word_flash real implementation is Spec D.
8. **Behavioral parity is structural, not pixel-exact.** The delta spec verifies node presence in the graph, not pixel equality with the old engine. Visual drift is acceptable within the mapping table; ffprobe checks cover resolution/fps/duration.

Plan ready: 2 checkpoints, ~6 hours total. Run `/skill:vox build 02-ffmpeg-engine` to start CP-1.
