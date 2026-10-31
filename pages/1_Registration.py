
import re
import uuid

import streamlit as st
import pandas as pd

from utils.sheets import get_sheets
from utils.data import load_students
from utils.auth import hash_password


st.set_page_config(
    page_title="SAES Student Registration",
    page_icon="🧾",
    layout="centered",
)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

SCHOOLS = ["DAT", "DEV", "DSN", "CYB"]

COHORT_HEADERS = [
    "cohort_id",
    "cohort_name",
    "cohort_code",
    "start_date",
    "end_date",
    "registration_status",
    "created_at",
]

STUDENT_SOURCES = {
    "Direct applicant": "Direct",
    "GOY": "GOY",
    "THCHF": "THCHF",
}

STUDENT_HEADERS = [
    "student_id",
    "user_id",
    "name",
    "email_address",
    "school",
    "cohort",
    "created_at",
    "student_source",
]

ACCOUNT_HEADERS = [
    "user_id",
    "email_address",
    "password_hash",
    "account_status",
    "role",
    "reset_code_hash",
    "reset_expires_at",
    "reset_attempts",
    "reset_last_sent_at",
    "password_change_required",
    "created_at",
    "last_login_at",
]


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def normalize_email(email):
    return str(email).strip().casefold()


def is_valid_email(email):
    return bool(
        re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            email,
        )
    )


def generate_student_id(df, prefix):
    """Generate the next sequential ID for a school."""

    if df.empty or "student_id" not in df.columns:
        return f"{prefix}-001"

    ids = (
        df["student_id"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    pattern = rf"^{re.escape(prefix)}-(\d+)$"

    numbers = ids.str.extract(
        pattern,
        expand=False,
    ).dropna()

    if numbers.empty:
        return f"{prefix}-001"

    next_number = numbers.astype(int).max() + 1

    return f"{prefix}-{next_number:03d}"


def generate_user_id(existing_user_ids):
    """Generate a unique ID for a shared SAES account."""

    existing = {
        str(value).strip()
        for value in existing_user_ids
        if str(value).strip()
    }

    while True:
        user_id = f"USR-{uuid.uuid4().hex[:12].upper()}"

        if user_id not in existing:
            return user_id


def get_missing_headers(actual_headers, required_headers):
    return [
        header
        for header in required_headers
        if header not in actual_headers
    ]


def build_row(data, headers):
    """Build a worksheet row in its actual column order."""

    return [data.get(header, "") for header in headers]


# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

st.title("🧾 Student Registration")

try:
    sheets = get_sheets()

    students_sheet = sheets["students"]
    accounts_sheet = sheets["user_accounts"]
    cohorts_sheet = sheets["cohorts"]

    student_sheet_headers = students_sheet.row_values(1)
    account_sheet_headers = accounts_sheet.row_values(1)
    cohort_sheet_headers = cohorts_sheet.row_values(1)

    missing_student_headers = get_missing_headers(
        student_sheet_headers,
        STUDENT_HEADERS,
    )

    missing_account_headers = get_missing_headers(
        account_sheet_headers,
        ACCOUNT_HEADERS,
    )

    missing_cohort_headers = get_missing_headers(
        cohort_sheet_headers,
        COHORT_HEADERS,
    )

    if (
        missing_student_headers
        or missing_account_headers
        or missing_cohort_headers
    ):
        st.error(
            "Registration worksheets are missing required columns. "
            "Please contact the Academy administrator."
        )

        if missing_student_headers:
            st.write(
                "Missing student columns:",
                ", ".join(missing_student_headers),
            )

        if missing_account_headers:
            st.write(
                "Missing account columns:",
                ", ".join(missing_account_headers),
            )

        if missing_cohort_headers:
            st.write(
                "Missing cohort columns:",
                ", ".join(missing_cohort_headers),
            )

        st.stop()

    cohort_records = cohorts_sheet.get_all_records()

except Exception as exc:
    st.error(
        "Registration is temporarily unavailable. "
        "Please try again later or contact the "
        "Academy administrator."
    )
    print(f"SAES registration setup error: {exc}")
    st.stop()


# --------------------------------------------------
# AVAILABLE COHORTS
# --------------------------------------------------

open_cohorts = [
    cohort
    for cohort in cohort_records
    if str(
        cohort.get("registration_status", "")
    ).strip().casefold() == "open"
    and str(cohort.get("cohort_name", "")).strip()
    and str(cohort.get("cohort_code", "")).strip()
]

cohort_options = {
    (
        f"{str(cohort['cohort_name']).strip()} "
        f"({str(cohort['cohort_code']).strip().upper()})"
    ): str(cohort["cohort_code"]).strip().upper()
    for cohort in open_cohorts
}

if not cohort_options:
    st.info(
        "Registration is currently closed for all cohorts. "
        "Please check back later."
    )
    st.stop()


# --------------------------------------------------
# REGISTRATION FORM
# --------------------------------------------------

with st.form("register"):
    name = st.text_input("Full Name")

    email = st.text_input("Email Address")

    school = st.selectbox(
        "School",
        options=SCHOOLS,
    )

    cohort_label = st.selectbox(
        "Joining Cohort",
        options=list(cohort_options.keys()),
    )

    source_label = st.selectbox(
        "Registration Source",
        options=list(STUDENT_SOURCES.keys()),
    )

    password = st.text_input(
        "Create Password",
        type="password",
        help="Use at least 8 characters.",
    )

    confirm_password = st.text_input(
        "Confirm Password",
        type="password",
    )

    submit = st.form_submit_button(
        "Create Student Account",
        use_container_width=True,
    )


# --------------------------------------------------
# PROCESS REGISTRATION
# --------------------------------------------------

if submit:
    name = name.strip()
    email = normalize_email(email)

    cohort = cohort_options[cohort_label]
    student_source = STUDENT_SOURCES[source_label]

    # Basic validation.
    if not name:
        st.error("Please enter your full name.")

    elif not is_valid_email(email):
        st.error("Please enter a valid email address.")

    elif len(password) < 8:
        st.error(
            "Your password must contain at least 8 characters."
        )

    elif password != confirm_password:
        st.error("The passwords do not match.")

    else:
        try:
            # Recheck cohort status at submission time.
            latest_cohort_records = cohorts_sheet.get_all_records()

            cohort_is_open = any(
                str(item.get("cohort_code", ""))
                .strip()
                .upper() == cohort
                and str(
                    item.get("registration_status", "")
                ).strip().casefold() == "open"
                for item in latest_cohort_records
            )

            if not cohort_is_open:
                st.error(
                    "This cohort is no longer accepting registrations. "
                    "Please refresh the page and select an available cohort."
                )

            else:
                # Read fresh worksheet data for duplicate checks.
                latest_student_records = (
                    students_sheet.get_all_records()
                )
                account_records = accounts_sheet.get_all_records()

                existing_student_emails = {
                    normalize_email(
                        record.get("email_address", "")
                    )
                    for record in latest_student_records
                    if normalize_email(
                        record.get("email_address", "")
                    )
                }

                existing_account_emails = {
                    normalize_email(
                        record.get("email_address", "")
                    )
                    for record in account_records
                    if normalize_email(
                        record.get("email_address", "")
                    )
                }

                if (
                    email in existing_student_emails
                    or email in existing_account_emails
                ):
                    st.error(
                        "This email is already registered. "
                        "Please use your existing SAES account "
                        "or contact the Academy Manager."
                    )

                else:
                    latest_students_df = pd.DataFrame(
                        latest_student_records
                    )

                    student_id = generate_student_id(
                        latest_students_df,
                        school,
                    )

                    user_id = generate_user_id(
                        [
                            record.get("user_id", "")
                            for record in account_records
                        ]
                    )

                    created_at = (
                        pd.Timestamp.now(tz="UTC").isoformat()
                    )

                    # Prepare student profile.
                    student_data = {
                        "student_id": student_id,
                        "user_id": user_id,
                        "name": name,
                        "email_address": email,
                        "school": school,
                        "cohort": cohort,
                        "status": "active",
                        "created_at": created_at,
                        "student_source": student_source,
                    }

                    student_row = build_row(
                        student_data,
                        student_sheet_headers,
                    )

                    # Prepare shared login account.
                    account_data = {
                        "user_id": user_id,
                        "email_address": email,
                        "password_hash": hash_password(password),
                        "account_status": "active",
                        "role": "student",
                        "reset_code_hash": "",
                        "reset_expires_at": "",
                        "reset_attempts": 0,
                        "reset_last_sent_at": "",
                        "password_change_required": False,
                        "created_at": created_at,
                        "last_login_at": "",
                    }

                    account_row = build_row(
                        account_data,
                        account_sheet_headers,
                    )

                    # Track the writes so failures are not
                    # silently treated as successful registrations.
                    profile_written = False
                    account_written = False

                    try:
                        # Create the student profile.
                        students_sheet.append_row(
                            student_row,
                            value_input_option="USER_ENTERED",
                        )
                        profile_written = True

                        # Create the shared authentication account.
                        accounts_sheet.append_row(
                            account_row,
                            value_input_option="USER_ENTERED",
                        )
                        account_written = True

                        # Clear cached student data.
                        load_students.clear()

                        st.success("Registration successful!")

                        st.write(f"**Student ID:** {student_id}")
                        st.write(f"**School:** {school}")
                        st.write(f"**Cohort:** {cohort}")
                        st.write(f"**Email:** {email}")

                        st.info(
                            "Your account has been created. "
                            "Go to the SAES Login page to sign in "
                            "with your email address and password."
                        )

                    except Exception as write_exc:
                        print(
                            "SAES registration write error: "
                            f"{write_exc}; user_id={user_id}; "
                            f"student_id={student_id}; "
                            f"profile_written={profile_written}; "
                            f"account_written={account_written}"
                        )

                        # If profile creation succeeded but account
                        # creation failed, attempt best-effort cleanup.
                        # Do not delete anything when a write's
                        # outcome is uncertain.
                        if profile_written and not account_written:
                            try:
                                # Check whether the account actually
                                # exists before attempting cleanup.
                                latest_accounts = (
                                    accounts_sheet.get_all_records()
                                )

                                account_exists = any(
                                    str(record.get("user_id", "")).strip()
                                    == user_id
                                    for record in latest_accounts
                                )

                                if not account_exists:
                                    profile_records = (
                                        students_sheet.get_all_records()
                                    )

                                    matching_rows = [
                                        index + 2
                                        for index, record in enumerate(
                                            profile_records
                                        )
                                        if str(
                                            record.get("user_id", "")
                                        ).strip() == user_id
                                    ]

                                    # Delete only when exactly one
                                    # matching profile is found.
                                    if len(matching_rows) == 1:
                                        students_sheet.delete_rows(
                                            matching_rows[0]
                                        )

                                load_students.clear()

                            except Exception as cleanup_exc:
                                print(
                                    "SAES registration cleanup could "
                                    f"not be confirmed: {cleanup_exc}; "
                                    f"user_id={user_id}"
                                )

                        st.error(
                            "Registration could not be confirmed as "
                            "complete. Please do not submit repeatedly. "
                            "Contact the Academy administrator to verify "
                            "your records before trying again."
                        )

        except Exception as exc:
            st.error(
                "Registration could not be completed. "
                "Please contact the Academy administrator "
                "to verify your registration before retrying."
            )
            print(f"SAES registration processing error: {exc}")
