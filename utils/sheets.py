import gspread
from google.oauth2.service_account import Credentials
import streamlit as st

@st.cache_resource
def get_client():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_file(
        "service_account.json",
        scopes=scope
    )

    return gspread.authorize(creds)


@st.cache_resource
def get_sheets():
    client = get_client()
    sheet = client.open_by_key("1YT7TAFGOgD5GQll8c4KNUQEsc8kWGfBMVl7chyvVngo")

    return {
        "students": sheet.worksheet("students"),
        "events": sheet.worksheet("events"),
        "logs": sheet.worksheet("engagement_logs")
    }
