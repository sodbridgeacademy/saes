
import hashlib
import hmac
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import streamlit as st
import logging

from utils.sheets import get_sheets
from utils.auth import (
    verify_password,
    hash_password,
    clear_student_session,
    clear_user_session,
    authenticate_user,
    set_user_session,
    create_persistent_session,
    logout_user,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------
# Role-based page destinations
# --------------------------------------------------

ROLE_DESTINATIONS = {
    "student": "pages/5_Student_Profile.py",
    "instructor": "pages/Staff_Profile.py",
    "admin": "pages/8_Admin.py",
}

# --------------------------------------------------
# Configuration
# --------------------------------------------------

RESET_CODE_MINUTES = 10
MAX_RESET_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60

REQUIRED_HEADERS = [
    "email_address",
    "user_id",
    "role",
    "password_hash",
    "account_status",
    "reset_code_hash",
    "reset_expires_at",
    "reset_attempts",
    "reset_last_sent_at",
]


def redirect_authenticated_user():
    """Route an authenticated user according to their role."""

    if st.session_state.get("student_authenticated"):
        role = "student"
    elif st.session_state.get("user_authenticated"):
        role = str(
            st.session_state.get("user_role", "")
        ).strip().casefold()
    else:
        return

    destination = ROLE_DESTINATIONS.get(role)

    if destination and "REPLACE_WITH_" not in destination:
        st.switch_page(destination)


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def normalize_email(email):
    return str(email or "").strip().casefold()


def utc_now():
    return datetime.now(timezone.utc)


def parse_timestamp(value):
    value = str(value or "").strip()

    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None



def get_account_context():
    """
    Return the account worksheet, headers, and records.
    Fail closed if the expected schema is unavailable.
    """

    sheets = get_sheets()
    worksheet = sheets["user_accounts"]

    headers = worksheet.row_values(1)

    missing = [
        header
        for header in REQUIRED_HEADERS
        if header not in headers
    ]

    if missing:
        raise ValueError(
            "Missing user_accounts headers: "
            + ", ".join(missing)
        )

    records = worksheet.get_all_records()

    header_positions = {
        header: headers.index(header) + 1
        for header in REQUIRED_HEADERS
    }

    return worksheet, headers, records, header_positions



def update_account_cells(
    worksheet,
    row_number,
    header_positions,
    updates,
):
    """Update account fields using their header names."""

    for header, value in updates.items():
        worksheet.update_cell(
            row_number,
            header_positions[header],
            value,
        )


def code_digest(email, code):
    """
    Hash the code with a server-side secret.
    The raw code is never stored in Google Sheets.
    """

    secret = st.secrets["RESET_CODE_SECRET"]

    if not secret or len(str(secret)) < 32:
        raise ValueError(
            "RESET_CODE_SECRET must be configured securely."
        )

    message = f"{normalize_email(email)}:{code}"

    return hmac.new(
        str(secret).encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def send_reset_email(email, code):
    """Send the password-reset verification code by SMTP."""

    smtp_host = st.secrets["SMTP_HOST"]
    smtp_port = int(st.secrets.get("SMTP_PORT", 465))
    smtp_username = st.secrets["SMTP_USERNAME"]
    smtp_password = st.secrets["SMTP_PASSWORD"]

    message = EmailMessage()
    message["Subject"] = "SAES Password Reset Code"
    message["From"] = smtp_username
    message["To"] = email

    message.set_content(
        f"""Hello,

We received a request to reset your Sodbridge Academy
Engagement System (SAES) password.

Your verification code is: {code}

This code expires in {RESET_CODE_MINUTES} minutes and can
only be used once.

If you did not request a password reset, you can ignore
this email.

SAES Support
"""
    )

    context = ssl.create_default_context()

    with smtplib.SMTP_SSL(
        smtp_host,
        smtp_port,
        context=context,
        timeout=20,
    ) as server:
        server.login(smtp_username, smtp_password)
        server.send_message(message)


def clear_reset_fields(
    worksheet,
    row_number,
    header_positions,
):
    update_account_cells(
        worksheet,
        row_number,
        header_positions,
        {
            "reset_code_hash": "",
            "reset_expires_at": "",
            "reset_attempts": 0,
            "reset_last_sent_at": "",
        },
    )


def reset_page_error():
    st.error(
        "Password recovery is temporarily unavailable. "
        "Please try again later or contact the Academy Manager."
    )


# --------------------------------------------------
# Page
# --------------------------------------------------

st.title("🔐 SAES Login")
st.caption(
    "Sign in to your Sodbridge Academy Engagement System account."
)

if "login_mode" not in st.session_state:
    st.session_state["login_mode"] = "Log In"

# Process navigation requests before creating the radio widget.
if st.session_state.pop("return_to_login", False):
    st.session_state["login_mode"] = "Log In"


# --------------------------------------------------
# Already authenticated
# --------------------------------------------------

if (
    st.session_state.get("user_authenticated")
    or st.session_state.get("student_authenticated")
):
    redirect_authenticated_user()
    st.stop()


# --------------------------------------------------
# Choose login or password recovery
# --------------------------------------------------

mode = st.radio(
    "Choose an option",
    ["Log In", "Forgot Password"],
    horizontal=True,
    key="login_mode",
)


# old hash: scrypt$16384$8$1$17e3de4665a8c1da6c5d77539cef76a3$ec530646240af77f8ab9255b2514272d6b3ade9bef04a4a73f07127c91271e7f
# new hash:  


# ==================================================
# LOGIN
# ==================================================

if mode == "Log In":

    with st.form("student_login"):
        email = st.text_input("Email Address")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Log In")

    if submit:
        email = normalize_email(email)

        if not email or not password:
            st.error("Enter your email address and password.")

        else:
            try:
                # ------------------------------------------
                # 1. Authenticate against shared accounts
                # ------------------------------------------

                shared_account = authenticate_user(email, password)

                if not shared_account:
                    st.error(
                        "Unable to log in with those details. "
                        "Check your credentials or contact "
                        "the Academy Manager."
                    )
                    st.stop()

                # ------------------------------------------
                # 2. Establish shared authenticated session
                # ------------------------------------------

                set_user_session(shared_account)

                user_id = str(
                    shared_account.get("user_id", "")
                ).strip()

                role = str(
                    shared_account.get("role")
                    or st.session_state.get("user_role", "")
                ).strip().casefold()

                role_aliases = {
                    "student": "student",
                    "learner": "student",
                    "instructor": "instructor",
                    "teacher": "instructor",
                    "admin": "admin",
                    "administrator": "admin",
                }

                role = role_aliases.get(role, role)

                if role not in ROLE_DESTINATIONS:
                    clear_user_session()
                    clear_student_session()

                    st.error(
                        "Your account role is missing or "
                        "is not supported. Please contact "
                        "the Academy Manager."
                    )
                    st.stop()

                st.session_state["user_role"] = role

                # ------------------------------------------
                # 3. Link student profile
                # ------------------------------------------

                if role == "student":

                    sheets = get_sheets()
                    students_sheet = sheets["students"]

                    student_records = students_sheet.get_all_records(
                        default_blank=""
                    )

                    matching_students = [
                        student
                        for student in student_records
                        if str(
                            student.get("user_id", "")
                        ).strip() == user_id
                    ]

                    if len(matching_students) != 1:
                        clear_user_session()
                        clear_student_session()

                        logger.error(
                            "Student profile link failed. "
                            "user_id=%s, matches=%s",
                            user_id,
                            len(matching_students),
                        )

                        st.error(
                            "Your student profile could not be "
                            "linked to your account. Please "
                            "contact the Academy Manager."
                        )
                        st.stop()

                    student = matching_students[0]

                    account_student_id = str(
                        student.get("student_id", "")
                    ).strip()

                    if not account_student_id:
                        clear_user_session()
                        clear_student_session()

                        logger.error(
                            "Student record has no student_id. "
                            "user_id=%s",
                            user_id,
                        )

                        st.error(
                            "Your student profile has an incomplete "
                            "record. Please contact the Academy Manager."
                        )
                        st.stop()

                    st.session_state["student_authenticated"] = True
                    st.session_state["student_email"] = email
                    st.session_state["student_id"] = account_student_id

                # ------------------------------------------
                # 4. Link instructor profile
                # ------------------------------------------

                elif role == "instructor":

                    sheets = get_sheets()
                    staff_sheet = sheets["staff"]

                    staff_records = staff_sheet.get_all_records(
                        default_blank=""
                    )

                    matching_staff = [
                        staff
                        for staff in staff_records
                        if str(
                            staff.get("user_id", "")
                        ).strip() == user_id
                    ]

                    if len(matching_staff) != 1:
                        clear_user_session()
                        clear_student_session()

                        logger.error(
                            "Instructor profile link failed. "
                            "user_id=%s, matches=%s",
                            user_id,
                            len(matching_staff),
                        )

                        st.error(
                            "Your instructor profile could not be "
                            "linked to your account. Please contact "
                            "the Academy Manager."
                        )
                        st.stop()

                    instructor = matching_staff[0]

                    staff_id = str(
                        instructor.get("staff_id", "")
                    ).strip()

                    if not staff_id:
                        clear_user_session()
                        clear_student_session()

                        logger.error(
                            "Instructor record has no staff_id. "
                            "user_id=%s",
                            user_id,
                        )

                        st.error(
                            "Your staff profile has an incomplete "
                            "record. Please contact the Academy Manager."
                        )
                        st.stop()

                    st.session_state["staff_id"] = staff_id
                    st.session_state["staff_name"] = str(
                        instructor.get("full_name", "")
                    ).strip()

                # ------------------------------------------
                # 5. Admins do not require student/staff links
                # ------------------------------------------

            
                # ------------------------------------------
                # 6. Create persistent session
                # ------------------------------------------

                create_persistent_session(shared_account)

                # ------------------------------------------
                # 7. Redirect authenticated user
                # ------------------------------------------

                redirect_authenticated_user()
                st.stop()

            except Exception:
                logger.exception("SAES login failed")

                logout_user()

            
                st.error(
                    "Login is temporarily unavailable. "
                    "Please try again later or contact the admin."
                )



# ==================================================
# REQUEST A RESET CODE
# ==================================================

elif mode == "Forgot Password":

    st.subheader("Reset your password")

    st.write(
        "Enter the email address registered to your "
        "SAES account. If the account is eligible, "
        "we will send a verification code."
    )

    with st.form("request_reset_code"):
        reset_email = st.text_input(
            "Registered email address"
        )

        request_code = st.form_submit_button(
            "Send verification code"
        )

    if request_code:
        reset_email = normalize_email(reset_email)

        if not reset_email:
            st.error("Enter your email address.")

        else:
            try:
                (
                    worksheet,
                    headers,
                    accounts,
                    header_positions,
                ) = get_account_context()

                matching_accounts = [
                    (index, account)
                    for index, account in enumerate(
                        accounts,
                        start=2,
                    )
                    if normalize_email(
                        account.get("email_address", "")
                    ) == reset_email
                ]

                # Use the same outward response whether the email
                # exists or not, to reduce account enumeration.
                generic_message = (
                    "If an active account matches that email, "
                    "a verification code will be sent. "
                    "If you don't receive it, check your inbox "
                    "and spam folder or contact the Academy Manager."
                )

                if len(matching_accounts) == 1:
                    row_number, account = matching_accounts[0]

                    active = (
                        str(
                            account.get("account_status", "")
                        ).strip().casefold()
                        == "active"
                    )

                    if active:
                        last_sent = parse_timestamp(
                            account.get("reset_last_sent_at", "")
                        )

                        if last_sent:
                            elapsed = (
                                utc_now() - last_sent
                            ).total_seconds()

                            if elapsed < RESEND_COOLDOWN_SECONDS:
                                st.info(
                                    "Please wait before requesting "
                                    "another code."
                                )
                                st.stop()

                        code = f"{secrets.randbelow(1_000_000):06d}"
                        expiry = (
                            utc_now()
                            + timedelta(
                                minutes=RESET_CODE_MINUTES
                            )
                        )

                        # Store the hash and expiry before sending.
                        update_account_cells(
                            worksheet,
                            row_number,
                            header_positions,
                            {
                                "reset_code_hash": code_digest(
                                    reset_email,
                                    code,
                                ),
                                "reset_expires_at": (
                                    expiry.isoformat()
                                ),
                                "reset_attempts": 0,
                                "reset_last_sent_at": (
                                    utc_now().isoformat()
                                ),
                            },
                        )

                        try:
                            send_reset_email(
                                reset_email,
                                code,
                            )

                        except Exception as exc:
                            print(
                                "SAES reset email error: "
                                f"{exc}"
                            )

                            # Invalidate the code if delivery failed.
                            clear_reset_fields(
                                worksheet,
                                row_number,
                                header_positions,
                            )

                st.session_state["reset_email"] = reset_email

                st.info(generic_message)

                st.caption(
                    "Next, choose Forgot Password again if needed, "
                    "or switch to the verification form in the "
                    "reset workflow after receiving your code."
                )

            except Exception as exc:
                print(f"SAES reset request error: {exc}")
                reset_page_error()


# ==================================================
# VERIFY CODE AND SET NEW PASSWORD
# ==================================================

st.divider()
st.subheader("Have a verification code?")

with st.form("verify_reset_code"):
    verify_email = st.text_input(
        "Registered email address",
        value=st.session_state.get("reset_email", ""),
        key="verify_reset_email",
    )

    verification_code = st.text_input(
        "Six-digit verification code",
        max_chars=6,
    )

    new_password = st.text_input(
        "New password",
        type="password",
    )

    confirm_password = st.text_input(
        "Confirm new password",
        type="password",
    )

    reset_password_button = st.form_submit_button(
        "Reset Password"
    )


if reset_password_button:
    verify_email = normalize_email(verify_email)
    verification_code = verification_code.strip()

    if (
        not verify_email
        or not verification_code
        or not new_password
        or not confirm_password
    ):
        st.error("Complete all fields.")

    elif (
        len(verification_code) != 6
        or not verification_code.isdigit()
    ):
        st.error(
            "Enter the six-digit verification code."
        )

    elif new_password != confirm_password:
        st.error("The passwords do not match.")

    elif len(new_password) < 10:
        st.error(
            "Choose a password with at least 10 characters."
        )

    else:
        try:
            (
                worksheet,
                headers,
                accounts,
                header_positions,
            ) = get_account_context()

            matching_accounts = [
                (index, account)
                for index, account in enumerate(
                    accounts,
                    start=2,
                )
                if normalize_email(
                    account.get("email_address", "")
                ) == verify_email
            ]

            if len(matching_accounts) != 1:
                st.error(
                    "The code is invalid or expired. "
                    "Request a new code and try again."
                )

            else:
                row_number, account = matching_accounts[0]

                status = str(
                    account.get("account_status", "")
                ).strip().casefold()

                stored_digest = str(
                    account.get("reset_code_hash", "")
                ).strip()

                expiry = parse_timestamp(
                    account.get("reset_expires_at", "")
                )

                try:
                    attempts = int(
                        account.get("reset_attempts", 0) or 0
                    )
                except (ValueError, TypeError):
                    attempts = MAX_RESET_ATTEMPTS

                if status != "active":
                    st.error(
                        "This account is not eligible for "
                        "password recovery."
                    )

                elif (
                    not stored_digest
                    or expiry is None
                    or utc_now() >= expiry
                    or attempts >= MAX_RESET_ATTEMPTS
                ):
                    clear_reset_fields(
                        worksheet,
                        row_number,
                        header_positions,
                    )

                    st.error(
                        "The code is invalid or expired. "
                        "Request a new code."
                    )

                else:
                    submitted_digest = code_digest(
                        verify_email,
                        verification_code,
                    )

                    if not hmac.compare_digest(
                        submitted_digest,
                        stored_digest,
                    ):
                        attempts += 1

                        update_account_cells(
                            worksheet,
                            row_number,
                            header_positions,
                            {
                                "reset_attempts": attempts,
                            },
                        )

                        if attempts >= MAX_RESET_ATTEMPTS:
                            clear_reset_fields(
                                worksheet,
                                row_number,
                                header_positions,
                            )

                            st.error(
                                "Too many incorrect attempts. "
                                "Request a new verification code."
                            )
                        else:
                            st.error(
                                "The code is invalid or expired. "
                                f"Attempts remaining: "
                                f"{MAX_RESET_ATTEMPTS - attempts}."
                            )

                    else:
                        # Update the password hash and invalidate
                        # the verification code.
                        update_account_cells(
                            worksheet,
                            row_number,
                            header_positions,
                            {
                                "password_hash": hash_password(
                                    new_password
                                ),
                                "reset_code_hash": "",
                                "reset_expires_at": "",
                                "reset_attempts": 0,
                                "reset_last_sent_at": "",
                            },
                        )

                        st.session_state.pop(
                            "reset_email",
                            None,
                        )

                        st.success(
                            "Your password has been reset. "
                            "You can now log in with your new password."
                        )

                        st.session_state["return_to_login"] = True
                        st.rerun()

        except Exception as exc:
            print(f"SAES password reset error: {exc}")

            st.error(
                "Password reset is temporarily unavailable. "
                "Please try again later."
            )
