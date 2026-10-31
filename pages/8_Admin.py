
import streamlit as st
import pandas as pd
import uuid
import re

from datetime import timedelta
from utils.data import load_students, load_events, load_school_records, load_staff_records
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
# SCHOOL VALIDATION HELPER
# --------------------------------------------------

def get_active_school(schools_sheet, school_id):
    school_id = str(school_id).strip()

    if not school_id:
        return None

    records = schools_sheet.get_all_records()

    matches = [
        row for row in records
        if str(row.get("school_id", "")).strip() == school_id
    ]

    # Reject missing or duplicate school IDs.
    if len(matches) != 1:
        return None

    school = matches[0]

    if str(school.get("status", "")).strip().lower() != "active":
        return None

    if not str(school.get("school_name", "")).strip():
        return None

    return school



# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

st.title("🛠️ SAES Admin Dashboard")
st.caption(
    "Manage events, check-in windows and student records."
)

sheets = get_sheets()

events_sheet = sheets["events"]
cohorts_sheet = sheets["cohorts"]
invitation_sheet = sheets["staff_invitations"]
schools_sheet = sheets["schools"]
staff_sheet = sheets["staff"]
user_accounts_sheet = sheets["user_accounts"]

events = load_events().copy()
students = load_students().copy()
staff_records = load_staff_records().copy()
school_records = load_school_records().copy()


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
# SCHOOL AND STAFF MANAGEMENT HELPERS
# --------------------------------------------------

SCHOOL_HEADERS = [
    "school_id",
    "school_name",
    "status",
    "created_at",
    "updated_at",
]

STAFF_MANAGEMENT_HEADERS = [
    "staff_id",
    "user_id",
    "full_name",
    "email_address",
    "username",
    "role",
    "status",
    "created_at",
    "created_by",
    "school_id",
]


def validate_sheet_headers(sheet, required_headers, sheet_name):
    headers = [
        str(value).strip()
        for value in sheet.row_values(1)
    ]

    missing = [
        header
        for header in required_headers
        if header not in headers
    ]

    if missing:
        raise ValueError(
            f"{sheet_name} is missing columns: "
            + ", ".join(missing)
        )

    return headers


def update_record_by_id(
    sheet,
    id_column,
    record_id,
    updates,
    sheet_name,
):
    """Update a worksheet record by ID, using header names."""
    headers = validate_sheet_headers(
        sheet,
        [id_column],
        sheet_name,
    )

    positions = {
        header: index + 1
        for index, header in enumerate(headers)
    }

    for column in updates:
        if column not in positions:
            raise ValueError(
                f"{sheet_name} is missing column: {column}"
            )

    values = sheet.get_all_values()
    id_position = positions[id_column] - 1
    matches = []

    for row_number, row in enumerate(values[1:], start=2):
        value = (
            row[id_position]
            if id_position < len(row)
            else ""
        )

        if str(value).strip() == str(record_id).strip():
            matches.append(row_number)

    if len(matches) != 1:
        raise ValueError(
            f"Expected one matching record in {sheet_name}; "
            f"found {len(matches)}."
        )

    row_number = matches[0]

    for column, value in updates.items():
        sheet.update_cell(
            row_number,
            positions[column],
            value,
        )


def load_school_records():
    validate_sheet_headers(
        schools_sheet,
        SCHOOL_HEADERS,
        "schools",
    )

    records = schools_sheet.get_all_records(
        default_blank="",
    )

    return pd.DataFrame(
        records,
        columns=SCHOOL_HEADERS,
    )


def load_staff_records():
    validate_sheet_headers(
        staff_sheet,
        STAFF_MANAGEMENT_HEADERS,
        "staff",
    )

    return pd.DataFrame(
        staff_sheet.get_all_records(
            default_blank="",
        )
    )



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

# Count active instructors
try:

    if (
        not staff_records.empty
        and {"staff_id", "role", "status"}.issubset(
            staff_records.columns
        )
    ):
        instructor_count = staff_records[
            staff_records["role"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
            .eq("instructor")
            &
            staff_records["status"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
            .eq("active")
        ]["staff_id"].nunique()
    else:
        instructor_count = 0

except Exception as exc:
    instructor_count = 0
    print(f"SAES instructor count error: {exc}")



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

m1, m2, m3, m4, m5 = st.columns(5)

m1.metric("Total Events", event_count)
m2.metric("Registered Students", student_count)
m3.metric("Total Instructors", instructor_count)
m4.metric("Open Check-ins", open_count)
m5.metric("Scheduled Events", scheduled_count)

st.divider()



# --------------------------------------------------
# SCHOOL MANAGEMENT
# --------------------------------------------------

st.header("🏫 School Management")

try:
    school_records = load_school_records()

    with st.expander("➕ Add a School", expanded=False):
        with st.form("admin_add_school_form"):
            new_school_name = st.text_input(
                "School name",
                placeholder="Enter the official school name",
                max_chars=150,
            )

            add_school = st.form_submit_button(
                "Add School",
                use_container_width=True,
            )

        if add_school:
            clean_name = new_school_name.strip()

            if not clean_name:
                st.error("Enter a school name.")

            elif (
                not school_records.empty
                and school_records["school_name"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.casefold()
                .eq(clean_name.casefold())
                .any()
            ):
                st.error(
                    "A school with this name already exists."
                )

            else:
                now = now_lagos().isoformat()

                school_record = {
                    "school_id": (
                        "SCH-" + uuid.uuid4().hex[:12].upper()
                    ),
                    "school_name": clean_name,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }

                headers = [
                    str(value).strip()
                    for value in schools_sheet.row_values(1)
                ]

                schools_sheet.append_row(
                    [
                        school_record.get(header, "")
                        for header in headers
                    ],
                    value_input_option="RAW",
                )

                st.success(
                    f"{clean_name} has been added."
                )
                st.rerun()

    st.subheader("Registered Schools")

    if school_records.empty:
        st.info("No schools have been added yet.")

    else:
        st.dataframe(
            school_records[
                [
                    column
                    for column in [
                        "school_id",
                        "school_name",
                        "status",
                        "created_at",
                        "updated_at",
                    ]
                    if column in school_records.columns
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        school_options = {
            (
                f"{row['school_name']} "
                f"({row['school_id']})"
            ): str(row["school_id"])
            for _, row in school_records.iterrows()
        }

        selected_school_label = st.selectbox(
            "Select a school to manage",
            list(school_options.keys()),
            key="manage_school_selection",
        )

        selected_school_id = school_options[
            selected_school_label
        ]

        selected_school_row = school_records[
            school_records["school_id"].astype(str)
            == selected_school_id
        ].iloc[0]

        current_school_status = str(
            selected_school_row["status"]
        ).strip().lower()


        # Edit school details
        with st.expander("✏️ Edit School Details", expanded=False):
            with st.form("admin_edit_school_form"):
                edited_school_name = st.text_input(
                    "School name",
                    value=str(
                        selected_school_row.get("school_name", "")
                    ).strip(),
                    max_chars=150,
                )

                save_school = st.form_submit_button(
                    "Save School Changes",
                    use_container_width=True,
                )

            if save_school:
                clean_name = edited_school_name.strip()

                if not clean_name:
                    st.error("School name cannot be empty.")

                else:
                    duplicate_name = (
                        school_records["school_name"]
                        .fillna("")
                        .astype(str)
                        .str.strip()
                        .str.casefold()
                        .eq(clean_name.casefold())
                        & school_records["school_id"]
                        .astype(str)
                        .str.strip()
                        .ne(selected_school_id)
                    ).any()

                    if duplicate_name:
                        st.error(
                            "Another school already uses this name."
                        )
                    elif clean_name == str(
                        selected_school_row["school_name"]
                    ).strip():
                        st.info("No changes to save.")
                    else:
                        update_record_by_id(
                            schools_sheet,
                            "school_id",
                            selected_school_id,
                            {
                                "school_name": clean_name,
                                "updated_at": now_lagos().isoformat(),
                            },
                            "schools",
                        )

                        st.success("School details updated.")
                        st.rerun()


        if current_school_status == "active":
            if st.button(
                "Deactivate School",
                key="deactivate_school",
            ):
                update_record_by_id(
                    schools_sheet,
                    "school_id",
                    selected_school_id,
                    {
                        "status": "inactive",
                        "updated_at": now_lagos().isoformat(),
                    },
                    "schools",
                )

                st.success(
                    "School deactivated. Its records have not been deleted."
                )
                st.rerun()

        elif current_school_status == "inactive":
            if st.button(
                "Reactivate School",
                key="reactivate_school",
            ):
                update_record_by_id(
                    schools_sheet,
                    "school_id",
                    selected_school_id,
                    {
                        "status": "active",
                        "updated_at": now_lagos().isoformat(),
                    },
                    "schools",
                )

                st.success("School reactivated.")
                st.rerun()

        else:
            st.warning(
                "This school has an unrecognised status. "
                "Review the worksheet before changing it."
            )

except Exception as exc:
    st.error(
        "School management is unavailable. "
        "Check the schools worksheet headers and permissions."
    )
    print(f"SAES school management error: {exc}")

st.divider()



# --------------------------------------------------
# STAFF MANAGEMENT
# --------------------------------------------------

st.header("👩‍🏫 Staff Management")

try:
    if staff_records.empty:
        st.info("No staff records have been registered yet.")

    else:
        staff_view = staff_records.copy()

        for column in [
            "full_name",
            "email_address",
            "username",
            "role",
            "status",
            "school_id",
        ]:
            if column in staff_view.columns:
                staff_view[column] = (
                    staff_view[column]
                    .fillna("")
                    .astype(str)
                )

        search_staff = st.text_input(
            "Search staff",
            placeholder="Name, email, username or staff ID...",
            key="admin_staff_search",
        )

        staff_filter_col1, staff_filter_col2 = st.columns(2)

        role_options = ["All"] + sorted(
            staff_view["role"].str.lower().unique().tolist()
        )

        selected_staff_role = staff_filter_col1.selectbox(
            "Filter by role",
            role_options,
            key="admin_staff_role_filter",
        )

        school_lookup = {}

        try:
            current_schools = load_school_records()

            school_lookup = {
                str(row["school_id"]).strip():
                str(row["school_name"]).strip()
                for _, row in current_schools.iterrows()
            }

        except Exception:
            pass

        staff_school_labels = {
            "All": "All",
            "Unassigned": "Unassigned",
        }

        for school_id, school_name in school_lookup.items():
            staff_school_labels[
                f"{school_name} ({school_id})"
            ] = school_id

        selected_staff_school_label = (
            staff_filter_col2.selectbox(
                "Filter by school",
                list(staff_school_labels.keys()),
                key="admin_staff_school_filter",
            )
        )

        selected_staff_school = staff_school_labels[
            selected_staff_school_label
        ]

        if selected_staff_role != "All":
            staff_view = staff_view[
                staff_view["role"].str.lower()
                == selected_staff_role
            ]

        if selected_staff_school == "Unassigned":
            staff_view = staff_view[
                staff_view["school_id"].str.strip() == ""
            ]

        elif selected_staff_school != "All":
            staff_view = staff_view[
                staff_view["school_id"].str.strip()
                == selected_staff_school
            ]

        if search_staff.strip():
            searchable = [
                column
                for column in [
                    "staff_id",
                    "full_name",
                    "email_address",
                    "username",
                ]
                if column in staff_view.columns
            ]

            mask = pd.Series(
                False,
                index=staff_view.index,
            )

            for column in searchable:
                mask |= staff_view[column].str.contains(
                    search_staff.strip(),
                    case=False,
                    na=False,
                    regex=False,
                )

            staff_view = staff_view[mask]

        staff_display = staff_view.copy()

        staff_display["school_name"] = (
            staff_display["school_id"]
            .map(school_lookup)
            .fillna("")
        )

        st.caption(
            f"Showing {len(staff_display)} staff record(s)."
        )

        display_columns = [
            column
            for column in [
                "staff_id",
                "full_name",
                "email_address",
                "username",
                "role",
                "status",
                "school_name",
                "school_id",
            ]
            if column in staff_display.columns
        ]

        st.dataframe(
            staff_display[display_columns],
            use_container_width=True,
            hide_index=True,
        )

        staff_options = {
            (
                f"{row['full_name']} — "
                f"{row['role']} — {row['staff_id']}"
            ): str(row["staff_id"])
            for _, row in staff_records.iterrows()
        }

        selected_staff_label = st.selectbox(
            "Select a staff member",
            list(staff_options.keys()),
            key="admin_staff_selection",
        )

        selected_staff_id = staff_options[
            selected_staff_label
        ]

        selected_staff = staff_records[
            staff_records["staff_id"].astype(str)
            == selected_staff_id
        ].iloc[0]

        current_staff_status = str(
            selected_staff["status"]
        ).strip().lower()

        st.write(
            f"**Role:** {selected_staff['role']}"
        )

        selected_staff_school_id = str(
            selected_staff.get("school_id", "")
        ).strip()


        # Edit staff details
        with st.expander("✏️ Edit Staff Details", expanded=False):
            active_schools = load_school_records()

            if not active_schools.empty:
                active_schools = active_schools[
                    active_schools["status"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.lower()
                    .eq("active")
                ]

            school_choices = {"Unassigned": ""}

            for _, school_row in active_schools.iterrows():
                sid = str(school_row["school_id"]).strip()
                sname = str(school_row["school_name"]).strip()

                school_choices[f"{sname} ({sid})"] = sid

            # Retain the current school option if it is inactive.
            # This lets the admin reassign the staff member to an
            # active school instead of silently changing the value.
            if (
                selected_staff_school_id
                and selected_staff_school_id not in school_choices.values()
            ):
                current_name = school_lookup.get(
                    selected_staff_school_id,
                    selected_staff_school_id,
                )
                school_choices[
                    f"{current_name} ({selected_staff_school_id}) — current"
                ] = selected_staff_school_id

            school_labels = list(school_choices.keys())

            current_school_label = next(
                (
                    label
                    for label, sid in school_choices.items()
                    if sid == selected_staff_school_id
                ),
                "Unassigned",
            )

            role_choices = ["instructor", "admin"]
            current_role = str(selected_staff["role"]).strip().lower()

            if current_role not in role_choices:
                role_choices.append(current_role)

            with st.form("admin_edit_staff_form"):
                edited_full_name = st.text_input(
                    "Full name",
                    value=str(
                        selected_staff.get("full_name", "")
                    ).strip(),
                )

                edited_email = st.text_input(
                    "Email address",
                    value=str(
                        selected_staff.get("email_address", "")
                    ).strip(),
                )

                edited_username = st.text_input(
                    "Username",
                    value=str(
                        selected_staff.get("username", "")
                    ).strip(),
                )

                edited_role = st.selectbox(
                    "Role",
                    role_choices,
                    index=role_choices.index(current_role),
                )

                edited_school_label = st.selectbox(
                    "Assigned school",
                    school_labels,
                    index=school_labels.index(current_school_label),
                )

                save_staff = st.form_submit_button(
                    "Save Staff Changes",
                    use_container_width=True,
                )

            if save_staff:
                clean_name = edited_full_name.strip()
                clean_email = edited_email.strip().lower()
                clean_username = edited_username.strip()
                clean_role = edited_role.strip().lower()
                new_school_id = school_choices[edited_school_label]

                if not clean_name:
                    st.error("Full name cannot be empty.")

                elif not clean_email or "@" not in clean_email:
                    st.error("Enter a valid email address.")

                elif not clean_username:
                    st.error("Username cannot be empty.")

                elif clean_role not in role_choices:
                    st.error("Select a valid role.")

                else:
                    # Check uniqueness against other staff records.
                    other_staff = staff_records[
                        staff_records["staff_id"].astype(str)
                        != selected_staff_id
                    ].copy()

                    duplicate_email = (
                        other_staff["email_address"]
                        .fillna("")
                        .astype(str)
                        .str.strip()
                        .str.casefold()
                        .eq(clean_email.casefold())
                    ).any()

                    duplicate_username = (
                        other_staff["username"]
                        .fillna("")
                        .astype(str)
                        .str.strip()
                        .str.casefold()
                        .eq(clean_username.casefold())
                    ).any()

                    if duplicate_email:
                        st.error(
                            "Another staff member already uses this email."
                        )

                    elif duplicate_username:
                        st.error(
                            "Another staff member already uses this username."
                        )

                    else:
                        # Validate the selected school against the live sheet.
                        if new_school_id:

                            school_matches = school_records[
                                school_records["school_id"]
                                .fillna("")
                                .astype(str)
                                .str.strip()
                                .eq(new_school_id)
                            ]

                            live_school = (
                                not school_matches.empty
                                and len(school_matches) == 1
                                and str(
                                    school_matches.iloc[0]["status"]
                                ).strip().lower() == "active"
                                and bool(
                                    str(
                                        school_matches.iloc[0]["school_name"]
                                    ).strip()
                                )
                            )

                            if not live_school:
                                st.error(
                                    "The selected school is no longer active. "
                                    "Refresh and select an active school."
                                )
                                st.stop()

                        user_id = str(
                            selected_staff.get("user_id", "")
                        ).strip()

                        if not user_id:
                            st.error(
                                "This staff record has no user_id. "
                                "No changes were saved."
                            )
                            st.stop()

                        old_staff_values = {
                            "full_name": str(
                                selected_staff.get("full_name", "")
                            ).strip(),
                            "email_address": str(
                                selected_staff.get("email_address", "")
                            ).strip(),
                            "username": str(
                                selected_staff.get("username", "")
                            ).strip(),
                            "role": current_role,
                            "school_id": selected_staff_school_id,
                        }

                        new_staff_values = {
                            "full_name": clean_name,
                            "email_address": clean_email,
                            "username": clean_username,
                            "role": clean_role,
                            "school_id": new_school_id,
                        }

                        try:
                            # Update the staff record first.
                            update_record_by_id(
                                staff_sheet,
                                "staff_id",
                                selected_staff_id,
                                new_staff_values,
                                "staff",
                            )

                            try:
                                # Keep the linked login record consistent.
                                update_record_by_id(
                                    user_accounts_sheet,
                                    "user_id",
                                    user_id,
                                    {
                                        "email_address": clean_email,
                                        "role": clean_role,
                                    },
                                    "user_accounts",
                                )

                            except Exception:
                                # Roll back the staff record if the
                                # linked account update fails.
                                update_record_by_id(
                                    staff_sheet,
                                    "staff_id",
                                    selected_staff_id,
                                    old_staff_values,
                                    "staff",
                                )
                                raise

                            st.success(
                                "Staff details updated successfully."
                            )
                            st.rerun()

                        except Exception as exc:
                            st.error(
                                "Could not save the staff changes. "
                                "Check the staff and user_accounts worksheets."
                            )
                            print(
                                f"SAES staff edit error: {exc}"
                            )

        st.write(
            "**Assigned school:** "
            + school_lookup.get(
                selected_staff_school_id,
                "Not assigned",
            )
        )

        if current_staff_status == "active":
            if st.button(
                "Deactivate Staff Account",
                key="deactivate_staff_account",
            ):
                user_id = str(
                    selected_staff["user_id"]
                ).strip()

                # Update both staff and authentication records.
                # Login must reject accounts whose status is inactive.
                update_record_by_id(
                    staff_sheet,
                    "staff_id",
                    selected_staff_id,
                    {"status": "inactive"},
                    "staff",
                )

                try:
                    update_record_by_id(
                        user_accounts_sheet,
                        "user_id",
                        user_id,
                        {"account_status": "inactive"},
                        "user_accounts",
                    )

                except Exception:
                    # Avoid leaving the staff record inactive
                    # while its login account remains active.
                    update_record_by_id(
                        staff_sheet,
                        "staff_id",
                        selected_staff_id,
                        {"status": "active"},
                        "staff",
                    )
                    raise

                st.success(
                    "Staff and login account deactivated."
                )
                st.rerun()

        elif current_staff_status == "inactive":
            if st.button(
                "Reactivate Staff Account",
                key="reactivate_staff_account",
            ):
                user_id = str(
                    selected_staff["user_id"]
                ).strip()

                update_record_by_id(
                    user_accounts_sheet,
                    "user_id",
                    user_id,
                    {"account_status": "active"},
                    "user_accounts",
                )

                try:
                    update_record_by_id(
                        staff_sheet,
                        "staff_id",
                        selected_staff_id,
                        {"status": "active"},
                        "staff",
                    )

                except Exception:
                    update_record_by_id(
                        user_accounts_sheet,
                        "user_id",
                        user_id,
                        {"account_status": "inactive"},
                        "user_accounts",
                    )
                    raise

                st.success(
                    "Staff and login account reactivated."
                )
                st.rerun()

        else:
            st.warning(
                "This staff member has an unrecognised status. "
                "Review the staff worksheet before changing it."
            )

# except Exception as exc:
#     st.error(
#         "Staff management is unavailable. "
#         "Check the staff and user_accounts worksheet headers "
#         "and permissions."
#     )

except Exception as exc:
    st.error(f"Staff management error: {exc}")
    st.exception(exc)

    print(f"SAES staff management error: {exc}")

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

students_sheet = sheets["students"]

STUDENT_STATUSES = [
    "active",
    "inactive",
    "suspended",
    "graduated",
]

STUDENT_PROGRAMME_TYPE = ["foundations", "professional"]

STUDENT_CATEGORY = ["audit", "certified"]

if students.empty:
    st.info("No students have registered yet.")

elif "student_id" not in students.columns:
    st.error("The Students sheet is missing student_id.")

elif "status" not in students.columns:
    st.error(
        "The Students sheet is missing the status column. "
        "Add status to row 1 of the worksheet and backfill "
        "existing students with active or inactive."
    )

elif "programme_type" not in students.columns:
    st.error(
        "The Students sheet is missing the programme_type column. "
        "Add programme_type to row 1 of the worksheet and backfill "
        "existing students with foundations or professional."
    )

elif "category" not in students.columns:
    st.error(
        "The Students sheet is missing the category column. "
        "Add category to row 1 of the worksheet and backfill "
        "existing students with audit or certified."
    )


else:
    student_view = students.copy()

    # Normalize display and filter columns.
    for column in [
        "student_id",
        "name",
        "email_address",
        "school",
        "cohort",
        "status",
        "programme_type",
        "category"
    ]:
        if column in student_view.columns:
            student_view[column] = (
                student_view[column]
                .fillna("")
                .astype(str)
                .str.strip()
            )

    student_view["status"] = student_view["status"].str.lower()

    # --------------------------------------------------
    # SEARCH AND FILTERS
    # --------------------------------------------------

    search = st.text_input(
        "Search students",
        placeholder="Student ID, name or email...",
        key="admin_student_search",
    )

    filter_col1, filter_col2, filter_col3 = st.columns(3)

    if "school" in student_view.columns:
        school_options = ["All"] + sorted(
            value
            for value in student_view["school"].unique().tolist()
            if value
        )

        selected_school = filter_col1.selectbox(
            "Filter by school",
            school_options,
            key="admin_student_school_filter",
        )

        if selected_school != "All":
            student_view = student_view[
                student_view["school"] == selected_school
            ]

    if "cohort" in student_view.columns:
        cohort_options = ["All"] + sorted(
            value
            for value in student_view["cohort"].unique().tolist()
            if value
        )

        selected_cohort = filter_col2.selectbox(
            "Filter by cohort",
            cohort_options,
            key="admin_student_cohort_filter",
        )

        if selected_cohort != "All":
            student_view = student_view[
                student_view["cohort"] == selected_cohort
            ]

    status_options = ["All"] + STUDENT_STATUSES

    selected_status = filter_col3.selectbox(
        "Filter by status",
        status_options,
        key="admin_student_status_filter",
    )

    if selected_status != "All":
        student_view = student_view[
            student_view["status"] == selected_status
        ]

    # Apply search after the other filters.
    if search.strip():
        searchable_columns = [
            column
            for column in [
                "student_id",
                "name",
                "email_address",
                "school",
                "cohort",
                "status",
                "programme_type",
                "category"
            ]
            if column in student_view.columns
        ]

        mask = pd.Series(False, index=student_view.index)

        for column in searchable_columns:
            mask |= student_view[column].str.contains(
                search.strip(),
                case=False,
                na=False,
                regex=False,
            )

        student_view = student_view[mask]

    # --------------------------------------------------
    # STUDENT TABLE AND CSV EXPORT
    # --------------------------------------------------

    preferred_columns = [
        "student_id",
        "name",
        "email_address",
        "school",
        "cohort",
        "status",
        "programme_type",
        "category",
        "created_at",
    ]



    visible_columns = [
        column
        for column in preferred_columns
        if column in student_view.columns
    ]

    display_students = student_view[visible_columns].rename(
        columns={
            "student_id": "Student ID",
            "name": "Name",
            "email_address": "Email",
            "school": "School",
            "cohort": "Cohort",
            "status": "Status",
            "programme_type": "Programme Type",
            "category": "Category",
            "created_at": "Registered At",
        }
    )

    st.caption(
        f"Showing {len(display_students)} student record(s)."
    )

    st.dataframe(
        display_students,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "⬇️ Export displayed student records (CSV)",
        data=display_students.to_csv(index=False).encode("utf-8"),
        file_name="saes_students.csv",
        mime="text/csv",
        key="admin_export_students",
    )

    st.divider()

    # --------------------------------------------------
    # EDIT STUDENT DETAILS AND STATUS
    # --------------------------------------------------

    st.subheader("✏️ Manage Student")

    # Build options from the original, unfiltered student list.
    student_options = {}

    for _, row in students.iterrows():
        student_id = str(row.get("student_id", "")).strip()

        if not student_id:
            continue

        name = str(row.get("name", "Unnamed")).strip() or "Unnamed"

        label = f"{name} — {student_id}"

        # Avoid overwriting labels if names/IDs are duplicated.
        if label in student_options:
            label = f"{label} (row {row.name})"

        student_options[label] = student_id

    if not student_options:
        st.warning("No students with a valid student ID were found.")

    else:
        selected_student_label = st.selectbox(
            "Select a student to manage",
            list(student_options.keys()),
            key="admin_manage_student",
        )

        selected_student_id = student_options[selected_student_label]

        selected_student_rows = students[
            students["student_id"].fillna("").astype(str).str.strip()
            == selected_student_id
        ]

        if len(selected_student_rows) != 1:
            st.error(
                "The student ID is missing or duplicated. "
                "Resolve this in the worksheet before editing."
            )

        else:
            selected_student = selected_student_rows.iloc[0]

            current_name = str(
                selected_student.get("name", "")
            ).strip()

            current_email = str(
                selected_student.get("email_address", "")
            ).strip()

            current_school = str(
                selected_student.get("school", "")
            ).strip()

            current_cohort = str(
                selected_student.get("cohort", "")
            ).strip()

            current_status = str(
                selected_student.get("status", "")
            ).strip().lower()

            current_programme_type = str(
                selected_student.get("programme_type", "")
            ).strip().lower()

            current_category = str(
                selected_student.get("category", "")
            ).strip().lower()

            # Preserve an unknown existing value so it can be
            # explicitly corrected rather than silently overwritten.
            edit_status_options = STUDENT_STATUSES.copy()
            edit_programme_type_options = STUDENT_PROGRAMME_TYPE.copy()
            edit_category_options = STUDENT_CATEGORY.copy()

            if current_status not in edit_status_options:
                edit_status_options.append(current_status)

            status_index = (
                edit_status_options.index(current_status)
                if current_status in edit_status_options
                else 0
            )

            if current_programme_type not in edit_programme_type_options:
                edit_programme_type_options.append(current_programme_type)

            programme_type_index = (
                edit_programme_type_options.index(current_programme_type)
                if current_programme_type in edit_programme_type_options
                else 0
            )

            if current_category not in edit_category_options:
                edit_category_options.append(current_category)

            category_index = (
                edit_category_options.index(current_category)
                if current_category in edit_category_options
                else 0
            )

            with st.expander(
                "Edit Student Details",
                expanded=False,
            ):
                with st.form("admin_edit_student_form"):
                    edited_name = st.text_input(
                        "Full name",
                        value=current_name,
                    )

                    edited_email = st.text_input(
                        "Email address",
                        value=current_email,
                    )

                    edited_school = st.text_input(
                        "School",
                        value=current_school,
                        help=(
                            "Enter the school name used in "
                            "the student record."
                        ),
                    )

                    edited_cohort = st.text_input(
                        "Cohort",
                        value=current_cohort,
                    )

                    edited_status = st.selectbox(
                        "Student status",
                        options=edit_status_options,
                        index=status_index,
                        format_func=lambda value: (
                            value.replace("_", " ").title()
                            if value in STUDENT_STATUSES
                            else f"{value} (unrecognised — change this)"
                        ),
                        help=(
                            "Active: currently participating. "
                            "Inactive: not currently active. "
                            "Suspended: temporarily restricted. "
                            "Graduated: completed the programme."
                        ),
                    )

                    
                    edited_programme_type = st.selectbox(
                        "Programme Type",
                        options=edit_programme_type_options,
                        index=programme_type_index,
                        format_func=lambda value: (
                            value.replace("_", " ").title()
                            if value in STUDENT_PROGRAMME_TYPE
                            else f"{value} (unrecognised — change this)"
                        ),
                        help=(
                            "Foundations: the default programme. "
                            "Professional: the professional programme."
                        ),
                    )

                    edited_category = st.selectbox(
                        "Student Category",
                        options=edit_category_options,
                        index=category_index,
                        format_func=lambda value: (
                            value.replace("_", " ").title()
                            if value in STUDENT_CATEGORY
                            else f"{value} (unrecognised — change this)"
                        ),
                        help=(
                            "Audit: learner participating under the audit arrangement. "
                            "Certified: learner in the certified category."
                        ),
                    )


                    save_student = st.form_submit_button(
                        "Save Student Changes",
                        use_container_width=True,
                    )

                if save_student:
                    clean_name = edited_name.strip()
                    clean_email = edited_email.strip().lower()
                    clean_school = edited_school.strip()
                    clean_cohort = edited_cohort.strip()
                    clean_status = edited_status.strip().lower()
                    clean_programme_type = edited_programme_type.strip().lower()
                    clean_category = edited_category.strip().lower()

                    if not clean_name:
                        st.error("Student name cannot be empty.")

                    elif not clean_email or "@" not in clean_email:
                        st.error("Enter a valid email address.")

                    elif not clean_school:
                        st.error("School cannot be empty.")

                    elif clean_status not in STUDENT_STATUSES:
                        st.error(
                            "Select a valid student status: "
                            "active, inactive, suspended or graduated."
                        )

                    elif clean_programme_type not in STUDENT_PROGRAMME_TYPE:
                        st.error(
                            "Select a valid programme type: "
                            "foundations or professional."
                        )

                    elif clean_category not in STUDENT_CATEGORY:
                        st.error(
                            "Select a valid student category: "
                            "audit or certified."
                        )


                    else:
                        other_students = students[
                            students["student_id"].fillna("").astype(str).str.strip()
                            != selected_student_id
                        ]

                        duplicate_email = (
                            other_students["email_address"]
                            .fillna("")
                            .astype(str)
                            .str.strip()
                            .str.casefold()
                            .eq(clean_email.casefold())
                        ).any() if "email_address" in students.columns else False

                        if duplicate_email:
                            st.error(
                                "Another student already uses this email."
                            )

                        else:
                            updates = {
                                "name": clean_name,
                                "email_address": clean_email,
                                "school": clean_school,
                                "cohort": clean_cohort,
                                "status": clean_status,
                                "programme_type": clean_programme_type,
                                "category": clean_category
                            }

                            try:
                                update_record_by_id(
                                    students_sheet,
                                    "student_id",
                                    selected_student_id,
                                    updates,
                                    "students",
                                )

                                load_students.clear()

                                st.success(
                                    "Student details and status "
                                    "updated successfully."
                                )
                                st.rerun()

                            except Exception as exc:
                                st.error(
                                    f"Could not update student: {exc}"
                                )

            # Current status summary
            st.write(f"**Student ID:** {selected_student_id}")
            st.write(f"**Current status:** {current_status.title() or 'Missing'}")
            st.write(
                f"**Programme type:** "
                f"{current_programme_type.title() or 'Missing'}"
            )
            st.write(
                f"**Student category:** "
                f"{current_category.title() or 'Missing'}"
            )


# --------------------------------------------------
# FOOTER
# --------------------------------------------------

st.divider()

if st.button("Sign out of Admin"):
    st.session_state["admin_authenticated"] = False
    st.rerun()
