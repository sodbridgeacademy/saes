
import os
import hashlib
import hmac
import streamlit as st

from utils.sheets import get_sheets



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


def normalize_email(email):
    """Normalize an email address for matching."""

    return str(email or "").strip().casefold()


def normalize_student_id(student_id):
    """Normalize a student ID for matching."""

    return str(student_id or "").strip().casefold()


def clear_student_session():
    """Clear the student's authentication session."""

    for key in (
        "student_authenticated",
        "student_id",
        "student_email",
    ):
        st.session_state.pop(key, None)


def require_student_login():
    """
    Require an authenticated student with a currently active,
    uniquely identifiable account in the student_accounts sheet.

    Fails closed if account verification cannot be completed.
    """

    if not st.session_state.get("student_authenticated"):
        st.warning("Please log in to access this page.")
        st.stop()

    student_id = str(
        st.session_state.get("student_id", "")
    ).strip()

    student_email = normalize_email(
        st.session_state.get("student_email", "")
    )

    if not student_id or not student_email:
        clear_student_session()
        st.error(
            "Your session is invalid. Please log in again."
        )
        st.stop()

    try:
        sheets = get_sheets()
        accounts_sheet = sheets["student_accounts"]

        headers = accounts_sheet.row_values(1)

        required_headers = {
            "email_address",
            "student_id",
            "account_status",
        }

        if not required_headers.issubset(set(headers)):
            clear_student_session()
            st.error(
                "Account verification is unavailable. "
                "Please contact the Academy administrator."
            )
            st.stop()

        accounts = accounts_sheet.get_all_records()

        normalized_id = normalize_student_id(student_id)

        # Match either identifier so duplicate or conflicting
        # account records cannot be silently ignored.
        related_accounts = [
            account
            for account in accounts
            if (
                normalize_student_id(
                    account.get("student_id", "")
                ) == normalized_id
                or normalize_email(
                    account.get("email_address", "")
                ) == student_email
            )
        ]

        # Exactly one account must be associated with these
        # identifiers, and both identifiers must agree.
        if len(related_accounts) != 1:
            clear_student_session()
            st.error(
                "Your account could not be verified. "
                "Please log in again or contact the "
                "Academy administrator."
            )
            st.stop()

        account = related_accounts[0]

        account_id = normalize_student_id(
            account.get("student_id", "")
        )
        account_email = normalize_email(
            account.get("email_address", "")
        )
        account_status = str(
            account.get("account_status", "")
        ).strip().casefold()

        if (
            account_id != normalized_id
            or account_email != student_email
            or account_status != "active"
        ):
            clear_student_session()
            st.error(
                "Your account is no longer authorised. "
                "Please contact the Academy administrator."
            )
            st.stop()

        # Return the canonical ID stored in the account sheet.
        return str(account["student_id"]).strip()

    except Exception as exc:
        clear_student_session()
        print(f"SAES student session verification error: {exc}")
        st.error(
            "Your account could not be verified right now. "
            "Please try again later."
        )
        st.stop()
