
import streamlit as st
import pandas as pd
from datetime import datetime, time

from utils.auth import require_student_login
from utils.sheets import get_sheets
from utils.data import load_students, load_events, load_logs


LAGOS_TZ = "Africa/Lagos"

st.title("🎓 Check-in System")

# Display the confirmation after the page reruns.
if "checkin_success" in st.session_state:
    confirmation = st.session_state.pop("checkin_success")

    st.success("✅ Check-in recorded successfully!")
    st.write(f"**Event:** {confirmation['event_name']}")
    st.write(
        f"**Participation:** {confirmation['participation']}"
    )
    st.caption(
        f"Recorded at {confirmation['timestamp']} WAT"
    )


# --------------------------------------------------
# Require authenticated student
# --------------------------------------------------

# Verifies the logged-in student's account is active
# and returns the canonical student ID from the account sheet.
student_id = require_student_login()

st.caption(f"Checking in as: {student_id}")


# --------------------------------------------------
# Load data
# --------------------------------------------------

try:
    students = load_students()
    events = load_events()
    logs = load_logs()

    sheets = get_sheets()
    logs_sheet = sheets["logs"]

except Exception as exc:
    print(f"SAES check-in loading error: {exc}")
    st.error(
        "Unable to load check-in data. Please check your "
        "connection and try again."
    )
    st.stop()


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def normalize(value):
    """Convert a value to a trimmed string safely."""
    if value is None or pd.isna(value):
        return ""

    return str(value).strip()


def normalize_id(value):
    """Normalize IDs for case-insensitive comparison."""
    return normalize(value).casefold()


def now_lagos():
    """Return the current timezone-aware time in Nigeria."""
    return pd.Timestamp.now(tz=LAGOS_TZ)


def parse_event_date(value):
    """Parse an event date."""
    value = normalize(value)

    if not value:
        return None

    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError):
        return None


def parse_event_time(value):
    """Parse a 24-hour event time."""
    value = normalize(value)

    if not value:
        return None

    try:
        return time.fromisoformat(value).replace(
            second=0,
            microsecond=0,
        )
    except ValueError:
        try:
            return pd.Timestamp(value).time().replace(
                second=0,
                microsecond=0,
            )
        except (TypeError, ValueError):
            return None


def event_datetime(event_date, event_time):
    """Combine a date and time using the Lagos timezone."""
    return pd.Timestamp(
        datetime.combine(event_date, event_time),
        tz=LAGOS_TZ,
    )


def checkin_window(event):
    """
    Validate an event's schedule and return its boundaries.
    The event and check-in window must be on the same day.
    """

    event_date = parse_event_date(event.get("date", ""))

    event_start = parse_event_time(
        event.get("event_start_time", "")
    )
    event_end = parse_event_time(
        event.get("event_end_time", "")
    )
    checkin_open = parse_event_time(
        event.get("checkin_open_time", "")
    )
    checkin_close = parse_event_time(
        event.get("checkin_close_time", "")
    )

    if any(
        value is None
        for value in (
            event_date,
            event_start,
            event_end,
            checkin_open,
            checkin_close,
        )
    ):
        return None, "This event has an incomplete schedule."

    if event_end <= event_start:
        return None, "The event schedule is invalid."

    if checkin_close <= checkin_open:
        return None, "The check-in window is invalid."

    if (
        checkin_open < event_start
        or checkin_close > event_end
    ):
        return (
            None,
            "The check-in window is outside the event duration.",
        )

    return {
        "event_start": event_datetime(
            event_date, event_start
        ),
        "event_end": event_datetime(
            event_date, event_end
        ),
        "checkin_open": event_datetime(
            event_date, checkin_open
        ),
        "checkin_close": event_datetime(
            event_date, checkin_close
        ),
    }, None


def check_time_allowed(window):
    """
    Check the event and check-in boundaries.
    The opening time is inclusive; the closing time is exclusive.
    """

    now = now_lagos()

    if now < window["event_start"]:
        return False, "This event has not started yet."

    if now >= window["event_end"]:
        return False, "This event has ended. Check-in is closed."

    if now < window["checkin_open"]:
        open_time = window["checkin_open"].strftime("%H:%M")
        return (
            False,
            f"Check-in has not opened yet. "
            f"It opens at {open_time} WAT.",
        )

    if now >= window["checkin_close"]:
        close_time = window["checkin_close"].strftime("%H:%M")
        return (
            False,
            f"Check-in closed at {close_time} WAT. "
            "Late check-ins are not accepted.",
        )

    return True, None


# --------------------------------------------------
# Validate data structure
# --------------------------------------------------

required_event_columns = {
    "event_id",
    "date",
    "event_start_time",
    "event_end_time",
    "checkin_open_time",
    "checkin_close_time",
    "type",
}

required_student_columns = {"student_id"}
required_log_columns = {"student_id", "event_id"}

missing_event_columns = (
    required_event_columns - set(events.columns)
)
missing_student_columns = (
    required_student_columns - set(students.columns)
)
missing_log_columns = (
    required_log_columns - set(logs.columns)
)

if missing_event_columns:
    st.error(
        "Events sheet is missing columns: "
        + ", ".join(sorted(missing_event_columns))
    )
    st.stop()

if missing_student_columns:
    st.error(
        "Students data is missing the student_id column."
    )
    st.stop()

if missing_log_columns:
    st.error(
        "Check-in logs are missing columns: "
        + ", ".join(sorted(missing_log_columns))
    )
    st.stop()

if events.empty:
    st.info("There are no events available.")
    st.stop()


# --------------------------------------------------
# Validate the authenticated student
# --------------------------------------------------

# Use the authenticated ID, never an ID entered by the user.
student_id_key = normalize_id(student_id)

valid_student_ids = {
    normalize_id(value)
    for value in students["student_id"]
    if normalize(value)
}

if not student_id_key or student_id_key not in valid_student_ids:
    st.error(
        "Your account could not be matched to the student "
        "records. Please contact the Academy administrator."
    )
    st.stop()


# --------------------------------------------------
# Prepare event options
# --------------------------------------------------

events = events.copy()
events["event_id"] = events["event_id"].map(normalize)

event_options = {}

for _, event in events.iterrows():
    current_event_id = normalize(
        event.get("event_id", "")
    )

    if not current_event_id:
        continue

    event_name = normalize(
        event.get("event_name", "")
    )

    label = (
        f"{event_name} ({current_event_id})"
        if event_name
        else current_event_id
    )

    # Avoid duplicate labels if the sheet contains duplicate IDs.
    if label in event_options:
        label = f"{label} — row {len(event_options) + 1}"

    event_options[label] = current_event_id

if not event_options:
    st.info("There are no valid events available.")
    st.stop()


# --------------------------------------------------
# Check-in form
# --------------------------------------------------

with st.form("checkin"):
    st.caption(f"Student account: {student_id}")

    selected_label = st.selectbox(
        "Event",
        list(event_options.keys()),
    )

    event_id = event_options[selected_label]

    participation = st.radio(
        "Participated?",
        ["Yes", "No"],
    )

    submit = st.form_submit_button("Check In")


# --------------------------------------------------
# Process check-in
# --------------------------------------------------

if submit:

    # ----------------------------------------------
    # Find the selected event
    # ----------------------------------------------

    matching_events = events[
        events["event_id"] == event_id
    ]

    if matching_events.empty:
        st.error("Invalid event.")
        st.stop()

    event = matching_events.iloc[0]

    # ----------------------------------------------
    # Enforce school eligibility
    # ----------------------------------------------

    event_type = normalize(
        event.get("type", "")
    ).upper()

    student_school = student_id.split("-", 1)[0].upper()

    general_event_types = {
        "TCD",
        "CHKIN",
        "ORIENTATION",
    }

    class_event_types = {
        "DAT",
        "DEV",
        "DSN",
        "CYB",
    }

    if event_type in general_event_types:
        # General events are available to all valid students.
        pass

    elif event_type in class_event_types:
        # Event type determines the required school.
        if student_school != event_type:
            st.error(
                f"You are not eligible to check in for this class. "
                f"This event is for {event_type} students "
                f"but you are a student of "
                f"{student_school} school."
            )
            st.stop()

    else:
        st.error(
            "This event has an unrecognized type. "
            "Please contact the Academy Manager."
        )
        st.stop()

    # ----------------------------------------------
    # Validate the event schedule
    # ----------------------------------------------

    window, schedule_error = checkin_window(event)

    if schedule_error:
        st.error(schedule_error)
        st.stop()

    # Check event and check-in boundaries.
    allowed, time_error = check_time_allowed(window)

    if not allowed:
        st.error(time_error)
        st.stop()

    # ----------------------------------------------
    # Refresh logs before duplicate detection
    # ----------------------------------------------

    try:
        logs = load_logs()

    except Exception as exc:
        print(f"SAES log refresh error: {exc}")
        st.error(
            "Unable to verify existing check-ins because of "
            "a connection problem. Please try again."
        )
        st.stop()

    if not {"student_id", "event_id"}.issubset(logs.columns):
        st.error("The check-in log structure is invalid.")
        st.stop()

    # Compare IDs without case sensitivity or surrounding spaces.
    existing = logs[
        (
            logs["student_id"].map(normalize_id)
            == student_id_key
        )
        & (
            logs["event_id"].map(normalize_id)
            == normalize_id(event_id)
        )
    ]

    if not existing.empty:
        st.error(
            "You have already checked in for this event."
        )
        st.stop()

    # ----------------------------------------------
    # Recheck the time immediately before writing
    # ----------------------------------------------

    allowed, time_error = check_time_allowed(window)

    if not allowed:
        st.error(
            f"{time_error} Your check-in was not submitted."
        )
        st.stop()

    # ----------------------------------------------
    # Save the check-in
    # ----------------------------------------------

    # Preserve the existing five-column log format:
    # student_id, event_id, check-in flag,
    # participation flag, timestamp.
    try:
        checkin_timestamp = now_lagos()

        logs_sheet.append_row(
            [
                student_id,
                event_id,
                1,
                1 if participation == "Yes" else 0,
                checkin_timestamp.isoformat(),
            ]
        )

        # Store the confirmation so it survives the rerun.
        st.session_state["checkin_success"] = {
            "event_name": normalize(
                event.get("event_name", event_id)
            ),
            "participation": participation,
            "timestamp": checkin_timestamp.strftime(
                "%d %b %Y, %H:%M:%S"
            ),
        }

        st.cache_data.clear()
        st.rerun()

    except Exception as exc:
        print(f"SAES check-in write error: {exc}")
        st.error(
            "Your check-in could not be confirmed because of a "
            "connection problem. Check your check-in record before "
            "trying again to avoid a duplicate."
        )
