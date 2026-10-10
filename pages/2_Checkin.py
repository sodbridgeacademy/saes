import streamlit as st
import pandas as pd

from utils.sheets import get_sheets
from utils.data import load_students, load_events, load_logs

students = load_students()
events = load_events()
logs = load_logs()

sheets = get_sheets()
logs_sheet = sheets["logs"]

st.title("🎓 Check-in System")

with st.form("checkin"):

    student_id = st.text_input("Student ID")
    event_id = st.selectbox("Event", events["event_id"].tolist())

    participation = st.radio("Participated?", ["Yes", "No"])

    submit = st.form_submit_button("Check In")


if submit:

    # validate student
    if student_id not in students["student_id"].values:
        st.error("Invalid student")
        st.stop()

    # validate event
    if event_id not in events["event_id"].values:
        st.error("Invalid event")
        st.stop()

    # prevent duplicates
    existing = logs[
        (logs["student_id"] == student_id) &
        (logs["event_id"] == event_id)
    ]

    if not existing.empty:
        st.error("Already checked in")
        st.stop()

    # write log (CORRECT SHEET)
    logs_sheet.append_row([
        student_id,
        event_id,
        1,
        1 if participation == "Yes" else 0,
        str(pd.Timestamp.now())
    ])

    st.success("Check-in successful!")

    st.cache_data.clear()
    st.rerun()