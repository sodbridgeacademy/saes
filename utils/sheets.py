import gspread
from google.oauth2.service_account import Credentials
import streamlit as st


@st.cache_resource
def get_client():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    try:
        gcp_service_account = st.secrets.get("gcp_service_account")
    except (FileNotFoundError, KeyError):
        gcp_service_account = None

    if gcp_service_account:
        creds = Credentials.from_service_account_info(
            dict(gcp_service_account),
            scopes=scope
        )
    else:
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
        "user_accounts": sheet.worksheet("user_accounts"),
        "enrollments": sheet.worksheet("enrollments"),
        "professional_applications": sheet.worksheet(
            "professional_applications"
        ),
        "staff": sheet.worksheet("staff"),
        "events": sheet.worksheet("events"),
        "logs": sheet.worksheet("engagement_logs"),
        "assignments": sheet.worksheet("assignments"),
        "assignment_submissions": sheet.worksheet(
            "assignment_submissions"
        ),
        "cohorts": sheet.worksheet("cohorts"),
        "staff_invitations": sheet.worksheet("staff_invitations"),

    }






