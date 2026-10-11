
import uuid
import pandas as pd
import streamlit as st

from datetime import timedelta
from utils.sheets import get_sheets
from utils.data import load_events

st.title("📅 Create Event")

LAGOS_TZ = "Africa/Lagos"
CHECKIN_DURATION_MINUTES = 20

# --- Admin authentication ---
if "admin_authenticated" not in st.session_state:
    st.session_state["admin_authenticated"] = False

if not st.session_state["admin_authenticated"]:
    with st.form("admin_login"):
        admin_pass = st.text_input(
            "Enter Admin Password",
            type="password"
        )
        login = st.form_submit_button("Login")

    if login:
        expected_password = st.secrets.get("ADMIN_PASSWORD", "")

        if expected_password and admin_pass == expected_password:
            st.session_state["admin_authenticated"] = True
            st.rerun()
        else:
            st.error("Invalid admin password")

    st.stop()

sheets = get_sheets()
events_sheet = sheets["events"]
events = load_events()

required_columns = {
    "event_id",
    "event_name",
    "type",
    "date",
    "school",
    "created_at",
    "checkin_opened_at",
    "checkin_expires_at",
    "status",
}

if not required_columns.issubset(set(events.columns)):
    st.error(
        "Update the Events sheet headers first. "
        "Add checkin_opened_at, checkin_expires_at, "
        "and status after the existing columns."
    )
    st.stop()


def generate_event_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


def now_lagos():
    return pd.Timestamp.now(tz=LAGOS_TZ)


def get_header_positions():
    headers = events_sheet.row_values(1)
    return {name: index + 1 for index, name in enumerate(headers)}


# --- Create event ---
st.subheader("Create a new event")

with st.form("create_event"):
    event_name = st.text_input("Event Name")

    event_type = st.selectbox(
        "Type",
        ["DAT", "DEV", "DSN", "CYB", "TCD", "CHKIN"]
    )

    event_date = st.date_input("Event Date")

    create = st.form_submit_button("Create Event")

if create:
    event_name = event_name.strip()

    if not event_name:
        st.error("Event name is required.")
    else:
        school = (
            "ALL"
            if event_type in ["TCD", "CHKIN"]
            else event_type
        )

        event_id = generate_event_id(event_type)

        new_event = [
            event_id,
            event_name,
            event_type,
            str(event_date),
            school,
            now_lagos().isoformat(),
            "",             # checkin_opened_at
            "",             # checkin_expires_at
            "Scheduled",
        ]

        events_sheet.append_row(new_event)

        load_events.clear()
        st.success(
            f"Event created: {event_id}. "
            "Check-in has not started yet."
        )
        st.rerun()


# --- Open check-in ---
st.divider()
st.subheader("Open student check-in")

events = load_events()

if events.empty:
    st.info("No events have been created yet.")
    st.stop()

event_options = {
    f"{row['event_name']} ({row['event_id']})": row["event_id"]
    for _, row in events.iterrows()
}

selected_label = st.selectbox(
    "Select the event to open",
    list(event_options.keys())
)
selected_id = event_options[selected_label]

selected_rows = events[
    events["event_id"].astype(str) == str(selected_id)
]

if selected_rows.empty:
    st.error("Event not found.")
    st.stop()

selected_event = selected_rows.iloc[0]
current_status = str(selected_event.get("status", "")).strip()

st.write(f"**Event:** {selected_event['event_name']}")
st.write(f"**School:** {selected_event['school']}")
st.write(f"**Status:** {current_status or 'Not set'}")

if current_status == "Open":
    expiry_value = str(
        selected_event.get("checkin_expires_at", "")
    ).strip()

    if expiry_value:
        expiry = pd.Timestamp(expiry_value)

        if expiry.tzinfo is None:
            expiry = expiry.tz_localize(LAGOS_TZ)

        if now_lagos() < expiry:
            st.warning(
                f"Check-in is already open until "
                f"{expiry.strftime('%H:%M:%S')} WAT."
            )
            st.stop()

        st.info("The previous check-in window has expired.")
    else:
        st.warning(
            "This event is marked Open but has no expiry time. "
            "Verify the event record before reopening it."
        )
        st.stop()

if st.button("Open 20-Minute Check-in", type="primary"):
    headers = get_header_positions()

    row_matches = events_sheet.col_values(
        headers["event_id"]
    )

    try:
        sheet_row = row_matches.index(str(selected_id)) + 1
    except ValueError:
        st.error("Could not locate this event in the Google Sheet.")
        st.stop()

    opened_at = now_lagos()
    expires_at = opened_at + timedelta(
        minutes=CHECKIN_DURATION_MINUTES
    )

    events_sheet.update_cell(
        sheet_row, headers["checkin_opened_at"],
        opened_at.isoformat()
    )
    events_sheet.update_cell(
        sheet_row, headers["checkin_expires_at"],
        expires_at.isoformat()
    )
    events_sheet.update_cell(
        sheet_row, headers["status"], "Open"
    )

    load_events.clear()

    st.success(
        f"Check-in opened for {selected_id}. "
        f"It expires at {expires_at.strftime('%H:%M:%S')} WAT."
    )
    st.rerun()
