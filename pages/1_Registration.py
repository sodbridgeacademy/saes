
import re
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
    "name",
    "email_address",
    "school",
    "cohort",
    "created_at",
    "student_source",
]

ACCOUNT_HEADERS = [
    "email_address",
    "student_id",
    "password_hash",
    "created_at",
    "account_status",
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


def get_missing_headers(actual_headers, required_headers):
    return [
        header
        for header in required_headers
        if header not in actual_headers
    ]


# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

st.title("🧾 Student Registration")

try:
    sheets = get_sheets()

    students_sheet = sheets["students"]
    accounts_sheet = sheets["student_accounts"]
    cohorts_sheet = sheets["cohorts"]

    students = load_students()

    student_sheet_headers = students_sheet.row_values(1)
    account_sheet_headers = accounts_sheet.row_values(1)
    cohort_sheet_headers = cohorts_sheet.row_values(1)

    cohort_records = cohorts_sheet.get_all_records()

except Exception as exc:
    st.error(
        "Registration is temporarily unavailable. "
        "Please try again later or contact the "
        "Academy administrator."
    )
    print(f"SAES registration setup error: {exc}")
    st.stop()


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

if missing_cohort_headers:
    st.error(
        "The cohorts worksheet is missing required columns: "
        + ", ".join(missing_cohort_headers)
    )
    st.stop()



if missing_student_headers or missing_account_headers:
    st.error(
        "The registration worksheets are missing required "
        "columns. Please contact the Academy administrator."
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
        "Register",
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

    # Recheck registration status at submission time.
    try:
        latest_cohort_records = cohorts_sheet.get_all_records()

        cohort_is_open = any(
            str(item.get("cohort_code", "")).strip().upper()
            == cohort
            and str(
                item.get("registration_status", "")
            ).strip().casefold() == "open"
            for item in latest_cohort_records
        )
    except Exception:
        cohort_is_open = False


    if not cohort_is_open:
        st.error(
            "This cohort is no longer accepting registrations. "
            "Please refresh the page and select an available cohort."
        )
    elif not name:
        st.error("Please enter your full name.")

    elif not is_valid_email(email):
        st.error("Please enter a valid email address.")

    elif len(password) < 8:
        st.error(
            "Your password must contain at least 8 characters."
        )

    elif password != confirm_password:
        st.error("The passwords do not match.")

    elif "email_address" not in students.columns:
        st.error(
            "The student sheet is missing the email_address "
            "column. Contact the Academy administrator."
        )

    else:
        try:
            # Check existing student profiles.
            existing_student_emails = (
                students["email_address"]
                .fillna("")
                .astype(str)
                .map(normalize_email)
            )

            if existing_student_emails.eq(email).any():
                st.error(
                    "This email is already registered. "
                    "Please use your existing SAES account "
                    "or contact the Academy Manager."
                )

            else:
                # Check existing login accounts as well.
                accounts = accounts_sheet.get_all_records()

                existing_account_emails = [
                    normalize_email(
                        account.get("email_address", "")
                    )
                    for account in accounts
                ]

                if email in existing_account_emails:
                    st.error(
                        "An account already exists for this email. "
                        "Please contact the Academy Manager."
                    )

                else:
                    student_id = generate_student_id(
                        students,
                        school,
                    )

                    created_at = pd.Timestamp.now().isoformat()

                    # Prepare the student profile row by header.
                    student_data = {
                        "student_id": student_id,
                        "name": name,
                        "email_address": email,
                        "school": school,
                        "cohort": cohort,
                        "created_at": created_at,
                        "student_source": student_source,
                    }

                    student_row = [
                        student_data[header]
                        for header in student_sheet_headers
                    ]

                    # Prepare the account row by header.
                    account_data = {
                        "email_address": email,
                        "student_id": student_id,
                        "password_hash": hash_password(password),
                        "created_at": created_at,
                        "account_status": "active",
                    }

                    account_row = [
                        account_data[header]
                        for header in account_sheet_headers
                    ]

                    # Write profile first, then login account.
                    students_sheet.append_row(
                        student_row,
                        value_input_option="USER_ENTERED",
                    )

                    # Refresh the profile cache after writing.
                    load_students.clear()

                    accounts_sheet.append_row(
                        account_row,
                        value_input_option="USER_ENTERED",
                    )

                    st.success(
                        "Registration successful!"
                    )

                    st.write(f"**Student ID:** {student_id}")
                    st.write(f"**School:** {school}")
                    st.write(f"**Cohort:** {cohort}")
                    st.write(
                        f"**Email:** {email}"
                    )

                    st.info(
                        "Your account has been created. "
                        "Go to the SAES Login page to sign in "
                        "with your email address and password."
                    )

        except Exception as exc:
            # Avoid displaying technical details to applicants.
            st.error(
                "Registration could not be fully completed. "
                "Please do not submit repeatedly. Contact "
                "the Academy administrator to verify your "
                "registration before trying again."
            )

            print(f"SAES registration error: {exc}")
