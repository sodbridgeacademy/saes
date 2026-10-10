import streamlit as st
import pandas as pd
import uuid

from utils.sheets import get_sheets
from utils.data import load_events

events = load_events()
events_sheet = get_sheets()["events"]

st.title("📅 Create Event")

admin_pass = st.text_input("Enter Admin Password", type="password")

if admin_pass != "Sodbridge3210":
    st.warning("Admin access required")
    st.stop()

def generate_event_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

with st.form("create_event"):

    event_name = st.text_input("Event Name")

    event_type = st.selectbox(
        "Type",
        ["DAT", "DEV", "DSN", "CYB", "TCD", "CHKIN"]
    )

    date = st.date_input("Date")

    submit = st.form_submit_button("Create Event")


if submit:

    # basic validation
    if not event_name:
        st.error("Event name required")
        st.stop()

    # assign school
    school = event_type
    if event_type in ["TCD", "CHKIN"]:
        school = "ALL"

    event_id = generate_event_id(event_type)

    new_event = [
        event_id,
        event_name,
        event_type,
        str(date),
        school,
        str(pd.Timestamp.now())
    ]

    events_sheet.append_row(new_event)

    # st.success(f"Event created: {event_id}")

    # STORE MESSAGE
    st.session_state["event_created"] = event_id

    st.cache_data.clear()
    st.rerun()


# SHOW MESSAGE AFTER RERUN
if "event_created" in st.session_state:
    st.success(f"Event created: {st.session_state['event_created']}")
    del st.session_state["event_created"]

    # refresh cache so it appears immediately in check-in
    st.cache_data.clear()
    st.rerun()



    