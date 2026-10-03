import streamlit as st
from ui.dashboard import main_dashboard

st.set_page_config(
    page_title="TrustLayers",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

if __name__ == "__main__":
    main_dashboard()