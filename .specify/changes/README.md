# n0x-content - Spec Pack Index and Build Order

Merged spec pack for improve.md. Seven specs (A-G) across four phases, executed in strict topological order.

Building downstream features (themes, text, audio) on the legacy MoviePy backend would cause duplicate work and code churn, because Spec B rips out the per-frame Python pipeline. All visual and audio work after Phase 2 targets the new filtergraph compiler.

## Phase Map

```
┌────────────────────────────────────────────────────────┐
│ Phase 1: Quality Gate & Test Fixtures                  │
│ [Spec A: Schema Validation Gate]                       │
│ + Runnable Test Fixture & Verification Suite           │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Phase 2: Core Engine Overhaul                          │
│ [Spec B: Native FFmpeg Filtergraph Engine]             │
│ [Spec G: GPU Auto-Detection & HW Accel]                │
│ (B consumes G's hardware profile for encoder choice)   │
└─────────────┬────────────────────────────┬─────────────┘
              │                            │
              ▼                            ▼
┌───────────────────────────┐┌───────────────────────────┐
│ Phase 3A: Audio Engine    ││ Phase 3B: Visual Engine   │
│ [Spec E: Audio Mastering] ││ [Spec D: Text & Layout]   │
└─────────────┬─────────────┘└─────────────┬─────────────┘
              └─────────────┬──────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Phase 4: Observability                                 │
│ [Spec F: FFmpeg Progress Telemetry & Status]           │
└────────────────────────────────────────────────────────┘
```

## Change Index

| Change | Spec | Phase | Domain | Size | Directory |
|--------|------|-------|--------|------|-----------|
| `01-validation-gate` | A | 1 | validation | S | `.specify/changes/01-validation-gate/` |
| `02-ffmpeg-engine` | B | 2 | rendering | XL | `.specify/changes/02-ffmpeg-engine/` |
| `07-gpu-acceleration` | G | 2 | hardware-acceleration | M | `.specify/changes/07-gpu-acceleration/` |
| `05-audio-mastering` | E | 3A | audio | M | `.specify/changes/05-audio-mastering/` |
| `04-text-layout` | D | 3B | typography | L | `.specify/changes/04-text-layout/` |
| `03-themes-recipes` | C | 3B | theming | L | `.specify/changes/03-themes-recipes/` |
| `06-progress-telemetry` | F | 4 | observability | S | `.specify/changes/06-progress-telemetry/` |

## Dependency Rules

- **A**: foundation, no dependencies. Everything else verifies against its fixture project.
- **B**: depends on A (fixture + validation gate). Replaces the MoviePy render loop.
- **G**: depends on B. Its hardware profile is a constructor parameter of B's graph compiler, which is why G ships in Phase 2, not later. Retrofitting `hwupload`/`hwdownload` into a CPU-only graph compiler is a rewrite.
- **C**: depends on B (graph extension points) and A (brutalist parity against the fixture).
- **D**: depends on B (text node replacement in the graph).
- **E**: depends on B (audio node replacement in the graph).
- **F**: depends on B (owns the ffmpeg process) and A (cutlist duration for ETA).

## Target Module Architecture

After all phases, `main.py` is split into discrete modules so no single file carries the whole engine:

```
src/
├── cli.py             # argparse, path resolution, entry point
├── validator.py       # Spec A: schema checks, asset probes, continuity
├── compiler/
│   ├── graph.py       # Spec B: filtergraph construction (accepts hardware profile)
│   ├── video.py       # Spec B, C: transforms, transitions, LUTs
│   ├── audio.py       # Spec E: sidechain, loudnorm, gating
│   └── text.py        # Spec D: .ass generator, safe zones
├── themes.py          # Spec C: theme loader and presets
├── gpu.py             # Spec G: probe + hardware profile
└── telemetry.py       # Spec F: -progress parsing, JSON events
```

## Scope Boundaries

- Spec B does NOT implement the advanced text or audio features. It ships parity (drawtext center text, volume 0.3 ducking). Specs D and E replace those in Phase 3.
- Spec B does NOT implement word_flash. Word-level timing is text-domain and lands in Spec D.
- Spec G does NOT add GPUs to machines that lack them. CPU fallback is the exact current behavior.

## Layman's Explanation

To upgrade n0x-content, we cannot simply patch all missing features at once.

First, we install a guardrail (Spec A) so the tool immediately stops and tells you if your script or video clips are missing or broken.

Second, we rip out the slow MoviePy engine and replace it with a fast, direct ffmpeg pipeline (Spec B), and make it use the GPU when one exists (Spec G).

Once that foundation is solid, we independently plug in professional audio mastering (Spec E), clean text formatting (Spec D), and customizable visual themes (Spec C), followed by a progress stream that shows how fast your video is rendering (Spec F).
