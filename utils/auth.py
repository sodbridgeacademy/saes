
import os
import hashlib
import hmac

import extra_streamlit_components as stx
import streamlit as st
import secrets
import uuid

from datetime import datetime, timedelta, timezone

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
        "persistent_session_id",
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
    """Revoke and clear only the current browser session."""

    session_id = st.session_state.get("persistent_session_id", "")

    try:
        if session_id:
            _revoke_persistent_session(session_id)

        _delete_auth_cookie()

    except Exception as exc:
        print(f"SAES logout error: {exc}")

    finally:
        clear_user_session()


# --------------------------------------------------
# PERSISTENT SESSION CONFIGURATION
# --------------------------------------------------

COOKIE_NAME = "saes_auth_session"
COOKIE_MANAGER_KEY = "saes_auth_cookie_manager"

SESSION_DURATION_HOURS = 24

AUTH_SESSION_HEADERS = [
    "session_id",
    "user_id",
    "token_hash",
    "created_at",
    "expires_at",
    "last_activity_at",
    "session_status",
    "revoked_at",
]


def utc_now():
    """Return the current UTC time."""
    return datetime.now(timezone.utc)



def get_cookie_manager():
    """Return one CookieManager instance per Streamlit session."""

    if "_saes_cookie_manager" not in st.session_state:
        st.session_state["_saes_cookie_manager"] = (
            stx.CookieManager(key=COOKIE_MANAGER_KEY)
        )

    return st.session_state["_saes_cookie_manager"]


def _get_auth_sessions_sheet():
    """Return the auth_sessions worksheet after validating its headers."""

    sheets = get_sheets()
    worksheet = sheets["auth_sessions"]

    headers = worksheet.row_values(1)

    if headers != AUTH_SESSION_HEADERS:
        raise ValueError(
            "The auth_sessions worksheet headers are missing, "
            "misordered or do not match the required structure."
        )

    return worksheet


def _get_role_alias(role):
    """Convert legacy role names to canonical SAES roles."""

    aliases = {
        "student": "student",
        "learner": "student",
        "instructor": "instructor",
        "teacher": "instructor",
        "admin": "admin",
        "administrator": "admin",
    }

    return aliases.get(normalize_role(role), "")


def _revoke_persistent_session(session_id):
    """Revoke one persistent session by its session ID."""

    if not session_id:
        return

    worksheet = _get_auth_sessions_sheet()
    records = worksheet.get_all_records(default_blank="")

    matches = [
        (index + 2, record)
        for index, record in enumerate(records)
        if str(record.get("session_id", "")).strip() == session_id
    ]

    if len(matches) != 1:
        return

    row_number, record = matches[0]

    if str(record.get("session_status", "")).strip().casefold() != "active":
        return

    worksheet.update_cell(row_number, 7, "revoked")
    worksheet.update_cell(row_number, 8, utc_now().isoformat())


def _delete_auth_cookie(cookie_manager=None):
    """Delete the persistent authentication cookie."""

    if cookie_manager is None:
        cookie_manager = get_cookie_manager()

    cookie_manager.delete(
        cookie=COOKIE_NAME,
        key="saes_auth_cookie_delete",
    )


def create_persistent_session(account):
    """
    Create a new 24-hour persistent session.

    The raw token is stored only in the browser cookie.
    Only its SHA-256 hash is stored in Google Sheets.
    """

    user_id = normalize_user_id(account.get("user_id", ""))

    if not user_id:
        raise ValueError("Cannot create a session without a user ID.")

    now = utc_now()
    expires_at = now + timedelta(hours=SESSION_DURATION_HOURS)

    session_id = uuid.uuid4().hex
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    worksheet = _get_auth_sessions_sheet()

    worksheet.append_row(
        [
            session_id,
            user_id,
            token_hash,
            now.isoformat(),
            expires_at.isoformat(),
            now.isoformat(),
            "active",
            "",
        ],
        value_input_option="RAW",
    )

    cookie_manager = get_cookie_manager()

    cookie_manager.set(
        cookie=COOKIE_NAME,
        val=token,
        expires_at=expires_at,
        path="/",
        secure=True,
        same_site="strict",
        key="saes_auth_cookie_set",
    )

    st.session_state["persistent_session_id"] = session_id


def _restore_user_profile(account, role):
    """
    Restore the profile fields required by existing SAES pages.
    """

    user_id = normalize_user_id(account.get("user_id", ""))

    if role == "student":

        sheets = get_sheets()
        records = sheets["students"].get_all_records(default_blank="")

        matches = [
            record for record in records
            if normalize_user_id(record.get("user_id", "")) == user_id
        ]

        if len(matches) != 1:
            raise ValueError("Student profile could not be restored.")

        student_id = str(matches[0].get("student_id", "")).strip()

        if not student_id:
            raise ValueError("Student profile has no student ID.")

        st.session_state["student_authenticated"] = True
        st.session_state["student_email"] = normalize_email(
            account.get("email_address", "")
        )
        st.session_state["student_id"] = student_id

    elif role == "instructor":

        sheets = get_sheets()
        records = sheets["staff"].get_all_records(default_blank="")

        matches = [
            record for record in records
            if normalize_user_id(record.get("user_id", "")) == user_id
        ]

        if len(matches) != 1:
            raise ValueError("Instructor profile could not be restored.")

        staff_id = str(matches[0].get("staff_id", "")).strip()

        if not staff_id:
            raise ValueError("Instructor profile has no staff ID.")

        st.session_state["staff_id"] = staff_id
        st.session_state["staff_name"] = str(
            matches[0].get("full_name", "")
        ).strip()


def restore_persistent_session():
    """
    Restore authentication from a valid browser cookie.

    Returns True when restoration succeeds, otherwise False.
    """

    cookie_manager = get_cookie_manager()
    token = cookie_manager.get(COOKIE_NAME)

    if not token:
        return False

    session_id = ""

    try:
        token_hash = hashlib.sha256(
            str(token).encode("utf-8")
        ).hexdigest()

        worksheet = _get_auth_sessions_sheet()
        records = worksheet.get_all_records(default_blank="")

        matches = [
            (index + 2, record)
            for index, record in enumerate(records)
            if hmac.compare_digest(
                str(record.get("token_hash", "")),
                token_hash,
            )
        ]

        if len(matches) != 1:
            _delete_auth_cookie(cookie_manager)()
            return False

        row_number, session_record = matches[0]

        session_id = str(
            session_record.get("session_id", "")
        ).strip()

        if str(
            session_record.get("session_status", "")
        ).strip().casefold() != "active":
            _delete_auth_cookie()
            return False

        expires_at = datetime.fromisoformat(
            str(session_record.get("expires_at", "")).replace(
                "Z", "+00:00"
            )
        )

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if utc_now() >= expires_at:
            _revoke_persistent_session(
                str(session_record.get("session_id", ""))
            )
            _delete_auth_cookie()
            return False

        user_id = normalize_user_id(
            session_record.get("user_id", "")
        )

        sheets = get_sheets()
        accounts = sheets["user_accounts"].get_all_records(
            default_blank=""
        )

        account_matches = [
            account for account in accounts
            if normalize_user_id(account.get("user_id", "")) == user_id
        ]

        if len(account_matches) != 1:
            _revoke_persistent_session(
                str(session_record.get("session_id", ""))
            )
            _delete_auth_cookie()
            return False

        account = account_matches[0]

        if str(
            account.get("account_status", "")
        ).strip().casefold() != "active":
            _revoke_persistent_session(
                str(session_record.get("session_id", ""))
            )
            _delete_auth_cookie()
            return False

        role = _get_role_alias(account.get("role", ""))

        if not role:
            _revoke_persistent_session(
                str(session_record.get("session_id", ""))
            )
            _delete_auth_cookie()
            return False

        # Re-establish the shared authentication state.
        set_user_session(account)

        # Ensure the role uses the canonical SAES value.
        st.session_state["user_role"] = role

        # Restore the relevant student or instructor profile.
        _restore_user_profile(account, role)

        # Preserve the ID of this particular browser session.
        st.session_state["persistent_session_id"] = str(
            session_record.get("session_id", "")
        ).strip()

        # Record restoration activity without extending expiry.
        worksheet.update_cell(
            row_number,
            6,
            utc_now().isoformat(),
        )

        return True

    except Exception as exc:
        print(f"SAES persistent session restoration error: {exc}")

        try:
            if session_id:
                _revoke_persistent_session(session_id)

            _delete_auth_cookie(cookie_manager)

        except Exception as cleanup_error:
            print(
                f"SAES persistent session cleanup error: {cleanup_error}"
            )

        clear_user_session()
        return False


def verify_current_persistent_session():
    """Verify that the current browser session remains active and unexpired."""

    session_id = str(
        st.session_state.get("persistent_session_id", "")
    ).strip()

    if not session_id:
        return False

    worksheet = _get_auth_sessions_sheet()
    records = worksheet.get_all_records(default_blank="")

    matches = [
        record for record in records
        if str(record.get("session_id", "")).strip() == session_id
    ]

    if len(matches) != 1:
        return False

    record = matches[0]

    if str(record.get("session_status", "")).strip().casefold() != "active":
        return False

    expires_at = datetime.fromisoformat(
        str(record.get("expires_at", "")).replace("Z", "+00:00")
    )

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    return utc_now() < expires_at


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

    Restore a persistent session when the Streamlit session
    state is missing.
    """

    if not st.session_state.get("user_authenticated"):

        if not restore_persistent_session():
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
        logout_user()
        st.error("Your session is invalid. Please log in again.")
        st.stop()

    try:
        # Check the actual persistent session record.
        if not verify_current_persistent_session():
            logout_user()
            st.warning("Your session has expired. Please log in again.")
            st.stop()

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

        accounts = accounts_sheet.get_all_records(default_blank="")

        matches = [
            account for account in accounts
            if normalize_user_id(
                account.get("user_id", "")
            ) == user_id
        ]

        if len(matches) != 1:
            logout_user()
            st.error(
                "Your account could not be verified. Please log in again."
            )
            st.stop()

        account = matches[0]

        account_email = normalize_email(
            account.get("email_address", "")
        )
        account_role = _get_role_alias(
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
            logout_user()
            st.error(
                "Your account is no longer authorised. "
                "Please log in again or contact the administrator."
            )
            st.stop()

        if allowed_roles is not None:
            permitted_roles = {
                _get_role_alias(item)
                for item in allowed_roles
            }

            if role not in permitted_roles:
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
            logout_user()

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
