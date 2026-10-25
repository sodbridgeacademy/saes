
import streamlit as st
import pandas as pd
import uuid
import re

from datetime import timedelta
from utils.data import load_students, load_events
from utils.sheets import get_sheets

st.set_page_config(
    page_title="SAES Admin Dashboard",
    page_icon="🛠️",
    layout="wide"
)

LAGOS_TZ = "Africa/Lagos"
DEFAULT_CHECKIN_MINUTES = 20

# --------------------------------------------------
# ADMIN AUTHENTICATION
# --------------------------------------------------

if "admin_authenticated" not in st.session_state:
    st.session_state["admin_authenticated"] = False

if not st.session_state["admin_authenticated"]:
    st.title("🛠️ SAES Admin Dashboard")
    st.caption("Authorised administrators only.")

    with st.form("admin_login"):
        password = st.text_input(
            "Admin Password",
            type="password"
        )
        submitted = st.form_submit_button("Sign in")

    if submitted:
        try:
            expected_password = st.secrets.get(
                "ADMIN_PASSWORD", ""
            )
        except (FileNotFoundError, KeyError):
            expected_password = ""

        if expected_password and password == expected_password:
            st.session_state["admin_authenticated"] = True
            st.rerun()
        else:
            st.error(
                "Password verification failed. "
                "Check your local Streamlit secrets."
            )

    st.stop()

# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

st.title("🛠️ SAES Admin Dashboard")
st.caption(
    "Manage events, check-in windows and student records."
)

events = load_events().copy()
students = load_students().copy()



sheets = get_sheets()

events_sheet = sheets["events"]
cohorts_sheet = sheets["cohorts"]
invitation_sheet = sheets["staff_invitations"]

# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def now_lagos():
    return pd.Timestamp.now(tz=LAGOS_TZ)


def parse_timestamp(value):
    """Parse a timestamp and interpret naive values as Lagos time."""
    if pd.isna(value) or not str(value).strip():
        return None

    try:
        timestamp = pd.Timestamp(str(value).strip())

        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(LAGOS_TZ)
        else:
            timestamp = timestamp.tz_convert(LAGOS_TZ)

        return timestamp
    except (ValueError, TypeError):
        return None


def effective_status(row):
    """
    Calculate the status displayed in the dashboard.
    The Check-in page must independently enforce the same deadline.
    """
    stored_status = str(row.get("status", "")).strip()
    opened_at = parse_timestamp(
        row.get("checkin_opened_at", "")
    )
    expires_at = parse_timestamp(
        row.get("checkin_expires_at", "")
    )

    if stored_status.lower() == "closed":
        return "Closed"

    if opened_at is None:
        return "Scheduled"

    if expires_at is None:
        return "Check configuration"

    if now_lagos() < opened_at:
        return "Scheduled"

    if now_lagos() < expires_at:
        return "Open"

    return "Expired"


def get_header_positions():
    headers = events_sheet.row_values(1)
    return {
        str(header).strip(): index + 1
        for index, header in enumerate(headers)
        if str(header).strip()
    }


def find_event_sheet_row(event_id, header_positions):
    """Find the actual worksheet row for an event ID."""
    values = events_sheet.get_all_values()
    event_col = header_positions.get("event_id")

    if not event_col:
        return None

    for row_number, row in enumerate(values[1:], start=2):
        if len(row) >= event_col:
            if str(row[event_col - 1]).strip() == str(event_id):
                return row_number

    return None


def update_event_fields(event_id, updates):
    """Update event fields by matching header names."""
    headers = get_header_positions()

    required = {
        "event_id",
        "checkin_opened_at",
        "checkin_expires_at",
        "status",
    }

    missing = required - set(headers)

    if missing:
        raise ValueError(
            "Missing Events sheet columns: "
            + ", ".join(sorted(missing))
        )

    row_number = find_event_sheet_row(event_id, headers)

    if row_number is None:
        raise ValueError(
            f"Could not find event {event_id} in the sheet."
        )

    for column, value in updates.items():
        if column not in headers:
            raise ValueError(
                f"Missing Events sheet column: {column}"
            )

        events_sheet.update_cell(
            row_number,
            headers[column],
            value
        )

    load_events.clear()


# --------------------------------------------------
# COHORT MANAGEMENT HELPERS
# --------------------------------------------------

COHORT_HEADERS = [
    "cohort_id",
    "cohort_name",
    "cohort_code",
    "start_date",
    "end_date",
    "registration_status",
    "created_at",
]


def load_cohort_records():
    """Load cohorts and validate the worksheet structure."""
    headers = cohorts_sheet.row_values(1)

    missing = [
        header for header in COHORT_HEADERS
        if header not in headers
    ]

    if missing:
        raise ValueError(
            "The cohorts worksheet is missing columns: "
            + ", ".join(missing)
        )

    records = cohorts_sheet.get_all_records()

    return pd.DataFrame(records), headers


def update_cohort_status(cohort_id, new_status):
    """Change a cohort's registration status by its ID."""
    headers = {
        str(value).strip(): index + 1
        for index, value in enumerate(
            cohorts_sheet.row_values(1)
        )
        if str(value).strip()
    }

    values = cohorts_sheet.get_all_values()
    id_column = headers["cohort_id"]

    for row_number, row in enumerate(values[1:], start=2):
        if (
            len(row) >= id_column
            and str(row[id_column - 1]).strip()
            == str(cohort_id).strip()
        ):
            cohorts_sheet.update_cell(
                row_number,
                headers["registration_status"],
                new_status,
            )
            return

    raise ValueError("The selected cohort could not be found.")


# --------------------------------------------------
# DASHBOARD SUMMARY
# --------------------------------------------------

if "event_id" in events.columns:
    event_count = events["event_id"].dropna().nunique()
else:
    event_count = 0

if "student_id" in students.columns:
    student_count = students["student_id"].dropna().nunique()
else:
    student_count = 0

if not events.empty and "event_id" in events.columns:
    events["display_status"] = events.apply(
        effective_status, axis=1
    )
    open_count = int(
        events["display_status"].eq("Open").sum()
    )
    scheduled_count = int(
        events["display_status"].eq("Scheduled").sum()
    )
else:
    events["display_status"] = pd.Series(dtype=str)
    open_count = 0
    scheduled_count = 0

m1, m2, m3, m4 = st.columns(4)

m1.metric("Total Events", event_count)
m2.metric("Registered Students", student_count)
m3.metric("Open Check-ins", open_count)
m4.metric("Scheduled Events", scheduled_count)

st.divider()


# --------------------------------------------------
# COHORT MANAGEMENT
# --------------------------------------------------

st.header("🎓 Cohort Management")

try:
    cohorts, cohort_sheet_headers = load_cohort_records()

    if cohorts.empty:
        st.info("No cohorts have been created yet.")

    with st.expander("➕ Create a New Cohort", expanded=cohorts.empty):
        with st.form("create_cohort_form"):
            cohort_name = st.text_input(
                "Cohort Name",
                placeholder="Cohort 5 (November 2026)",
            )

            cohort_code = st.text_input(
                "Unique Cohort Code",
                placeholder="NOV26",
                help="Use a short code such as NOV26 or COH5.",
            )

            start_date = st.date_input("Start Date")

            has_end_date = st.checkbox(
                "Specify an end date",
                value=False,
            )

            # end_date = (
            #     st.date_input("End Date")
            #     if has_end_date
            #     else None
            # )

            end_date = None

            if has_end_date:
                suggested_end_date = (
                    pd.Timestamp(start_date)
                    + pd.DateOffset(weeks=6)
                ).date()

                end_date = st.date_input(
                    "End Date",
                    value=suggested_end_date,
                    key=f"cohort_end_date_{start_date.isoformat()}",
                )

            initial_status = st.selectbox(
                "Registration Status",
                ["Open", "Closed"],
            )

            create_cohort = st.form_submit_button(
                "Create Cohort",
                use_container_width=True,
            )

        if create_cohort:
            clean_name = cohort_name.strip()
            clean_code = cohort_code.strip().upper()

            if not clean_name:
                st.error("Enter a cohort name.")

            elif not re.fullmatch(
                r"[A-Z0-9_-]{2,20}",
                clean_code,
            ):
                st.error(
                    "Use 2–20 letters, numbers, hyphens "
                    "or underscores for the cohort code."
                )

            elif end_date and end_date < start_date:
                st.error(
                    "The end date cannot be earlier than "
                    "the start date."
                )

            else:
                existing_codes = (
                    cohorts["cohort_code"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.upper()
                    .tolist()
                    if "cohort_code" in cohorts.columns
                    else []
                )

                if clean_code in existing_codes:
                    st.error(
                        "That cohort code already exists. "
                        "Choose a different code."
                    )

                else:
                    cohort_data = {
                        "cohort_id": (
                            "COH-" + uuid.uuid4().hex[:12].upper()
                        ),
                        "cohort_name": clean_name,
                        "cohort_code": clean_code,
                        "start_date": start_date.isoformat(),
                        "end_date": (
                            end_date.isoformat()
                            if end_date
                            else ""
                        ),
                        "registration_status": initial_status,
                        "created_at": now_lagos().isoformat(),
                    }

                    new_row = [
                        cohort_data.get(header, "")
                        for header in cohort_sheet_headers
                    ]

                    cohorts_sheet.append_row(
                        new_row,
                        value_input_option="USER_ENTERED",
                    )

                    st.success(
                        f"{clean_name} has been created."
                    )
                    st.rerun()

    st.subheader("Existing Cohorts")

    if cohorts.empty:
        st.caption("Your cohorts will appear here after creation.")

    else:
        st.dataframe(
            cohorts[
                [
                    column for column in [
                        "cohort_name",
                        "cohort_code",
                        "start_date",
                        "end_date",
                        "registration_status",
                    ]
                    if column in cohorts.columns
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        if (
            "cohort_id" in cohorts.columns
            and "cohort_name" in cohorts.columns
            and "cohort_code" in cohorts.columns
            and "registration_status" in cohorts.columns
        ):
            st.subheader("Change Registration Status")

            cohort_options = {
                (
                    f"{row['cohort_name']} "
                    f"({row['cohort_code']})"
                ): str(row["cohort_id"])
                for _, row in cohorts.iterrows()
            }

            selected_cohort_label = st.selectbox(
                "Select a cohort",
                list(cohort_options.keys()),
                key="admin_cohort_selection",
            )

            selected_cohort_id = cohort_options[
                selected_cohort_label
            ]

            selected_cohort = cohorts[
                cohorts["cohort_id"].astype(str)
                == selected_cohort_id
            ].iloc[0]

            current_registration_status = str(
                selected_cohort["registration_status"]
            ).strip().title()

            st.write(
                "Current registration status: "
                f"**{current_registration_status}**"
            )

            if current_registration_status == "Open":
                if st.button(
                    "Close Registration for This Cohort",
                    key="close_cohort_registration",
                ):
                    update_cohort_status(
                        selected_cohort_id,
                        "Closed",
                    )
                    st.success("Cohort registration closed.")
                    st.rerun()

            elif current_registration_status == "Closed":
                if st.button(
                    "Reopen Registration for This Cohort",
                    key="reopen_cohort_registration",
                ):
                    update_cohort_status(
                        selected_cohort_id,
                        "Open",
                    )
                    st.success("Cohort registration reopened.")
                    st.rerun()

            else:
                st.warning(
                    "This cohort has an unrecognised registration "
                    "status. Update it to Open or Closed."
                )

except Exception as exc:
    st.error(
        "Cohort management is temporarily unavailable. "
        "Check the cohorts worksheet headers and try again."
    )
    print(f"SAES cohort management error: {exc}")

st.divider()


# --------------------------------------------------
# TABLE 1: EVENT MANAGEMENT
# --------------------------------------------------

st.header("📅 Events Management")

if events.empty:
    st.info("No events have been created yet.")

elif "event_id" not in events.columns:
    st.error("The Events sheet is missing event_id.")

else:
    display_events = events.copy()

    # Display timestamps in a readable format.
    for column in [
        "checkin_opened_at",
        "checkin_expires_at",
        "created_at",
    ]:
        if column in display_events.columns:
            display_events[column] = display_events[column].apply(
                lambda value: (
                    parse_timestamp(value).strftime(
                        "%Y-%m-%d %H:%M:%S WAT"
                    )
                    if parse_timestamp(value) is not None
                    else "—"
                )
            )

    display_events["Status"] = display_events[
        "display_status"
    ]

    event_columns = [
        column for column in [
            "event_id",
            "event_name",
            "type",
            "school",
            "date",
            "Status",
            "checkin_opened_at",
            "checkin_expires_at",
        ]
        if column in display_events.columns
    ]

    st.dataframe(
        display_events[event_columns],
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Event Actions")

    event_ids = (
        events["event_id"]
        .dropna()
        .astype(str)
        .tolist()
    )

    selected_event_id = st.selectbox(
        "Select an event",
        event_ids,
        format_func=lambda event_id: (
            f"{event_id} — "
            + str(
                events.loc[
                    events["event_id"].astype(str) == event_id,
                    "event_name"
                ].iloc[0]
            )
        )
    )

    selected_rows = events[
        events["event_id"].astype(str) == selected_event_id
    ]

    if not selected_rows.empty:
        selected_event = selected_rows.iloc[0]
        selected_status = effective_status(selected_event)

        st.write(f"Current status: **{selected_status}**")

        # Support an optional duration column if present.
        duration_column = next(
            (
                column for column in [
                    "checkin_duration_minutes",
                    "checkin_duration",
                    "duration_minutes",
                ]
                if column in events.columns
            ),
            None
        )

        duration_minutes = DEFAULT_CHECKIN_MINUTES

        if duration_column:
            try:
                duration_minutes = int(
                    selected_event[duration_column]
                )
                if duration_minutes <= 0:
                    duration_minutes = DEFAULT_CHECKIN_MINUTES
            except (ValueError, TypeError):
                duration_minutes = DEFAULT_CHECKIN_MINUTES

        action_col1, action_col2 = st.columns(2)

        with action_col1:
            open_clicked = st.button(
                "▶️ Open / Reopen Check-in",
                disabled=(selected_status == "Open"),
                use_container_width=True
            )

        with action_col2:
            close_clicked = st.button(
                "⏹️ Close Check-in",
                disabled=(selected_status != "Open"),
                use_container_width=True
            )

        if open_clicked:
            try:
                opened_at = now_lagos()
                expires_at = opened_at + timedelta(
                    minutes=duration_minutes
                )

                update_event_fields(
                    selected_event_id,
                    {
                        "checkin_opened_at": opened_at.isoformat(),
                        "checkin_expires_at": expires_at.isoformat(),
                        "status": "Open",
                    }
                )

                st.success(
                    f"Check-in opened for {selected_event_id}. "
                    f"Window: {duration_minutes} minutes."
                )
                st.rerun()

            except Exception as exc:
                st.error(f"Could not open check-in: {exc}")

        if close_clicked:
            try:
                update_event_fields(
                    selected_event_id,
                    {"status": "Closed"}
                )

                st.success(
                    f"Check-in closed for {selected_event_id}."
                )
                st.rerun()

            except Exception as exc:
                st.error(f"Could not close check-in: {exc}")

st.divider()

# --------------------------------------------------
# TABLE 2: STUDENT MANAGEMENT
# --------------------------------------------------

st.header("👥 Student Management")

if students.empty:
    st.info("No students have registered yet.")

elif "student_id" not in students.columns:
    st.error("The Students sheet is missing student_id.")

else:
    student_view = students.copy()

    # Ensure cohort values are consistently treated as text.
    # This prevents PyArrow from interpreting cohort codes
    # such as "Nov26" as numeric values.
    if "cohort" in student_view.columns:
        student_view["cohort"] = (
            student_view["cohort"]
            .fillna("")
            .astype(str)
        )

    search = st.text_input(
        "Search students",
        placeholder="Student ID, name or email..."
    )

    filter_col1, filter_col2 = st.columns(2)

    if "school" in student_view.columns:
        school_options = ["All"] + sorted(
            student_view["school"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        selected_school = filter_col1.selectbox(
            "Filter by school",
            school_options
        )

        if selected_school != "All":
            student_view = student_view[
                student_view["school"].astype(str)
                == selected_school
            ]

    if "cohort" in student_view.columns:
        cohort_options = ["All"] + sorted(
            student_view["cohort"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        selected_cohort = filter_col2.selectbox(
            "Filter by cohort",
            cohort_options
        )

        if selected_cohort != "All":
            student_view = student_view[
                student_view["cohort"].astype(str)
                == selected_cohort
            ]

    if search.strip():
        searchable_columns = [
            column for column in [
                "student_id",
                "name",
                "email_address",
                "school",
                "cohort",
            ]
            if column in student_view.columns
        ]

        mask = pd.Series(
            False, index=student_view.index
        )

        for column in searchable_columns:
            mask |= student_view[column].astype(str).str.contains(
                search.strip(),
                case=False,
                na=False,
                regex=False
            )

        student_view = student_view[mask]

    preferred_columns = [
        "student_id",
        "name",
        "email_address",
        "school",
        "cohort",
        "created_at",
    ]

    visible_columns = [
        column for column in preferred_columns
        if column in student_view.columns
    ]

    student_view = student_view[visible_columns].rename(
        columns={
            "student_id": "Student ID",
            "name": "Name",
            "email_address": "Email",
            "school": "School",
            "cohort": "Cohort",
            "created_at": "Registered At",
        }
    )

    st.caption(
        f"Showing {len(student_view)} student record(s)."
    )

    st.dataframe(
        student_view,
        use_container_width=True,
        hide_index=True
    )

    # Export only the filtered records displayed above.
    csv_data = student_view.to_csv(index=False).encode("utf-8")

    st.download_button(
        "⬇️ Export displayed student records (CSV)",
        data=csv_data,
        file_name="saes_students.csv",
        mime="text/csv"
    )

# --------------------------------------------------
# FOOTER
# --------------------------------------------------

st.divider()

if st.button("Sign out of Admin"):
    st.session_state["admin_authenticated"] = False
    st.rerun()
