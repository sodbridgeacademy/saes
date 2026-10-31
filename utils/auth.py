
import os
import hashlib
import hmac

import streamlit as st

from utils.sheets import get_sheets


# --------------------------------------------------
# PASSWORD SECURITY
# --------------------------------------------------

def hash_password(password):
    """Create a salted scrypt hash for password storage."""

    salt = os.urandom(16)

    n = 2**14
    r = 8
    p = 1

    password_hash = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=32,
    )

    return (
        f"scrypt${n}${r}${p}$"
        f"{salt.hex()}${password_hash.hex()}"
    )


def verify_password(password, stored_hash):
    """Verify a password against its stored scrypt hash."""

    try:
        algorithm, n, r, p, salt_hex, hash_hex = (
            stored_hash.split("$")
        )

        if algorithm != "scrypt":
            return False

        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)

        actual_hash = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected_hash),
        )

        return hmac.compare_digest(
            actual_hash,
            expected_hash,
        )

    except (ValueError, TypeError, MemoryError):
        return False


# --------------------------------------------------
# NORMALISATION
# --------------------------------------------------

def normalize_email(email):
    """Normalize an email address for matching."""

    return str(email or "").strip().casefold()


def normalize_student_id(student_id):
    """Normalize a student ID for matching."""

    return str(student_id or "").strip().casefold()


def normalize_user_id(user_id):
    """Normalize a shared user ID for matching."""

    return str(user_id or "").strip()


def normalize_role(role):
    """Normalize an account role."""

    return str(role or "").strip().casefold()


# --------------------------------------------------
# SESSION MANAGEMENT
# --------------------------------------------------

def clear_user_session():
    """Clear shared authentication and profile session data."""

    keys = (
        "user_authenticated",
        "user_id",
        "user_email",
        "user_role",
        "staff_id",
        "staff_name",
        "staff_username",
        "student_authenticated",
        "student_id",
        "student_email",
        "admin_authenticated",
    )

    for key in keys:
        st.session_state.pop(key, None)


def clear_student_session():
    """
    Clear student authentication state.

    Also clears shared authentication when the active account
    is a student.
    """

    current_role = normalize_role(
        st.session_state.get("user_role", "")
    )

    for key in (
        "student_authenticated",
        "student_id",
        "student_email",
    ):
        st.session_state.pop(key, None)

    if current_role == "student":
        clear_user_session()


def set_user_session(account):
    """
    Establish a shared authenticated session from a user_accounts
    record. Call only after successfully verifying the password.
    """

    user_id = normalize_user_id(account.get("user_id", ""))
    email = normalize_email(account.get("email_address", ""))
    role = normalize_role(account.get("role", ""))

    if not user_id or not email or not role:
        raise ValueError(
            "The account is missing its user ID, email or role."
        )

    clear_user_session()

    st.session_state["user_authenticated"] = True
    st.session_state["user_id"] = user_id
    st.session_state["user_email"] = email
    st.session_state["user_role"] = role

    # Temporary compatibility for existing student pages.
    if role == "student":
        st.session_state["student_authenticated"] = True
        st.session_state["student_email"] = email

    # The old admin dashboard uses a shared admin password.
    # Do not enable this flag merely because a shared account
    # has role="admin". The admin dashboard must be migrated
    # to role-aware authentication first.


def logout_user():
    """Log out the current user."""

    clear_user_session()


# --------------------------------------------------
# SHARED ACCOUNT LOOKUP
# --------------------------------------------------

def get_active_user_by_email(email):
    """
    Return one active user_accounts record for the email.

    Returns None if no active, uniquely identifiable account
    exists. Fails closed on duplicate matching records.
    """

    normalized_email = normalize_email(email)

    if not normalized_email:
        return None

    sheets = get_sheets()
    accounts_sheet = sheets["user_accounts"]

    headers = accounts_sheet.row_values(1)

    required_headers = {
        "user_id",
        "email_address",
        "password_hash",
        "account_status",
        "role",
    }

    if not required_headers.issubset(set(headers)):
        raise ValueError(
            "The user_accounts worksheet is missing required columns."
        )

    accounts = accounts_sheet.get_all_records(
        default_blank="",
    )

    matches = [
        account
        for account in accounts
        if normalize_email(
            account.get("email_address", "")
        ) == normalized_email
    ]

    if len(matches) != 1:
        return None

    account = matches[0]

    if str(
        account.get("account_status", "")
    ).strip().casefold() != "active":
        return None

    if not normalize_user_id(account.get("user_id", "")):
        return None

    if not normalize_role(account.get("role", "")):
        return None

    return account


def authenticate_user(email, password):
    """
    Authenticate an account against user_accounts.

    Returns the account record on success, otherwise None.
    Raises worksheet/configuration errors to the caller.
    """

    account = get_active_user_by_email(email)

    if account is None:
        return None

    stored_hash = str(
        account.get("password_hash", "")
    ).strip()

    if not stored_hash:
        return None

    if not verify_password(password, stored_hash):
        return None

    return account


# --------------------------------------------------
# SHARED SESSION VERIFICATION
# --------------------------------------------------

def require_user_login(allowed_roles=None):
    """
    Require an authenticated, active shared user account.

    Optionally restrict access to a list or set of roles.
    Returns the verified account record.
    """

    if not st.session_state.get("user_authenticated"):
        st.warning("Please log in to access this page.")
        st.stop()

    user_id = normalize_user_id(
        st.session_state.get("user_id", "")
    )
    email = normalize_email(
        st.session_state.get("user_email", "")
    )
    role = normalize_role(
        st.session_state.get("user_role", "")
    )

    if not user_id or not email or not role:
        clear_user_session()
        st.error(
            "Your session is invalid. Please log in again."
        )
        st.stop()

    try:
        sheets = get_sheets()
        accounts_sheet = sheets["user_accounts"]

        headers = accounts_sheet.row_values(1)

        required_headers = {
            "user_id",
            "email_address",
            "account_status",
            "role",
        }

        if not required_headers.issubset(set(headers)):
            raise ValueError(
                "The user_accounts worksheet is missing required columns."
            )

        accounts = accounts_sheet.get_all_records(
            default_blank="",
        )

        matches = [
            account
            for account in accounts
            if normalize_user_id(
                account.get("user_id", "")
            ) == user_id
        ]

        if len(matches) != 1:
            clear_user_session()
            st.error(
                "Your account could not be verified. Please log in again."
            )
            st.stop()

        account = matches[0]

        account_email = normalize_email(
            account.get("email_address", "")
        )
        account_role = normalize_role(
            account.get("role", "")
        )
        account_status = str(
            account.get("account_status", "")
        ).strip().casefold()

        if (
            account_email != email
            or account_role != role
            or account_status != "active"
        ):
            clear_user_session()
            st.error(
                "Your account is no longer authorised. "
                "Please log in again or contact the administrator."
            )
            st.stop()

        if allowed_roles is not None:
            permitted_roles = {
                normalize_role(item)
                for item in allowed_roles
            }

            if account_role not in permitted_roles:
                st.error(
                    "You do not have permission to access this page."
                )
                st.stop()

        return account

    except Exception as exc:
        clear_user_session()
        print(f"SAES shared session verification error: {exc}")
        st.error(
            "Your account could not be verified right now. "
            "Please try again later."
        )
        st.stop()


# --------------------------------------------------
# LEGACY STUDENT SESSION VERIFICATION
# --------------------------------------------------

def require_student_login():
    """
    Verify a student through shared user_accounts authentication
    and link the account to the students worksheet using user_id.
    """

    # First verify the shared account and its student role.
    account = require_user_login(allowed_roles={"student"})

    user_id = normalize_user_id(
        account.get("user_id", "")
    )

    session_student_id = normalize_student_id(
        st.session_state.get("student_id", "")
    )

    if not user_id or not session_student_id:
        clear_user_session()
        clear_student_session()

        st.error(
            "Your student session is incomplete. "
            "Please log in again."
        )
        st.stop()

    try:
        sheets = get_sheets()
        students_sheet = sheets["students"]

        headers = students_sheet.row_values(1)

        required_headers = {
            "user_id",
            "student_id",
        }

        if not required_headers.issubset(set(headers)):
            raise ValueError(
                "The students worksheet is missing required columns."
            )

        student_records = students_sheet.get_all_records(
            default_blank=""
        )

        matching_students = [
            student
            for student in student_records
            if normalize_user_id(
                student.get("user_id", "")
            ) == user_id
        ]

        if len(matching_students) != 1:
            clear_user_session()
            clear_student_session()

            st.error(
                "Your student profile could not be linked "
                "to your account. Please contact the "
                "Academy administrator."
            )
            st.stop()

        student = matching_students[0]

        actual_student_id = normalize_student_id(
            student.get("student_id", "")
        )

        if (
            not actual_student_id
            or actual_student_id != session_student_id
        ):
            clear_user_session()
            clear_student_session()

            st.error(
                "Your student profile could not be verified. "
                "Please log in again or contact the Academy administrator."
            )
            st.stop()

        return str(student.get("student_id", "")).strip()

    except Exception as exc:
        clear_user_session()
        clear_student_session()

        print(
            f"SAES shared student verification error: {exc}"
        )

        st.error(
            "Your account could not be verified right now. "
            "Please try again later."
        )
        st.stop()
