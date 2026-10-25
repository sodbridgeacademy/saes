
import hashlib
import hmac
import re
import uuid
from datetime import datetime, timezone

import streamlit as st

from utils.sheets import get_sheets
from utils.auth import hash_password


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="Staff Registration | SAES",
    page_icon="📝",
    layout="centered",
)

INVITATION_HEADERS = [
    "invitation_id",
    "invited_email",
    "role",
    "token_hash",
    "status",
    "expires_at",
    "created_at",
    "created_by",
    "used_at",
    "used_by",
]

USER_ACCOUNT_HEADERS = [
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

STAFF_HEADERS = [
    "staff_id",
    "user_id",
    "full_name",
    "email_address",
    "username",
    "role",
    "status",
    "created_at",
    "created_by",
]

APPROVED_ROLES = {"instructor", "admin"}
MIN_PASSWORD_LENGTH = 12


# --------------------------------------------------
# GENERAL HELPERS
# --------------------------------------------------

def now_utc():
    return datetime.now(timezone.utc)


def normalise_email(value):
    return str(value).strip().lower()


def token_digest(token):
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def parse_datetime(value):
    if not str(value).strip():
        return None

    try:
        from datetime import timedelta

        parsed = datetime.fromisoformat(
            str(value).strip().replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None


def get_headers(sheet):
    return [
        str(header).strip()
        for header in sheet.row_values(1)
    ]


def validate_headers(sheet, required_headers, sheet_name):
    headers = get_headers(sheet)

    missing = [
        header
        for header in required_headers
        if header not in headers
    ]

    if missing:
        raise ValueError(
            f"{sheet_name} is missing required columns: "
            + ", ".join(missing)
        )

    return headers


def append_record(sheet, required_headers, record, sheet_name):
    headers = validate_headers(
        sheet,
        required_headers,
        sheet_name,
    )

    row = [
        record.get(header, "")
        for header in headers
    ]

    sheet.append_row(
        row,
        value_input_option="RAW",
    )


def find_row_by_value(sheet, column_name, target_value):
    headers = get_headers(sheet)

    if column_name not in headers:
        raise ValueError(
            f"Missing column '{column_name}' in worksheet."
        )

    column_index = headers.index(column_name)

    for row_number, row in enumerate(
        sheet.get_all_values()[1:],
        start=2,
    ):
        value = (
            row[column_index]
            if column_index < len(row)
            else ""
        )

        if str(value).strip() == str(target_value).strip():
            return row_number

    return None


def update_record(sheet, row_number, updates):
    headers = get_headers(sheet)

    for column_name, value in updates.items():
        if column_name not in headers:
            raise ValueError(
                f"Missing worksheet column: {column_name}"
            )

        sheet.update_cell(
            row_number,
            headers.index(column_name) + 1,
            value,
        )


def email_exists(user_accounts, email):
    records = user_accounts.get_all_records(
        default_blank="",
    )

    return any(
        normalise_email(row.get("email_address", "")) == email
        for row in records
    )


def username_exists(staff_sheet, username):
    records = staff_sheet.get_all_records(
        default_blank="",
    )

    return any(
        str(row.get("username", "")).strip().casefold()
        == username.casefold()
        for row in records
    )


# --------------------------------------------------
# READ AND VALIDATE INVITATION
# --------------------------------------------------

st.title("📝 Sodbridge Academy Staff Registration")
st.caption(
    "Complete your staff account registration using "
    "the invitation sent to your email address."
)

invite_token = str(
    st.query_params.get("invite", "")
).strip()

# Keep the token available during Streamlit reruns.
if invite_token:
    st.session_state["staff_registration_token"] = invite_token

invite_token = st.session_state.get(
    "staff_registration_token",
    "",
)

if not invite_token:
    st.error(
        "No invitation token was provided. "
        "Please open the registration link from your invitation email."
    )
    st.stop()

if len(invite_token) > 512:
    st.error("The invitation link is invalid.")
    st.stop()

try:
    sheets = get_sheets()

    invitation_sheet = sheets["staff_invitations"]
    user_accounts = sheets["user_accounts"]
    staff_sheet = sheets["staff"]

    validate_headers(
        invitation_sheet,
        INVITATION_HEADERS,
        "staff_invitations",
    )

    validate_headers(
        user_accounts,
        USER_ACCOUNT_HEADERS,
        "user_accounts",
    )

    validate_headers(
        staff_sheet,
        STAFF_HEADERS,
        "staff",
    )

    invitation_records = invitation_sheet.get_all_records(
        default_blank="",
    )

except Exception as exc:
    st.error(
        "Registration is temporarily unavailable. "
        "Please contact the SAES administrator."
    )
    print(
        "SAES registration worksheet error: "
        f"{type(exc).__name__}: {exc}"
    )
    st.stop()


provided_digest = token_digest(invite_token)

invitation = None

for record in invitation_records:
    stored_digest = str(
        record.get("token_hash", "")
    ).strip()

    if stored_digest and hmac.compare_digest(
        stored_digest,
        provided_digest,
    ):
        invitation = record
        break


if invitation is None:
    st.error(
        "This invitation is invalid or could not be found. "
        "Please contact the SAES administrator."
    )
    st.stop()


invitation_id = str(
    invitation.get("invitation_id", "")
).strip()

invited_email = normalise_email(
    invitation.get("invited_email", "")
)

assigned_role = str(
    invitation.get("role", "")
).strip().lower()

invitation_status = str(
    invitation.get("status", "")
).strip().lower()

expiry = parse_datetime(
    invitation.get("expires_at", "")
)

if invitation_status != "pending":
    st.error(
        "This invitation has already been used, revoked, "
        "or is otherwise no longer available."
    )
    st.stop()

if expiry is None:
    st.error(
        "This invitation has an invalid expiry date. "
        "Please contact the SAES administrator."
    )
    st.stop()

if now_utc() >= expiry:
    st.error(
        "This invitation has expired. "
        "Please request a new invitation from the SAES administrator."
    )
    st.stop()

if assigned_role not in APPROVED_ROLES:
    st.error(
        "This invitation contains an unsupported staff role. "
        "Please contact the SAES administrator."
    )
    st.stop()

if not invited_email:
    st.error(
        "This invitation has no valid email address. "
        "Please contact the SAES administrator."
    )
    st.stop()


# --------------------------------------------------
# REGISTRATION FORM
# --------------------------------------------------

st.success("Your invitation is valid.")
st.write(f"**Invited email:** {invited_email}")
st.write(f"**Assigned role:** {assigned_role.title()}")
st.caption(
    "Your email address and role are fixed by the invitation "
    "and cannot be changed on this page."
)

with st.form("staff_registration_form"):
    full_name = st.text_input(
        "Full name",
        placeholder="Enter your full name",
        max_chars=120,
    )

    username = st.text_input(
        "Username",
        placeholder="Choose a username",
        max_chars=40,
        help=(
            "Use 3–40 characters: letters, numbers, "
            "periods, underscores or hyphens."
        ),
    )

    password = st.text_input(
        "Create password",
        type="password",
        help=(
            f"Use at least {MIN_PASSWORD_LENGTH} characters."
        ),
    )

    confirm_password = st.text_input(
        "Confirm password",
        type="password",
    )

    submitted = st.form_submit_button(
        "Create Staff Account",
        use_container_width=True,
    )


# --------------------------------------------------
# PROCESS REGISTRATION
# --------------------------------------------------

if submitted:
    full_name = full_name.strip()
    username = username.strip()

    errors = []

    if len(full_name) < 2:
        errors.append("Enter your full name.")

    if not re.fullmatch(
        r"[A-Za-z0-9_.-]{3,40}",
        username,
    ):
        errors.append(
            "Username must be 3–40 characters and contain only "
            "letters, numbers, periods, underscores or hyphens."
        )

    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(
            f"Your password must contain at least "
            f"{MIN_PASSWORD_LENGTH} characters."
        )

    if len(password) > 1024:
        errors.append("Your password is too long.")

    if password != confirm_password:
        errors.append("The passwords do not match.")

    if errors:
        for error in errors:
            st.error(error)

    else:
        user_id = "USR-" + uuid.uuid4().hex[:12].upper()
        staff_id = "STF-" + uuid.uuid4().hex[:12].upper()
        created_at = now_utc().isoformat()

        account_record = {
            "user_id": user_id,
            "email_address": invited_email,
            "password_hash": hash_password(password),
            "account_status": "active",
            "role": assigned_role,
            "reset_code_hash": "",
            "reset_expires_at": "",
            "reset_attempts": 0,
            "reset_last_sent_at": "",
            "password_change_required": "FALSE",
            "created_at": created_at,
            "last_login_at": "",
        }

        staff_record = {
            "staff_id": staff_id,
            "user_id": user_id,
            "full_name": full_name,
            "email_address": invited_email,
            "username": username,
            "role": assigned_role,
            "status": "active",
            "created_at": created_at,
            "created_by": invitation.get(
                "created_by",
                "invitation",
            ),
        }

        account_row_number = None
        staff_row_number = None

        try:
            # Re-read the invitation immediately before writing.
            # This reduces the chance of using a revoked invitation.
            fresh_invitations = invitation_sheet.get_all_records(
                default_blank="",
            )

            fresh_invitation = next(
                (
                    row
                    for row in fresh_invitations
                    if str(row.get("invitation_id", "")).strip()
                    == invitation_id
                ),
                None,
            )

            if fresh_invitation is None:
                st.error("This invitation could not be found.")
                st.stop()

            fresh_digest = str(
                fresh_invitation.get("token_hash", "")
            ).strip()

            if not fresh_digest or not hmac.compare_digest(
                fresh_digest,
                provided_digest,
            ):
                st.error("This invitation is no longer valid.")
                st.stop()

            fresh_status = str(
                fresh_invitation.get("status", "")
            ).strip().lower()

            fresh_expiry = parse_datetime(
                fresh_invitation.get("expires_at", "")
            )

            if (
                fresh_status != "pending"
                or fresh_expiry is None
                or now_utc() >= fresh_expiry
            ):
                st.error(
                    "This invitation has expired or is no longer "
                    "available for registration."
                )
                st.stop()

            if email_exists(user_accounts, invited_email):
                st.error(
                    "An account already exists for this email address. "
                    "Please contact the SAES administrator."
                )
                st.stop()

            if username_exists(staff_sheet, username):
                st.error(
                    "That username is already taken. "
                    "Please choose another username."
                )
                st.stop()

            # Write the account first, then the associated staff record.
            append_record(
                user_accounts,
                USER_ACCOUNT_HEADERS,
                account_record,
                "user_accounts",
            )

            account_row_number = find_row_by_value(
                user_accounts,
                "user_id",
                user_id,
            )

            append_record(
                staff_sheet,
                STAFF_HEADERS,
                staff_record,
                "staff",
            )

            staff_row_number = find_row_by_value(
                staff_sheet,
                "staff_id",
                staff_id,
            )

            # Mark the invitation used after both records are created.
            invitation_row_number = find_row_by_value(
                invitation_sheet,
                "invitation_id",
                invitation_id,
            )

            if invitation_row_number is None:
                raise RuntimeError(
                    "Could not locate the invitation to complete registration."
                )

            update_record(
                invitation_sheet,
                invitation_row_number,
                {
                    "status": "used",
                    "used_at": now_utc().isoformat(),
                    "used_by": user_id,
                },
            )

            # Do not retain the raw token after successful registration.
            st.session_state.pop(
                "staff_registration_token",
                None,
            )

            st.success(
                "Your staff account has been created successfully."
            )

            st.info(
                "You can now sign in through the SAES login page "
                "using your email address and password."
            )

            st.session_state["staff_registration_complete"] = True

        except Exception as exc:
            # Best-effort cleanup if one of the writes fails.
            # Google Sheets does not provide a multi-worksheet transaction.
            cleanup_errors = []

            if staff_row_number is not None:
                try:
                    staff_sheet.delete_rows(staff_row_number)
                except Exception as cleanup_exc:
                    cleanup_errors.append(
                        f"staff cleanup: {type(cleanup_exc).__name__}"
                    )

            if account_row_number is not None:
                try:
                    user_accounts.delete_rows(account_row_number)
                except Exception as cleanup_exc:
                    cleanup_errors.append(
                        f"account cleanup: {type(cleanup_exc).__name__}"
                    )

            st.error(
                "We could not complete registration. "
                "Please do not submit repeatedly. Contact the "
                "SAES administrator to check the account records "
                "before trying again."
            )

            print(
                "SAES registration error: "
                f"{type(exc).__name__}: {exc}"
            )

            if cleanup_errors:
                print(
                    "SAES registration cleanup requires review: "
                    + "; ".join(cleanup_errors)
                )


# --------------------------------------------------
# SUCCESS STATE
# --------------------------------------------------

if st.session_state.get("staff_registration_complete"):
    st.caption(
        "For security, your invitation link should not be shared "
        "or used again."
    )
