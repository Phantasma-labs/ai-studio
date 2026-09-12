"""
applocal.py — Local entry point for AI Studio.
Run with: streamlit run applocal.py  (or via run_studio.bat)
Shows engine mode selector and local model chooser. No API key field shown.
"""
import streamlit as st
import os
from dotenv import load_dotenv
import ui_core

load_dotenv()

st.set_page_config(page_title="AI Studio (Local)", layout="wide")

if os.path.exists("logo.png"):
    try:
        st.logo("logo.png", size="large")
    except Exception:
        pass

st.title("🎬 Multi-Agent AI Studio")

# --- SIDEBAR: Local configuration ---
st.sidebar.header("⚙️ Configuration")

workflow_mode = st.sidebar.radio(
    "Workflow Mode:",
    ["Storytelling", "Product Shot"],
    help="Storytelling: 3-phase creative pipeline. Product Shot: 1-shot hyper-detailed prompt."
)

engine_mode = st.sidebar.radio(
    "Engine Mode:",
    ["Local", "Cloud"],
    index=0,
    help="Local uses Ollama (offline). Cloud uses Google Gemini."
)

api_key = None

if engine_mode == "Local":
    local_model_selector = st.sidebar.selectbox(
        "Intelligence Engine (Local):",
        ["qwen3-vl:8b", "qwen3.5:9b", "qwen3.5:cloud", "kimi-k2.5:cloud", "gemma4:31b-cloud"],
        index=0
    )
    if "qwen3-vl" in local_model_selector:
        model_name = "qwen3-vl:8b"
    elif "qwen3.5" in local_model_selector:
        model_name = "qwen3.5:cloud" if "cloud" in local_model_selector else "qwen3.5:9b"
    elif "kimi" in local_model_selector:
        model_name = "kimi-k2.5:cloud"
    elif "gemma4" in local_model_selector:
        model_name = "gemma4:31b-cloud"
    else:
        model_name = "gemma4:31b-cloud"
else:
    # Cloud option available from local launcher too
    model_name = "gemini-3.5-flash"
    env_key = os.getenv("GOOGLE_API_KEY")
    key_input = st.sidebar.text_input("Google API Key (leave blank to use .env):", type="password")
    api_key = key_input if key_input else env_key
    if not api_key:
        st.sidebar.warning("Cloud mode requires a Google API Key.")

# --- Hand off to shared workflow UI ---
ui_core.run(engine_mode, model_name, api_key, workflow_mode)
