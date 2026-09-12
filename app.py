"""
app.py — Cloud entry point for AI Studio.
Deployed to Streamlit Community Cloud or any remote server.
Engine is fixed to Google Gemini (gemini-3.5-flash). No local model controls shown.
"""
import streamlit as st
import os
from dotenv import load_dotenv
import ui_core

load_dotenv()

st.set_page_config(page_title="AI Studio", layout="wide")

if os.path.exists("logo.png"):
    try:
        st.logo("logo.png", size="large")
    except Exception:
        pass

# Hide Streamlit chrome (footer, menu, fullscreen button)
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    button[title="View fullscreen"] {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

st.title("🎬 Multi-Agent AI Studio")

# --- SIDEBAR: Cloud configuration only ---
st.sidebar.header("⚙️ Configuration")

workflow_mode = st.sidebar.radio(
    "Workflow Mode:",
    ["Storytelling", "Product Shot"],
    help="Storytelling: 3-phase creative pipeline. Product Shot: 1-shot hyper-detailed prompt."
)

# Fixed engine: Cloud / Gemini 2.5 Flash
engine_mode = "Cloud"
model_name = "gemini-3.5-flash"

env_key = os.getenv("GOOGLE_API_KEY")
key_input = st.sidebar.text_input("Google API Key (leave blank to use .env):", type="password")
api_key = key_input if key_input else env_key

if not api_key:
    st.sidebar.warning("A Google API Key is required.")

# --- Hand off to shared workflow UI ---
ui_core.run(engine_mode, model_name, api_key, workflow_mode)
