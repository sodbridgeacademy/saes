import pandas as pd
import streamlit as st
from utils.sheets import get_sheets

sheets = get_sheets()

@st.cache_data(ttl=60)
def load_students():
    return pd.DataFrame(sheets["students"].get_all_records())

@st.cache_data(ttl=60)
def load_events():
    return pd.DataFrame(sheets["events"].get_all_records())

@st.cache_data(ttl=60)
def load_logs():
    return pd.DataFrame(sheets["logs"].get_all_records())