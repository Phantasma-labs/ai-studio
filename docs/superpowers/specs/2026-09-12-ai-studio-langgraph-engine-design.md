# AI Studio — Stateful Multi-Agent Film Studio Engine

**Design spec · 2026-09-12**
**Status:** Awaiting review
**Supersedes:** `v1.0-legacy` (tagged) / branch `legacy01`

---

## 1. Purpose

The current repository is a prompt *generator*: a linear chain of LLM calls
(`pipeline.py`) that turns a concept into Nano Banana T2I/I2V prompt text and stops
there. A human then pastes those prompts into a generation service by hand.

This spec describes the rewrite into a **stateful production engine** that carries a
project from concept to a finished, muxed video file with no human step in the middle.

The engine targets **high-production short-form content**: advertising spots and
documentary shorts, **30 seconds to 5 minutes**. That duration band is the single
most important constraint in this document. It bounds shot count (roughly 8–60
shots), bounds budget (every shot costs real Magnific credits), and rules out
architectures that assume a human will fix a bad shot.

### 1.1 What changes

| Today | After |
|---|---|
| Linear function chain, stateless | LangGraph `StateGraph`, checkpointed, resumable |
| Output is prompt *text* | Output is a rendered `.mp4` |
| Every scene is one image + one clip | Shot-level units with per-shot QC and retry |
| One LLM for everything | Two tiers: heavy reasoner + fast structured |
| No media generation | Magnific: keyframes, motion, voice, SFX |
| Human pastes prompts | Engine drives the API end to end |
| Streamlit calls `pipeline.py` | Streamlit calls FastAPI; graph runs server-side |

### 1.2 Non-goals

- **Not** a real-time or interactive editor. Runs are minutes-to-tens-of-minutes jobs.
- **Not** multi-tenant / SaaS. Single-operator, single-project-at-a-time is fine.
- **Not** preserving the legacy Streamlit UI shape. The UI is repointed, not redesigned.
- **No** local model inference. All LLM traffic goes to Ollama (daemon-proxied cloud tags).
- **No** ComfyUI path in the engine. Legacy keeps it; the engine does not.

---

## 2. Verified external contracts

Everything in this section was verified against the live Magnific REST API during
research, not inferred. This mattered: **three assumptions in the original brief were
wrong**, and each would have produced code that fails at runtime.

### 2.1 Magnific endpoint map

Base URL `https://api.magnific.ai`, auth header `x-magnific-api-key`.

| Capability | POST (create) | GET (poll) |
|---|---|---|
| Keyframe | `/v1/ai/text-to-image/nano-banana-pro` | `/v1/ai/text-to-image/nano-banana-pro/{task-id}` |
| Motion | `/v1/ai/video/seedance-2-pro-{res}` | `/v1/ai/video/seedance-2-pro/{task-id}` |
| Voiceover | `/v1/ai/voiceover/elevenlabs-turbo-v2-5` | `/v1/ai/voiceover/elevenlabs-turbo-v2-5/{task-id}` |
| SFX | `/v1/ai/sound-effects` | `/v1/ai/sound-effects/{task-id}` |
| Music | `/v1/ai/music-generation` | `/v1/ai/music-generation/{task-id}` |
| Identity check | — | `/v1/ai/me/flows` |

**The asymmetry on the Motion row is real and must be encoded exactly as shown.**
For `seedance-2-pro`, resolution lives in the *create* path but is **omitted** from the
*poll* path. The newer `seedance-2-5-pro-{res}` family does the opposite — its poll path
*includes* resolution. Two different rules for two sibling endpoints. The client models
this as an explicit per-model endpoint descriptor, never as string concatenation.

Every task follows one lifecycle: `CREATED` → `IN_PROGRESS` → `COMPLETED` | `FAILED`.

### 2.2 Corrections to the original brief

These are the three places the brief's stated API shape does not match reality.

**Correction 1 — audio cannot be one method.** The brief specified
`generate_elevenlabs_audio(prompt_or_text, is_sfx=False)`. This is not implementable:

- Voiceover **requires** `voice_id` (no default exists).
- SFX **requires** `duration_seconds` (range 0.5–22) and has no voice concept at all.

A single method with an `is_sfx` flag would have to accept both parameters and ignore
one of them in each branch — an untyped union pretending to be an API. Splitting into
`generate_voiceover()` and `generate_sfx()` is the honest shape.

**Correction 2 — Seedance ignores `aspect_ratio` when an image is supplied.** The
engine always supplies a keyframe (it is image-to-video by design), so `aspect_ratio`
is dead weight on every call. Aspect ratio is decided once, at keyframe time, and the
video inherits it. Sending it anyway invites a future reader to believe it does something.

**Correction 3 — Seedance duration is any integer 4–15**, not the "5 or 10" the brief
implied. Also: Seedance emits **native audio** (`sound_effects` defaults to `true`).
This is a real asset — it means ambient sound comes free with the clip — but it also
means generated SFX must be *mixed against* existing clip audio rather than laid over
silence. Assembly accounts for this.

### 2.3 Multi-speaker dialogue

There is no API surface for multi-speaker dialogue. One voiceover task renders one
voice. A two-hander scene therefore costs two tasks and is mixed at assembly time.
The engine models this as: **one `DialogueLine` → one voiceover task**, with `speaker`
resolved against `CharacterProfile.voice_id`. Scenes with N speakers cost N tasks.

---

## 3. Architecture

### 3.1 Layout

```
ai-studio/
├── backend/
│   └── app/
│       ├── core/
│       │   ├── config.py          # Pydantic BaseSettings — the only secret reader
│       │   └── logging.py         # structured JSON logs, run-scoped
│       ├── graph/
│       │   ├── state.py           # Pydantic models + FilmProjectState TypedDict
│       │   ├── workflow.py        # StateGraph assembly, checkpointer, entrypoint
│       │   ├── nodes/
│       │   │   ├── writer_director.py
│       │   │   ├── casting_bible.py
│       │   │   ├── cinematographer.py
│       │   │   ├── magnific_render.py
│       │   │   ├── qc_critic.py
│       │   │   └── assembly.py
│       │   └── edges/
│       │       └── routing.py     # conditional edge functions
│       ├── clients/
│       │   ├── base.py            # Protocols: LLMProvider, ImageProvider, ...
│       │   ├── ollama_client.py   # OllamaCloudClient
│       │   ├── magnific_client.py # MagnificStudioClient (image + video)
│       │   ├── magnific_audio.py  # voiceover + sfx
│       │   ├── fakes.py           # deterministic offline providers
│       │   └── errors.py          # typed exception hierarchy
│       ├── services/
│       │   ├── assembly.py        # timeline → build plan
│       │   ├── ffmpeg_stitcher.py # concat / mux / loudness normalize
│       │   └── timeline.py        # Remotion-compatible JSON exporter
│       └── api/
│           ├── main.py            # FastAPI app factory
│           ├── routes/
│           │   ├── projects.py    # create / status / stream (SSE)
│           │   └── webhooks.py    # Magnific callbacks, HMAC-SHA256 verified
│           └── schemas.py         # request/response models
├── knowledge/                     # prompt source-of-truth (kept at root, see 3.3)
├── tests/
├── docs/superpowers/specs/
├── pyproject.toml
├── docker-compose.yml
└── .env                           # gitignored
```

### 3.2 Where the legacy code goes

Cut-over is **additive, never destructive**:

1. `git tag v1.0-legacy` on `33f5ecd` — done.
2. `git branch legacy01` — done.
3. `main` gains `backend/` alongside the existing files.

Legacy `app.py`, `applocal.py`, `ui_core.py`, `pipeline.py`, `clients/` stay on `main`
until the API layer can serve them, then get ported. Deleting them first would leave
nothing to port *from*. `legacy01` is the escape hatch if the port goes wrong.

### 3.3 Prompt storage

The `knowledge/*.md` files are the real IP here — 381 lines of accumulated prompt
engineering, including the 144-line Nano Banana render guide. The engine **keeps them at
the repo root** rather than burying them in the package, because the documented workflow
is "edit `knowledge/render_artist_style.md` to change prompting style" and that should
not require touching Python.

`config.prompts_dir` resolves to repo root `knowledge/`, with an env override. A small
`load_prompt(name)` helper (ported from `pipeline.py`) reads and caches them.

---

## 4. Data schemas

`backend/app/graph/state.py`. Strict Pydantic v2 (`model_config = ConfigDict(extra="forbid")`)
so a malformed LLM response fails loudly at the boundary rather than silently becoming
a `None` three nodes later.

### 4.1 Shot

```python
class Shot(BaseModel):
    shot_id: str                    # "sh_03"
    scene_id: str                   # "sc_02"
    duration_sec: float             # 4–15 (Seedance constraint)
    visual_action: str
    camera_angle: str
    lens_specs: str
    lighting: str
    dialogue: list[DialogueLine] = []
    sfx_description: str | None = None
    magnific_image_prompt: str
    seedance_motion_prompt: str
    keyframe_url: str | None = None
    video_url: str | None = None
    audio_url: str | None = None    # merged dialogue+sfx stem
    qc_passed: bool = False
    qc_notes: str | None = None
    retry_count: int = 0

class DialogueLine(BaseModel):
    speaker: str                    # → CharacterProfile.id
    line: str
    voice_id: str | None = None     # resolved at render time
```

`dialogue` is a list, not a string. The brief had it as `dialogue` singular; a shot with
two speakers needs two lines, and flattening them to one string destroys who-says-what
before it reaches the voice resolver.

### 4.2 CharacterProfile

```python
class CharacterProfile(BaseModel):
    id: str
    name: str
    visual_anchor_description: str  # the anti-drift paragraph, injected into EVERY prompt
    wardrobe_rules: str
    voice_id: str
```

`visual_anchor_description` is the load-bearing field. Character drift across shots is
the dominant failure mode in AI film — the fix is injecting one immutable physical
description into every keyframe prompt in which the character appears. The casting node
writes it once; the cinematographer node is *forbidden* from paraphrasing it.

### 4.3 FilmProjectState

```python
class FilmProjectState(TypedDict):
    project_id: str
    title: str
    logline: str
    target_duration_sec: int
    screenplay: str
    scene_breakdown: list[Scene]
    characters: dict[str, CharacterProfile]
    shots: list[Shot]
    qc_feedback: str | None
    qc_pass_count: int
    final_video_url: str | None
    timeline_json: dict | None
    status: Literal["queued","writing","casting","storyboarding",
                    "rendering","reviewing","assembling","complete","failed"]
    errors: list[str]
    cost_estimate_credits: float
```

`shots` uses an `operator.add`-free *replace* reducer: the cinematographer returns a
full shot list, and retries return only the corrected shots merged by `shot_id`. A
naive `operator.add` would duplicate shots on every retry loop — this is the single
easiest way to blow the credit budget, so the merge is explicit and unit-tested.

---

## 5. Graph

### 5.1 Topology

```
        ┌──────────────────┐
        │ writer_director  │  deepseek-pro · temp 0.6
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │  casting_bible   │  deepseek-flash · JSON
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐◄───────────────┐
        │  cinematographer │  deepseek-flash │  retry with
        └────────┬─────────┘  · JSON strict  │  qc_feedback
                 ▼                           │
        ┌──────────────────┐                 │
        │ magnific_render  │  Magnific API   │
        └────────┬─────────┘  (bounded conc) │
                 ▼                           │
        ┌──────────────────┐                 │
        │    qc_critic     │  deepseek-pro ──┘  failed shots
        └────────┬─────────┘  · vision         AND retries left
                 │
                 │ all pass OR retries exhausted
                 ▼
        ┌──────────────────┐
        │     assembly     │  FFmpeg + timeline JSON
        └────────┬─────────┘
                 ▼
               END
```

### 5.2 Routing

One conditional edge, one function, in `edges/routing.py`:

```python
MAX_SHOT_RETRIES = 2
MAX_QC_PASSES = 2

def route_after_qc(state: FilmProjectState) -> Literal["cinematographer", "assembly"]:
    if state["qc_pass_count"] >= MAX_QC_PASSES:
        return "assembly"                      # global guard wins, always
    failed = [s for s in state["shots"] if not s.qc_passed]
    if any(s.retry_count < MAX_SHOT_RETRIES for s in failed):
        return "cinematographer"
    return "assembly"
```

Two guards, both necessary:

- **Per-shot retry cap** (`retry_count < MAX_SHOT_RETRIES`) — matches the brief's intent.
  Prevents one permanently-bad shot from looping forever.
- **Global pass cap** — the per-shot cap alone is not sufficient. With 20 shots, a
  pathological state where each pass fails a *different* shot can cycle indefinitely
  while every individual shot stays under its own cap. `qc_pass_count` starts at 0 and
  is **incremented on every entry to the QC node**; the global guard is checked *first*,
  so it can never be pre-empted by the per-shot condition.

Note the graph deliberately routes **back to `cinematographer`, not to `magnific_render`**.
This matches the brief, and it is the right call: a QC failure means the *prompt* was
wrong (composition drifted, character off-model), not that the render glitched. Re-running
prompt generation is also cheaper than re-rendering blind.

### 5.3 Durability

`AsyncSqliteSaver` at `data/checkpoints.sqlite`. Thread ID = `project_id`. This buys
three things that matter at this budget:

- **Crash recovery.** A 40-shot render is many minutes of metered API calls. A crash at
  shot 31 must not re-bill shots 1–30.
- **Resume after a failed shot.** The operator can fix a prompt by hand and resume.
- **SSE replay.** The API streams from checkpoint deltas, so a client reconnecting
  mid-render sees current state rather than a blank screen.

---

## 6. Clients

### 6.1 Protocols (`clients/base.py`)

```python
class ImageProvider(Protocol):
    async def generate_keyframe(self, prompt: str, *, aspect_ratio: str = "16:9") -> str: ...
class VideoProvider(Protocol):
    async def animate(self, image_url: str, motion_prompt: str, *, duration_sec: int) -> str: ...
class AudioProvider(Protocol):
    async def generate_voiceover(self, text: str, *, voice_id: str) -> str: ...
    async def generate_sfx(self, description: str, *, duration_sec: float) -> str: ...
class LLMProvider(Protocol):
    async def complete(self, *, tier: LLMTier, system: str, user: str,
                       temperature: float, json_schema: type[BaseModel] | None = None) -> str: ...
```

Nodes depend on protocols, never on concrete clients. This is what makes the whole graph
testable without network access and without spending credits.

### 6.2 Ollama client

`OllamaCloudClient(base_url="http://127.0.0.1:11434", api_key=None)` — the local daemon
proxies `:cloud` tags, so no Ollama API key is needed in the client.

| Tier | Model tag | Temp | Used by |
|---|---|---|---|
| `HEAVY` | `deepseek-v4.1-pro:cloud` | 0.6 | writer_director, qc_critic |
| `FLASH` | `deepseek-v4.1-flash:cloud` | 0.2 | casting_bible, cinematographer, audio prompts |

Both tiers declared in config as `{tier}_model` / `{tier}_temperature` so a model swap
is a config change, not a code change.

**Structured output.** `json_schema` is enforced two ways: Ollama's native
`format: <json-schema>` at the API level, *and* Pydantic validation of the response
against the passed model. Native enforcement alone is a strong hint, not a guarantee —
the validator is what makes it a guarantee, and it fails with the offending payload
attached rather than an opaque `ValidationError`.

**Vision.** `deepseek-v4.1-flash:cloud` advertises `vision` alongside `tools` and
`thinking`. The QC node uses FLASH for the vision pass (inspect rendered keyframes) and
HEAVY for the judgment pass (is this shot acceptable, and why). No separate VL model is
required — an earlier draft of this design proposed pulling `qwen3-vl:8b`, which was
unnecessary.

### 6.3 Magnific client

`MagnificStudioClient` wraps image + video; `magnific_audio.py` wraps voice + SFX. The
split follows the endpoint asymmetry in §2.1 rather than an arbitrary line count.

Polling is shared infrastructure (`_poll_task`) with:
- Exponential backoff, 2s base, ×1.6, capped at 15s
- Hard ceiling of 600s per task, then `RenderTimeout`
- Retry on 429/5xx with jitter; fail fast on 4xx (a bad prompt will not fix itself)
- Structured logging of every state transition with task id and elapsed time

**Concurrency is bounded by `asyncio.Semaphore`, default 4.** Magnific allows 50 req/s
burst and 10 req/s average, but the binding constraint is *credits*, not rate limit.
Unbounded `asyncio.gather` over 40 shots would fire 40 keyframes at once — fast, and a
fast way to discover a credit ceiling mid-run with 12 half-rendered shots. Default 4 is
deliberately conservative and configurable.

### 6.4 Fakes (`clients/fakes.py`)

Deterministic offline providers: fixed-latency fake URLs, no network. Not a fallback —
a **test seam**. Every graph test runs against fakes. Without them the node tests are
either unmockable or they bill the user's account on every CI run.

This resolves the open question from the design discussion: fakes are **in scope**, not
as an alternative to the real client but alongside it. They are required for the
testing plan in §12 to be executable at all.

### 6.5 Errors (`clients/errors.py`)

```
StudioError
├── ConfigError
├── LLMError
│   ├── LLMValidationError   # carries raw payload + Pydantic errors
│   └── LLMTimeout
├── RenderError
│   ├── RenderFailed         # Magnific returned FAILED
│   ├── RenderTimeout
│   └── InsufficientCredits  # distinct: retrying is pointless
└── AssemblyError
```

`InsufficientCredits` is separated because it is the one render error where the correct
response is to *stop the whole run* and tell the operator, not to retry or degrade.

---

## 7. Nodes

Each node is a pure async function `(FilmProjectState) -> dict` returning a partial state
update. No node reads config globals directly — dependencies arrive via closure from
`workflow.py`, which is what lets tests inject fakes.

**`writer_director`** — concept → 3-act structure + scene breakdown, using
`story_frameworks.md` and `screenplay_standards.md`. HEAVY tier. Emits `Scene` objects
with target durations; the sum is validated against `target_duration_sec` and the node
re-asks once if it is off by more than 20%. Duration discipline has to be enforced here
— downstream everything is derived from it, and a 12-minute screenplay for a 90-second
brief is unrecoverable later.

**`casting_bible`** — screenplay → `CharacterProfile` per speaking or featured
character. FLASH tier, JSON. Writes `visual_anchor_description` as one dense immutable
paragraph. Characters with no dialogue are still cast if they appear in two or more
shots — a background figure appearing in three shots will drift without an anchor.

**`cinematographer`** — scenes → `Shot` list with both prompts populated, using
`art_direction.md`, `camera_motion.md`, and `render_artist_style.md` (the Nano Banana
formula). Inherits the render guide's `{scene_label, t2i, i2v}` output contract, extended
with the shot-level fields. On retry entry, receives only the failed shots plus
`qc_feedback` and returns corrections for those shots alone.

**`magnific_render`** — the expensive node. For each shot, in dependency order:
keyframe → (video motion ‖ dialogue voiceovers ‖ sfx). Video and audio have no
dependency on each other, so they run concurrently per shot, under the global semaphore.
Writes `keyframe_url`, `video_url`, `audio_url` back onto the shot.

**`qc_critic`** — inspects rendered artifacts. FLASH vision pass describes what is
actually in each keyframe; HEAVY pass judges it against `visual_action` and the
character's `visual_anchor_description`. Sets `qc_passed` / `qc_notes` per shot and
produces `qc_feedback` for the retry. Critically: QC judges **metadata and frames**, and
explicitly does *not* claim to assess motion smoothness — there is no frame-accurate
video analysis available, and a critic that asserts quality it cannot see is worse than
no critic.

**`assembly`** — builds the timeline (§8), runs the FFmpeg stitch, sets
`final_video_url` and `status="complete"`.

---

## 8. Assembly

**`timeline.py`** emits a Remotion-compatible JSON document — the same structure a
Remotion composition would consume, so the project can be re-cut in Node without
touching Python. It is also the human-readable record of what was built.

**`ffmpeg_stitcher.py`** executes it with `ffmpeg-python`:
- Concat video clips in shot order (`concat` demuxer, stream-copy where codecs match,
  re-encode when they do not)
- Mix per-shot dialogue and SFX stems *against Seedance's native clip audio* (§2.2)
- Loudness normalization to **EBU R128 / -14 LUFS** — the delivery target for web
  platforms, and the difference between a cut that sounds professional and one that
  does not
- Burn no overlays, add no titles. Text rendering is a post step the operator owns.

Output: `data/<project_id>/final.mp4`, plus `timeline.json` and a per-run manifest
recording every prompt and every task id — the audit trail for "why does shot 7 look
like that".

---

## 9. API layer

FastAPI, `backend/app/api/`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/projects` | Create project, start graph run |
| `GET` | `/projects/{id}` | Current state snapshot |
| `GET` | `/projects/{id}/stream` | **SSE** — state deltas as nodes complete |
| `POST` | `/projects/{id}/resume` | Resume from checkpoint after a fix |
| `GET` | `/projects/{id}/timeline` | Remotion JSON |
| `POST` | `/webhooks/magnific` | Task callbacks, HMAC-SHA256 verified |
| `GET` | `/health` | Liveness + Ollama reachability |

SSE rather than WebSocket: the data flow is strictly server→client, and SSE survives
proxies and reconnects with far less ceremony. Reconnect replays from the last
checkpoint.

**Webhook verification.** `MAGNIFIC_WEBHOOK_SECRET` from `.env`; compute HMAC-SHA256
over the raw body, compare with `hmac.compare_digest`. Unsigned or mismatched requests
are rejected 401 before any parsing. Webhooks are an *optimization* — the poller is the
source of truth, so a webhook that never arrives delays nothing.

---

## 10. Config

`backend/app/core/config.py`, Pydantic `BaseSettings`, reads `.env`:

```
MAGNIFIC_API_KEY          required
MAGNIFIC_WEBHOOK_SECRET   optional (webhook verification)
MAGNIFIC_BASE_URL         default https://api.magnific.ai
MAGNIFIC_MAX_CONCURRENCY  default 4
OLLAMA_BASE_URL           default http://127.0.0.1:11434
HEAVY_MODEL               default deepseek-v4.1-pro:cloud
FLASH_MODEL               default deepseek-v4.1-flash:cloud
PROMPTS_DIR               default <repo>/knowledge
DATA_DIR                  default <repo>/data
DEFAULT_ASPECT_RATIO      default 16:9
```

**Secret handling.** `MAGNIFIC_API_KEY` is read from `.env` and nowhere else. It is
never logged, never included in a state snapshot, never returned by the API. A
`SecretStr` field plus a custom log filter enforces this. `.env` is gitignored and stays
that way.

> **Operator action required.** The API key and webhook secret were pasted into a chat
> transcript during design. Both are now outside the secret store. **Rotate both in the
> Magnific dashboard** and put the new values in `.env`. The code is written to read
> from `.env` only, so rotation requires no code change.

---

## 11. Dependencies

`pyproject.toml`, `requires-python = ">=3.11"`:

Runtime: `langgraph`, `langgraph-checkpoint-sqlite`, `fastapi`, `uvicorn[standard]`,
`httpx`, `pydantic>=2`, `pydantic-settings`, `ollama`, `ffmpeg-python`,
`python-multipart`, `sse-starlette`.

Dev: `pytest`, `pytest-asyncio`, `respx`, `ruff`, `mypy`.

`docker-compose.yml` pins **Python 3.12** for the container while local dev is 3.11.9 —
the code targets `>=3.11`, and both are exercised so the floor stays honest.

---

## 12. Testing

TDD throughout, per superpowers:test-driven-development. All graph tests use
`clients/fakes.py` and never touch the network.

| Layer | Approach |
|---|---|
| Schemas | Pydantic validation, rejection of malformed LLM payloads |
| Routing | `route_after_qc` truth table: pass/fail × retries × global cap |
| Shot merge | **Retry must not duplicate shots** — regression test on the reducer |
| Clients | `respx` mocking Magnific: poll sequences, `FAILED`, 429 backoff, timeout, exact URL shape for both Seedance path rules |
| Nodes | Fake providers; assert prompt-assembly invariants (anchor text present verbatim) |
| Assembly | ffmpeg on synthetic 1-second clips; assert duration, stream count, LUFS |
| API | `httpx.ASGITransport`; SSE ordering; webhook HMAC accept + reject |
| E2E | One 3-shot fake-provider run, concept → `final_video_url` |

Two tests earn their keep more than the rest: the **shot-merge regression** (protects the
credit budget against the retry loop) and the **Seedance URL-shape test** (protects
against the §2.1 asymmetry, which is invisible until it 404s in production).

---

## 13. Build order

1. `core/config.py` + `pyproject.toml` + `docker-compose.yml`
2. `graph/state.py` — schemas first, everything depends on them
3. `clients/` — protocols, fakes, then real clients
4. `graph/edges/routing.py` + `graph/workflow.py` — graph wired against fakes
5. Nodes in order: writer_director → casting_bible → cinematographer
6. `magnific_render` + `qc_critic` + retry loop
7. `services/` — timeline, stitcher, assembly node
8. `api/` — FastAPI, SSE, webhooks
9. Port `ui_core.py` and `cli_telegram.py` to call the API

Steps 1–5 are fully testable offline. Step 6 is the first that spends credits, and only
after every fake-provider test is green.

---

## 14. Open decisions for review

1. **Fakes** — resolved above as in-scope and required. Flagging so the reviewer can
   disagree; the alternative (mock at the node boundary instead) makes node tests
   heavier and client tests impossible.
2. **`knowledge/` at root vs. inside the package** — spec keeps it at root for editing
   ergonomics (§3.3). Move it into `backend/app/graph/prompts/` if package
   self-containment matters more.
3. **Legacy deletion timing** — spec keeps legacy files on `main` until the port lands.
   Delete them in the same PR as the port, or keep `legacy01` as the only home?
4. **Credit ceiling** — spec adds `MAX_CONCURRENCY` but no hard credit budget. Should
   `magnific_render` refuse to start if `cost_estimate_credits` exceeds a configured
   cap? Recommended yes, but it needs a real number from the operator.
