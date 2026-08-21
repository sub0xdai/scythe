# LLM Video Generation - Scope (not implemented)

Scope for plugging an LLM video-generation API (MiniMax first, others later) into scythe as a supplement. This document studies the seam, the providers, and the design. Nothing here is built.

## Why

scythe composites and masters user-provided assets. LLM video APIs can GENERATE those assets from a prompt. The combination is: prompt -> generated clips -> scythe's existing validation, cut, grade, caption, and audio-master pipeline. The provider generates footage; scythe stays the editor. This is supplementation, not replacement.

## Integration seams in the current pipeline

```
[prompt] -> [cutlist.json] -> [validation gate] -> [one ffmpeg filtergraph] -> [MP4 + JSON events]
```

Two natural seams:

1. **Asset generation** - before ingest. Prompt -> clips into `raw_footage/`. The generated clips then flow through the existing `generate_cutlist.py` and render unchanged.
2. **Cutlist generation** - the LLM cutlist step already exists as `prompts/brutalist-video-prompt.md` fed by hand to an LLM. It can become an API call with the same prompt text.

Seam 1 is the smallest useful slice and the recommended first phase.

## Provider landscape

Costs are per second of video, approximate, as of Feb 2026. Verify before build; pricing churns.

| Provider | Model (2026) | API access | Modes | Duration | Resolution | ~$/sec |
|----------|--------------|------------|-------|----------|------------|--------|
| MiniMax | Hailuo / M2-H3 | direct REST | t2v, i2v (first/last frame), reference-to-video | 4-15s | 768P, 2K | ~0.027 |
| Google | Veo 3.1 | Gemini API / Vertex AI | t2v, i2v | 8s (up to 1 min research) | 720p/1080p | ~0.030 |
| Runway | Gen-4.5 | REST / SDK | t2v, i2v, camera control | up to 10s | up to 4K | ~0.050 |
| Kling | 3.0 | REST / aggregators | t2v, i2v | 5-10s | 1080p | ~0.084 |
| OpenAI | Sora 2 | REST | t2v | up to 10s | 720p/1080p | ~0.100 |
| ByteDance | Seedance 2.0 | aggregators | t2v, i2v | 5-10s | 1080p | ~0.100 |
| Luma | Ray 3.2 | REST | t2v, i2v | 5s | 1080p | ~0.200 |

Open-weights models (Wan 2.6, HunyuanVideo) run via aggregators (fal, Replicate) at comparable cost but with self-host or aggregator licensing.

## MiniMax API facts (verified against docs)

- Auth: HTTP Bearer with an API key from Account Management > API Keys.
- Endpoint: POST video generation v2, body `{"model": "MiniMax-H3", "content": [...], "resolution": "768P"|"2K", "duration": 4-15}`.
- `content` is a multimodal array: a `text` element alone is text-to-video; adding an image with `role=first_frame` or `last_frame` (or both) is image-to-video; `reference_image` / `reference_video` / `reference_audio` roles are reference-to-video.
- Async: the create call returns a `task_id`; a query-task endpoint returns status and the result. Optional `callback_url` for push.
- Cost: ~$0.027/s on the Hailuo tier; a 2K 10s clip is roughly $0.30.

## Scoped design (what we would build if greenlit)

- Flat config keys: `ai_provider`, `ai_model`, `ai_prompt`, `ai_resolution`, `ai_duration`, `ai_count`. The API key lives in an env var, never in config.json.
- `src/providers/` with a base interface: `generate(prompt, opts) -> local clip path`, plus a MiniMax implementation (create task, poll, download).
- `scripts/generate_clips.py <project-dir>`: prompt -> N generated clips -> `raw_footage/`. Generated clips are ordinary assets; the validation gate, `generate_cutlist.py` (which already clamps to probed clip durations), and the render pipeline consume them unchanged.
- Phase 2 seam: a cutlist agent - one API call with `prompts/brutalist-video-prompt.md` plus the asset inventory, writing `cutlist.json`. Same prompt text, API-backed.
- Phase 3: multi-provider via the abstraction (Veo, Runway, Kling drop in as new implementations).

## Deliberate non-goals

- scythe does not become a hybrid editing-and-generation tool. It edits; providers generate footage.
- No local/open-model hosting.
- No audio/voice generation (voiceover stays user-provided).
- No watermark or licensing negotiation tooling.

## Risks

- **Cost**: 2K clips at $0.03-0.20/s add up fast. `ai_count` and `ai_duration` are hard caps; a prompt loop must be bounded.
- **Licensing**: provider terms on commercial use of outputs vary. Verify per provider before shipping a phase.
- **Quality variance**: generated clips can undershoot requested duration. `generate_cutlist.py` already probes and clamps, so a short clip degrades gracefully instead of breaking the timeline.
- **API instability**: model names and endpoints churn (H3, M2.7, Hailuo in the same docs). The provider abstraction isolates churn to one file.
- **Latency**: generation is minutes, not seconds, and async. The Spec F progress events cover rendering only; the generation phase gets a status line, not JSON events.
- **Determinism**: generation is non-deterministic. scythe's byte-identical render guarantee holds for whatever clips exist; the clips themselves vary per run.

## Open questions before any build

1. Preferred first provider - MiniMax, or Veo 3.1 given similar cost and Google's API polish?
2. Which mode matters first - text-to-video, or image-to-video from a user still?
3. Are outputs commercial-use licensed for the target use cases?
