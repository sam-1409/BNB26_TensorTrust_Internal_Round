from dotenv import load_dotenv

load_dotenv()

from PIL import Image
import streamlit as st
from ui.dashboard import main_dashboard
from core.config import BASE_DIR

favicon_path = BASE_DIR / "assets" / "logo.ico"
favicon = Image.open(favicon_path) if favicon_path.exists() else "🛡️"

st.set_page_config(
    page_title="TrustLayers",
    page_icon=favicon,
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={"Get help": None, "Report a bug": None, "About": "TrustLayers investigation workbench"},
)

if __name__ == "__main__":
    main_dashboard()