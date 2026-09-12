# 🎬 Multi-Agent AI Studio

**Live Demo:**  [ai-studio-phantasmalabs.streamlit.app](https://ai-studio-phantasmalabs.streamlit.app/)

**AI Studio** is an experimental multi-agent creative pipeline that translates narrative concepts into structured, production-ready image generation prompts. It uses LLMs as a creative engine — passing a concept through specialized agents (Story Writer, Screenwriter, Art Consultant, Camera Consultant, Render Artist) — and culminating in fully-formed **Nano Banana Pro** T2I and I2V prompts ready for submission to any generative model.

---

## ✨ Features

- **Dual-Engine Architecture**
  - **Cloud Mode**: Powered by `gemini-3.5-flash` via Google GenAI. Auto-selected when deployed remotely — engine and model controls are hidden automatically.
  - **Local Mode**: Runs fully offline via Ollama. Supports `qwen3-vl:8b`, `qwen3.5:9b`, `qwen3.5:cloud`, `kimi-k2.5:cloud`, and `gemma4:31b-cloud`.

- **Workflow Modes**
  - **Storytelling**: A 3-phase pipeline — Pre-Production (story arc + screenplay + art direction) → Cinematography → Production (6-scene T2I + I2V prompts + storyboard consolidation).
  - **Product Shot**: A streamlined 1-shot pipeline that synthesizes a concept directly into a detailed product rendering prompt.

- **Render Artist Output (Nano Banana Pro)**
  The final stage produces rich, narrative-style T2I prompts using the Nano Banana prompting framework — covering subject, lighting, camera, color grading, materiality, and optional I2V animation instructions. No JSON required.

- **Integrated Image Generation**
  - **Local ComfyUI**: Dispatches generation jobs to a running ComfyUI instance (`ZimageRender.json` workflow), polls `/history`, and returns the image directly to the UI.

- **Telegram Bot (CLI)**
  Headless interface for running full campaigns from your phone via `/generate` and `/product` commands.

- **Image Upload**
  Upload a reference image to auto-generate a descriptive concept caption using the vision model.

- **Deliverables Export**
  One-click Markdown export of the full creative pipeline — story arc, screenplay, art/camera direction, final prompts, and storyboard.

---

## 🚀 Installation & Setup

### Prerequisites
1. **Python 3.12**
2. **Google Gemini API Key** (for Cloud mode)
3. **Ollama** installed locally (for Local mode)
4. *(Optional)* **ComfyUI** running on port `8188` (for local image generation)

### 1. Clone & Install
```bash
git clone https://github.com/phantomvfx/ai-studio.git
cd ai-studio

python -m venv venv

# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Environment Variables
Create a `.env` file in the root directory:
```env
GOOGLE_API_KEY=your_genai_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here   # optional
```

For remote/server deployments, set this to hide engine controls automatically:
```env
CLOUD_DEPLOY=true
```

### 3. Run
```bash
# Cloud version (Streamlit Community Cloud / remote server)
streamlit run app.py

# Local version (Ollama + optional ComfyUI)
streamlit run applocal.py

# OR using the Windows batch launcher (runs applocal.py + Telegram bot)
run_studio.bat
```

---

## 📱 Telegram Bot (CLI)

`cli_telegram.py` provides a headless interface to the full pipeline.

1. Create a bot via `@BotFather` on Telegram and copy the HTTP API token.
2. Add `TELEGRAM_BOT_TOKEN` to your `.env` file.
3. Run `python cli_telegram.py` (or via `run_studio.bat`).
4. Commands:
   - `/generate <concept>` — Full storytelling storyboard campaign
   - `/product <concept>` — Single product shot prompt
   - Send an image — Returns a descriptive caption (vision model)

---

## 🔌 Local ComfyUI Integration

1. Launch ComfyUI at `http://127.0.0.1:8188`.
2. Ensure `comfyui/ZimageRender.json` is present.
3. Click **"Generate Local Image (ComfyUI)"** in the UI. The backend injects the prompt, randomizes the seed, and polls `/history` until the image is ready.

---

## 📂 Project Structure

```
ai-studio/
├── app.py                  # ☁️  Cloud entry point (Gemini only, no local controls)
├── applocal.py             # 💻  Local entry point (Ollama + optional Cloud mode)
├── ui_core.py              # Shared workflow UI (Product Shot, Storytelling, session state)
├── pipeline.py             # Agent orchestration, LLM routing, ComfyUI API
├── cli_telegram.py         # Telegram bot (optional)
├── requirements.txt
├── run_studio.bat          # Windows launcher → runs applocal.py + Telegram bot
├── knowledge/
│   ├── story_frameworks.md
│   ├── screenplay_standards.md
│   ├── art_consultant.md
│   ├── art_direction.md
│   ├── camera_consultant.md
│   ├── camera_motion.md
│   ├── render_artist_style.md    # Render Artist prompting guide (Nano Banana)
│   └── product_shot_rules.md
├── comfyui/
│   └── ZimageRender.json         # ComfyUI workflow
└── outputs/                      # Generated .md exports
```

---

## 🛠️ Customization

- **Add Local Models**: Update the `local_model_selector` dropdown in `applocal.py` — it flows automatically into `pipeline.py`.
- **Adjust the Render Artist**: Edit `knowledge/render_artist_style.md` to change prompting style, formula, or vocabulary.
- **Modify Shared Workflow**: Edit `ui_core.py` — changes apply to both cloud and local simultaneously.
- **Cloud Auto-Detection**: `app.py` is always cloud — no env vars needed. For the local launcher, `applocal.py` defaults to Local engine.
