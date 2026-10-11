import os
import hashlib
import hmac
import streamlit as st


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


def require_student_login():
    """Stop a page from displaying content to unauthenticated users."""

    if not st.session_state.get("student_authenticated"):
        st.warning("Please log in to access this page.")
        st.stop()

    student_id = str(
        st.session_state.get("student_id", "")
    ).strip()

    if not student_id:
        st.session_state.pop("student_authenticated", None)
        st.session_state.pop("student_id", None)
        st.session_state.pop("student_email", None)

        st.error("Your session is invalid. Please log in again.")
        st.stop()

    return student_id
