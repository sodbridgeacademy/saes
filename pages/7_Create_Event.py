
import uuid
from datetime import date, datetime, time

import pandas as pd
import streamlit as st

from utils.sheets import get_sheets
from utils.data import load_events


st.title("📅 Create Event")

LAGOS_TZ = "Africa/Lagos"

DEFAULT_EVENT_START = time(10, 0)
DEFAULT_EVENT_END = time(12, 0)
DEFAULT_CHECKIN_OPEN = time(10, 0)
DEFAULT_CHECKIN_CLOSE = time(10, 20)

REQUIRED_COLUMNS = {
    "event_id",
    "event_name",
    "type",
    "date",
    "school",
    "created_at",
    "event_start_time",
    "event_end_time",
    "checkin_open_time",
    "checkin_close_time",
    "checkin_opened_at",
    "checkin_expired_at",
    "status",
}


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def now_lagos():
    return pd.Timestamp.now(tz=LAGOS_TZ)


def generate_event_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


def normalize(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def get_header_positions(sheet):
    headers = sheet.row_values(1)
    positions = {}

    for index, header in enumerate(headers, start=1):
        header = normalize(header)
        if header:
            if header in positions:
                raise ValueError(
                    f"Duplicate column header detected: {header}"
                )
            positions[header] = index

    return headers, positions


def get_event_row(sheet, event_id, positions):
    event_ids = sheet.col_values(positions["event_id"])

    for row_number, value in enumerate(event_ids[1:], start=2):
        if normalize(value) == normalize(event_id):
            return row_number

    return None


def update_event_fields(sheet, row_number, positions, values):
    """Update fields using their header names."""
    for column_name, value in values.items():
        if column_name not in positions:
            raise KeyError(f"Missing sheet column: {column_name}")

        sheet.update_cell(
            row_number,
            positions[column_name],
            value,
        )


def event_datetime(event_date, event_time):
    """Create a timezone-aware Africa/Lagos datetime."""
    return pd.Timestamp(
        datetime.combine(event_date, event_time),
        tz=LAGOS_TZ,
    )


def parse_event_date(value):
    value = normalize(value)

    if not value:
        return None

    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError):
        return None


def parse_event_time(value, fallback=None):
    value = normalize(value)

    if not value:
        return fallback

    # Handle standard sheet values such as 10:00 or 10:00:00.
    try:
        return time.fromisoformat(value).replace(
            second=0,
            microsecond=0,
        )
    except ValueError:
        pass

    # Handle spreadsheet values that include a date.
    try:
        return pd.Timestamp(value).time().replace(
            second=0,
            microsecond=0,
        )
    except (TypeError, ValueError):
        return fallback


def get_schedule(event):
    """Return the event date and all four configured times."""
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
        return None

    return {
        "date": event_date,
        "event_start": event_start,
        "event_end": event_end,
        "checkin_open": checkin_open,
        "checkin_close": checkin_close,
    }


def validate_schedule(
    event_start,
    event_end,
    checkin_open,
    checkin_close,
):
    if event_end <= event_start:
        return "The event end time must be later than its start time."

    if checkin_close <= checkin_open:
        return "The check-in closing time must be later than its opening time."

    if checkin_open < event_start:
        return "Check-in cannot open before the event starts."

    if checkin_close > event_end:
        return "Check-in cannot close after the event ends."

    return None


def sync_event_lifecycle(events_sheet, events, positions):
    """
    Synchronize event status and scheduled check-in audit timestamps.

    Event status:
      Scheduled: before event start
      Open: event start reached, event end not reached
      Expired: event end reached

    Check-in audit timestamps record the scheduled boundaries.
    Check-in availability must still be enforced separately
    by the student Check-in page.
    """
    now = now_lagos()
    updated_count = 0

    for _, event in events.iterrows():
        event_id = normalize(event.get("event_id", ""))

        if not event_id:
            continue

        schedule = get_schedule(event)

        # Skip incomplete or invalid schedules.
        if schedule is None:
            continue

        event_date = schedule["date"]
        event_start = schedule["event_start"]
        event_end = schedule["event_end"]
        checkin_open = schedule["checkin_open"]
        checkin_close = schedule["checkin_close"]

        validation_error = validate_schedule(
            event_start,
            event_end,
            checkin_open,
            checkin_close,
        )

        if validation_error:
            continue

        event_start_dt = event_datetime(event_date, event_start)
        event_end_dt = event_datetime(event_date, event_end)
        checkin_open_dt = event_datetime(event_date, checkin_open)
        checkin_close_dt = event_datetime(event_date, checkin_close)

        if now < event_start_dt:
            expected_status = "Scheduled"
        elif now < event_end_dt:
            expected_status = "Open"
        else:
            expected_status = "Expired"

        updates = {}

        current_status = normalize(event.get("status", ""))

        if current_status != expected_status:
            updates["status"] = expected_status

        # Record the scheduled opening boundary once the opening
        # time has been reached. This remains correct if this page
        # runs a little later than the scheduled time.
        opened_at = normalize(event.get("checkin_opened_at", ""))

        if now >= checkin_open_dt and not opened_at:
            updates["checkin_opened_at"] = checkin_open_dt.isoformat()

        # Record the scheduled closing boundary once the closing
        # time has been reached.
        expired_at = normalize(event.get("checkin_expired_at", ""))

        if now >= checkin_close_dt and not expired_at:
            updates["checkin_expired_at"] = checkin_close_dt.isoformat()

        if updates:
            row_number = get_event_row(
                events_sheet,
                event_id,
                positions,
            )

            if row_number is not None:
                update_event_fields(
                    events_sheet,
                    row_number,
                    positions,
                    updates,
                )
                updated_count += 1

    return updated_count


def reload_events():
    load_events.clear()
    return load_events()


# --------------------------------------------------
# Admin authentication
# --------------------------------------------------

if "admin_authenticated" not in st.session_state:
    st.session_state["admin_authenticated"] = False

if not st.session_state["admin_authenticated"]:
    with st.form("admin_login"):
        admin_pass = st.text_input(
            "Enter Admin Password",
            type="password",
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


# --------------------------------------------------
# Load and validate Google Sheets
# --------------------------------------------------

try:
    sheets = get_sheets()
    events_sheet = sheets["events"]
    headers, positions = get_header_positions(events_sheet)

except Exception as exc:
    print(f"SAES event sheet error: {exc}")
    st.error(
        "Unable to access the Events sheet. Please try again."
    )
    st.stop()


missing_columns = REQUIRED_COLUMNS - set(positions)

if missing_columns:
    st.error(
        "The Events sheet is missing these headers: "
        + ", ".join(sorted(missing_columns))
    )
    st.info(
        "Add the missing headers to the first row of the Events "
        "sheet before continuing."
    )
    st.stop()


# --------------------------------------------------
# Synchronize scheduled event lifecycle on page load
# --------------------------------------------------

try:
    events = load_events()

    if not events.empty:
        sync_event_lifecycle(
            events_sheet,
            events,
            positions,
        )
        events = reload_events()

except Exception as exc:
    print(f"SAES lifecycle sync error: {exc}")
    st.warning(
        "Event schedules loaded, but lifecycle synchronization "
        "could not be completed."
    )

    try:
        events = load_events()
    except Exception:
        events = pd.DataFrame()


# --------------------------------------------------
# Create a new event
# --------------------------------------------------

st.subheader("Create a new event")

with st.form("create_event"):
    event_name = st.text_input("Event Name")

    event_type = st.selectbox(
        "Type",
        [
            "DAT",
            "DEV",
            "DSN",
            "CYB",
            "TCD",
            "CHKIN",
            "ORIENTATION",
        ],
    )

    event_date = st.date_input(
        "Event Date",
        value=date.today(),
    )

    st.caption(
        "All times use West Africa Time (WAT), in 24-hour format."
    )

    col1, col2 = st.columns(2)

    with col1:
        planned_event_start = st.time_input(
            "Event starts",
            value=DEFAULT_EVENT_START,
            key="new_event_start",
        )

        planned_checkin_open = st.time_input(
            "Check-in opens",
            value=DEFAULT_CHECKIN_OPEN,
            key="new_checkin_open",
        )

    with col2:
        planned_event_end = st.time_input(
            "Event ends",
            value=DEFAULT_EVENT_END,
            key="new_event_end",
        )

        planned_checkin_close = st.time_input(
            "Check-in closes",
            value=DEFAULT_CHECKIN_CLOSE,
            key="new_checkin_close",
        )

    create = st.form_submit_button(
        "Create Event",
        type="primary",
    )


if create:
    event_name = event_name.strip()

    validation_error = validate_schedule(
        planned_event_start,
        planned_event_end,
        planned_checkin_open,
        planned_checkin_close,
    )

    if not event_name:
        st.error("Event name is required.")

    elif validation_error:
        st.error(validation_error)

    else:
        school = (
            "ALL"
            if event_type in ["TCD", "CHKIN", "ORIENTATION"]
            else event_type
        )

        event_id = generate_event_id(event_type)

        event_start_dt = event_datetime(
            event_date,
            planned_event_start,
        )
        event_end_dt = event_datetime(
            event_date,
            planned_event_end,
        )
        checkin_open_dt = event_datetime(
            event_date,
            planned_checkin_open,
        )
        checkin_close_dt = event_datetime(
            event_date,
            planned_checkin_close,
        )

        now = now_lagos()

        if now < event_start_dt:
            initial_status = "Scheduled"
        elif now < event_end_dt:
            initial_status = "Open"
        else:
            initial_status = "Expired"

        # If an event is created after its check-in window has
        # started or ended, populate the corresponding audit
        # timestamps using the scheduled boundary times.
        checkin_opened_at = (
            checkin_open_dt.isoformat()
            if now >= checkin_open_dt
            else ""
        )

        checkin_expired_at = (
            checkin_close_dt.isoformat()
            if now >= checkin_close_dt
            else ""
        )

        new_event = {
            "event_id": event_id,
            "event_name": event_name,
            "type": event_type,
            "date": str(event_date),
            "school": school,
            "created_at": now.isoformat(),
            "event_start_time": planned_event_start.strftime("%H:%M"),
            "event_end_time": planned_event_end.strftime("%H:%M"),
            "checkin_open_time": planned_checkin_open.strftime("%H:%M"),
            "checkin_close_time": planned_checkin_close.strftime("%H:%M"),
            "checkin_opened_at": checkin_opened_at,
            "checkin_expired_at": checkin_expired_at,
            "status": initial_status,
        }

        try:
            row_values = [
                new_event.get(normalize(header), "")
                for header in headers
            ]

            events_sheet.append_row(row_values)

            reload_events()

            st.success(
                f"Event created successfully: {event_id}"
            )

            st.write(
                f"**Event:** {event_start_dt.strftime('%d %b %Y, %H:%M')}–"
                f"{event_end_dt.strftime('%H:%M')} WAT"
            )

            st.write(
                f"**Check-in:** {checkin_open_dt.strftime('%H:%M')}–"
                f"{checkin_close_dt.strftime('%H:%M')} WAT"
            )

            st.info(
                "The schedule has been saved. Student check-in "
                "availability must be enforced by the Check-in page."
            )

            st.rerun()

        except Exception as exc:
            print(f"SAES create event error: {exc}")
            st.error(
                "The event could not be saved. Check the Events "
                "sheet before retrying to avoid creating a duplicate."
            )


# --------------------------------------------------
# Configure an existing event
# --------------------------------------------------

st.divider()
st.subheader("Configure an existing event")

try:
    events = load_events()
except Exception as exc:
    print(f"SAES event load error: {exc}")
    st.error("Unable to load existing events.")
    st.stop()


if events.empty:
    st.info("No events have been created yet.")
    st.stop()


events = events.copy()
events["event_id"] = events["event_id"].astype(str).str.strip()

event_options = {}

for _, row in events.iterrows():
    event_id = normalize(row.get("event_id", ""))

    if not event_id:
        continue

    event_name = normalize(row.get("event_name", "Unnamed event"))
    event_options[
        f"{event_name} ({event_id})"
    ] = event_id


if not event_options:
    st.info("No valid events are available to configure.")
    st.stop()


selected_label = st.selectbox(
    "Select an event to configure",
    list(event_options.keys()),
    key="configure_event_select",
)

selected_id = event_options[selected_label]

selected_rows = events[
    events["event_id"] == selected_id
]

if selected_rows.empty:
    st.error("Event not found.")
    st.stop()


selected_event = selected_rows.iloc[0]
selected_schedule = get_schedule(selected_event)

if selected_schedule is None:
    st.error(
        "This event has an incomplete or invalid schedule. "
        "Review its date and all four time fields."
    )
    st.stop()


current_status = normalize(
    selected_event.get("status", "")
) or "Not set"

st.write(f"**Event:** {selected_event.get('event_name', '')}")
st.write(f"**Event ID:** {selected_id}")
st.write(f"**School:** {selected_event.get('school', '')}")
st.write(f"**Current status:** {current_status}")

with st.form("configure_event"):
    edited_date = st.date_input(
        "Event Date",
        value=selected_schedule["date"],
        key=f"edit_date_{selected_id}",
    )

    col1, col2 = st.columns(2)

    with col1:
        edited_event_start = st.time_input(
            "Event starts",
            value=selected_schedule["event_start"],
            key=f"edit_event_start_{selected_id}",
        )

        edited_checkin_open = st.time_input(
            "Check-in opens",
            value=selected_schedule["checkin_open"],
            key=f"edit_checkin_open_{selected_id}",
        )

    with col2:
        edited_event_end = st.time_input(
            "Event ends",
            value=selected_schedule["event_end"],
            key=f"edit_event_end_{selected_id}",
        )

        edited_checkin_close = st.time_input(
            "Check-in closes",
            value=selected_schedule["checkin_close"],
            key=f"edit_checkin_close_{selected_id}",
        )

    save_schedule = st.form_submit_button(
        "Save Event Schedule"
    )


if save_schedule:
    validation_error = validate_schedule(
        edited_event_start,
        edited_event_end,
        edited_checkin_open,
        edited_checkin_close,
    )

    if validation_error:
        st.error(validation_error)

    else:
        new_event_start_dt = event_datetime(
            edited_date,
            edited_event_start,
        )
        new_event_end_dt = event_datetime(
            edited_date,
            edited_event_end,
        )
        new_checkin_open_dt = event_datetime(
            edited_date,
            edited_checkin_open,
        )
        new_checkin_close_dt = event_datetime(
            edited_date,
            edited_checkin_close,
        )

        now = now_lagos()

        if now < new_event_start_dt:
            new_status = "Scheduled"
        elif now < new_event_end_dt:
            new_status = "Open"
        else:
            new_status = "Expired"

        try:
            row_number = get_event_row(
                events_sheet,
                selected_id,
                positions,
            )

            if row_number is None:
                st.error(
                    "Could not locate this event in Google Sheets."
                )
                st.stop()

            # Preserve existing audit timestamps when already set.
            # If the schedule is moved to a future window, clear
            # timestamps that no longer describe the new schedule.
            old_opened_at = normalize(
                selected_event.get("checkin_opened_at", "")
            )
            old_expired_at = normalize(
                selected_event.get("checkin_expired_at", "")
            )

            if now < new_checkin_open_dt:
                old_opened_at = ""

            if now < new_checkin_close_dt:
                old_expired_at = ""

            if now >= new_checkin_open_dt and not old_opened_at:
                old_opened_at = new_checkin_open_dt.isoformat()

            if now >= new_checkin_close_dt and not old_expired_at:
                old_expired_at = new_checkin_close_dt.isoformat()

            updates = {
                "date": str(edited_date),
                "event_start_time": edited_event_start.strftime("%H:%M"),
                "event_end_time": edited_event_end.strftime("%H:%M"),
                "checkin_open_time": edited_checkin_open.strftime("%H:%M"),
                "checkin_close_time": edited_checkin_close.strftime("%H:%M"),
                "checkin_opened_at": old_opened_at,
                "checkin_expired_at": old_expired_at,
                "status": new_status,
            }

            update_event_fields(
                events_sheet,
                row_number,
                positions,
                updates,
            )

            reload_events()

            st.success("Event schedule updated successfully.")
            st.rerun()

        except Exception as exc:
            print(f"SAES event configuration error: {exc}")
            st.error(
                "Unable to update the event. Verify the Events sheet."
            )


# --------------------------------------------------
# Display schedule summary
# --------------------------------------------------

st.divider()
st.subheader("Selected Event Schedule")

latest_events = load_events()
latest_rows = latest_events[
    latest_events["event_id"].astype(str).str.strip()
    == selected_id
]

if not latest_rows.empty:
    latest_event = latest_rows.iloc[0]
    latest_schedule = get_schedule(latest_event)

    if latest_schedule:
        st.write(
            f"**Event date:** {latest_schedule['date']}"
        )
        st.write(
            f"**Event time:** "
            f"{latest_schedule['event_start'].strftime('%H:%M')}–"
            f"{latest_schedule['event_end'].strftime('%H:%M')} WAT"
        )
        st.write(
            f"**Check-in window:** "
            f"{latest_schedule['checkin_open'].strftime('%H:%M')}–"
            f"{latest_schedule['checkin_close'].strftime('%H:%M')} WAT"
        )
        st.write(
            f"**Lifecycle status:** "
            f"{normalize(latest_event.get('status', ''))}"
        )

        st.caption(
            "Lifecycle status is synchronized when this page runs. "
            "A scheduled background task is still needed to update "
            "Google Sheets while the app is idle."
        )
