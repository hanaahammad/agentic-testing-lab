"""Agentic Testing Lab: the console where you drive (or watch) the QA agent test an application.

Pages (menu at the top of the sidebar):
  Start            Welcome: a cartoon of how to use the agent, step by step
  Test activities  Stories · 1 Design · 2 Scripts · 3 Run · 4 Triage & issues · Full cycle · Explore live
  Results          Issues · Artifacts (every run as a versioned, committable folder) · Dashboard

Run locally:   streamlit run streamlit_app.py
Deploy:        Streamlit Community Cloud, main file = streamlit_app.py
"""
import streamlit as st

from console import common, pages

st.set_page_config(page_title="Agentic Testing Lab", page_icon="🧪", layout="wide")
common.init_state()
nav = st.navigation(pages.build())
common.sidebar()
nav.run()
