
import hashlib
import re
import secrets
import uuid

import smtplib
import ssl
import html

from email.message import EmailMessage
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from utils.sheets import get_sheets


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="Staff Invitations | SAES",
    page_icon="✉️",
    layout="wide",
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

# Only roles explicitly approved by the application.
# Add other roles here only when they are required.
APPROVED_ROLES = ["instructor", "admin"]

INVITATION_HOURS = 24


# --------------------------------------------------
# ADMIN AUTHENTICATION
# --------------------------------------------------

if "admin_authenticated" not in st.session_state:
    st.session_state["admin_authenticated"] = False

if not st.session_state["admin_authenticated"]:
    st.title("✉️ Staff Invitations")
    st.warning("Authorised administrators only.")
    st.info(
        "Sign in through the SAES Admin Dashboard "
        "before managing staff invitations."
    )
    st.stop()


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def now_utc():
    return datetime.now(timezone.utc)


def normalise_email(email):
    return str(email).strip().lower()


def valid_email(email):
    return bool(
        re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            email,
        )
    )


def token_digest(token):
    """Store only a SHA-256 hash of the invitation token."""
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def parse_datetime(value):
    if not str(value).strip():
        return None

    try:
        parsed = pd.Timestamp(str(value).strip())

        if parsed.tzinfo is None:
            parsed = parsed.tz_localize("UTC")
        else:
            parsed = parsed.tz_convert("UTC")

        return parsed.to_pydatetime()
    except (ValueError, TypeError):
        return None


def get_header_positions(sheet):
    headers = sheet.row_values(1)

    positions = {
        str(header).strip(): index + 1
        for index, header in enumerate(headers)
        if str(header).strip()
    }

    missing = [
        header
        for header in INVITATION_HEADERS
        if header not in positions
    ]

    if missing:
        raise ValueError(
            "The staff_invitations worksheet is missing "
            "these headers: "
            + ", ".join(missing)
        )

    return positions


def load_invitations(sheet):
    get_header_positions(sheet)

    records = sheet.get_all_records(
        default_blank="",
    )

    if not records:
        return pd.DataFrame(columns=INVITATION_HEADERS)

    frame = pd.DataFrame(records)

    for header in INVITATION_HEADERS:
        if header not in frame.columns:
            frame[header] = ""

    return frame[INVITATION_HEADERS]


def find_row_by_invitation_id(sheet, invitation_id):
    positions = get_header_positions(sheet)
    id_column = positions["invitation_id"]

    values = sheet.get_all_values()

    for row_number, row in enumerate(values[1:], start=2):
        if (
            len(row) >= id_column
            and str(row[id_column - 1]).strip()
            == str(invitation_id).strip()
        ):
            return row_number

    return None


def update_invitation(sheet, invitation_id, updates):
    positions = get_header_positions(sheet)

    row_number = find_row_by_invitation_id(
        sheet,
        invitation_id,
    )

    if row_number is None:
        raise ValueError(
            "The selected invitation could not be found."
        )

    for header, value in updates.items():
        if header not in positions:
            raise ValueError(
                f"Missing worksheet column: {header}"
            )

        sheet.update_cell(
            row_number,
            positions[header],
            value,
        )


def effective_status(row):
    stored_status = str(row.get("status", "")).strip().lower()

    if stored_status != "pending":
        return stored_status.title() or "Unknown"

    expiry = parse_datetime(row.get("expires_at", ""))

    if expiry is None:
        return "Invalid expiry"

    if now_utc() >= expiry:
        return "Expired"

    return "Pending"



def send_invitation_email(email, role, registration_url):
    """Send a staff invitation using the configured SMTP server."""

    required_secrets = [
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
    ]

    config = {}

    for key in required_secrets:
        try:
            config[key] = st.secrets[key]
        except (KeyError, FileNotFoundError):
            raise RuntimeError(
                f"Missing SMTP configuration: {key}"
            )

    host = str(config["SMTP_HOST"]).strip()
    port = int(config["SMTP_PORT"])
    username = str(config["SMTP_USERNAME"]).strip()
    password = str(config["SMTP_PASSWORD"])

    safe_role = html.escape(role.title(), quote=True)
    safe_url = html.escape(registration_url, quote=True)

    if not host or not username or not password:
        raise RuntimeError(
            "SMTP configuration contains an empty value."
        )

    message = EmailMessage()
    message["Subject"] = (
        "You're invited to join Sodbridge Academy"
    )
    message["From"] = username
    message["To"] = email

    plain_text = f"""Hello,

You have been invited to join Sodbridge Academy's staff platform.

Your assigned role: {role.title()}

To complete your registration, please open the secure invitation link below:

{registration_url}

This invitation expires in {INVITATION_HOURS} hours  and can only be used once. It is intended for your email address and should not be shared with anyone else.

If you have any questions, please contact the Sodbridge Academy administration.

Regards,
Sodbridge Academy Administration
"""

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:Arial,sans-serif;
                 color:#222;line-height:1.6;">
        <p>Hello,</p>

        <p>
            You have been invited to join
            <strong>Sodbridge Academy</strong>'s staff platform.
        </p>

        <p>
            <strong>Your assigned role:</strong>
            {safe_role}
        </p>

        <p>
            To complete your registration, use the secure
            invitation link below:
        </p>

        <p style="margin:28px 0;">
            <a href="{safe_url}"
               style="background-color:#17365D;
                      color:#ffffff;
                      padding:12px 20px;
                      text-decoration:none;
                      border-radius:5px;
                      display:inline-block;">
                Complete Your Registration
            </a>
        </p>

        <p>
            This invitation expires in 24 hours and can only
            be used once. It is intended for your email address
            and should not be shared with anyone else.
        </p>

        <p>
            If you have any questions, please contact the
            Sodbridge Academy Manager.
        </p>

        <p>
            Regards,<br>
            <strong>Team Sodbridge</strong>
        </p>
    </body>
    </html>
    """

    message.set_content(plain_text)
    message.add_alternative(html_content, subtype="html")

    context = ssl.create_default_context()

    try:
        if port == 465:
            with smtplib.SMTP_SSL(
                host,
                port,
                context=context,
                timeout=20,
            ) as server:
                server.login(username, password)
                server.send_message(message)

        else:
            with smtplib.SMTP(
                host,
                port,
                timeout=20,
            ) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(username, password)
                server.send_message(message)

    except (smtplib.SMTPException, OSError) as exc:
        raise RuntimeError(
            "The invitation email could not be sent. "
            "Check your SMTP settings and email provider."
        ) from exc


# --------------------------------------------------
# LOAD WORKSHEET
# --------------------------------------------------

st.title("✉️ Staff Invitations")
st.caption(
    "Create and manage secure, time-limited invitations "
    "for Sodbridge Academy staff."
)

try:
    sheets = get_sheets()
    invitation_sheet = sheets["staff_invitations"]

    invitations = load_invitations(invitation_sheet)

except Exception as exc:
    st.error(
        "Unable to load staff invitations. "
        "Check the worksheet name, headers and permissions."
    )
    print(f"SAES staff invitations error: {exc}")
    st.stop()



# --------------------------------------------------
# CREATE INVITATION
# --------------------------------------------------

st.header("Create a Staff Invitation")

st.info(
    f"Invitation links expire in {INVITATION_HOURS} hours "
    "and can be used only once."
)

with st.form("create_staff_invitation"):
    invited_email_input = st.text_input(
        "Staff member's email address",
        placeholder="name@example.com",
    )

    invited_role = st.selectbox(
        "Assigned role",
        APPROVED_ROLES,
        help=(
            "The invited person cannot change this role "
            "during registration."
        ),
    )

    submitted = st.form_submit_button(
        "Generate and Email Invitation",
        use_container_width=True,
    )


if submitted:
    email = normalise_email(invited_email_input)

    # Validate input before creating any records.
    if not email:
        st.error("Enter an email address.")

    elif not valid_email(email):
        st.error("Enter a valid email address.")

    elif invited_role not in APPROVED_ROLES:
        st.error("The selected staff role is not permitted.")

    else:
        # Check configuration before saving an invitation.
        try:
            base_url = str(
                st.secrets["APP_BASE_URL"]
            ).strip().rstrip("/")
        except (KeyError, FileNotFoundError):
            base_url = ""

        if not base_url.startswith(("https://", "http://")):
            st.error(
                "APP_BASE_URL is missing or invalid. "
                "Configure it in Streamlit Secrets first."
            )

        else:
            try:
                # Refresh worksheet data before checking duplicates.
                invitations = load_invitations(invitation_sheet)

                existing_pending = invitations[
                    invitations["invited_email"]
                    .astype(str)
                    .str.strip()
                    .str.lower()
                    .eq(email)
                    &
                    invitations["status"]
                    .astype(str)
                    .str.strip()
                    .str.lower()
                    .eq("pending")
                ]

                unexpired_pending = existing_pending[
                    existing_pending.apply(
                        lambda row: effective_status(row) == "Pending",
                        axis=1,
                    )
                ]

                if not unexpired_pending.empty:
                    st.warning(
                        "An unexpired pending invitation already "
                        "exists for this email. Revoke it before "
                        "creating another invitation."
                    )

                else:
                    # Generate a new, unpredictable token.
                    raw_token = secrets.token_urlsafe(32)

                    created_at = now_utc()
                    expires_at = (
                        created_at
                        + timedelta(hours=INVITATION_HOURS)
                    )

                    invitation_id = (
                        "INV-"
                        + uuid.uuid4().hex[:12].upper()
                    )

                    # IMPORTANT:
                    # Verify this route against the actual deployed
                    # Streamlit page before sending real invitations.
                    registration_url = (
                        f"{base_url}/Staff_Registration"
                        f"?invite={raw_token}"
                    )

                    invitation_record = {
                        "invitation_id": invitation_id,
                        "invited_email": email,
                        "role": invited_role,
                        "token_hash": token_digest(raw_token),
                        "status": "pending",
                        "expires_at": expires_at.isoformat(),
                        "created_at": created_at.isoformat(),
                        "created_by": "shared_admin",
                        "used_at": "",
                        "used_by": "",
                    }

                    # Validate the worksheet schema.
                    headers = [
                        str(header).strip()
                        for header in invitation_sheet.row_values(1)
                    ]

                    missing_headers = [
                        header
                        for header in INVITATION_HEADERS
                        if header not in headers
                    ]

                    unexpected_headers = [
                        header
                        for header in headers
                        if header
                        and header not in INVITATION_HEADERS
                    ]

                    if missing_headers:
                        raise ValueError(
                            "Missing worksheet headers: "
                            + ", ".join(missing_headers)
                        )

                    if unexpected_headers:
                        raise ValueError(
                            "Unexpected non-empty worksheet headers: "
                            + ", ".join(unexpected_headers)
                        )

                    row = [
                        invitation_record.get(header, "")
                        for header in headers
                    ]

                    # Save the invitation before sending the email.
                    invitation_sheet.append_row(
                        row,
                        value_input_option="RAW",
                    )

                    # Retain the link in this admin session so that
                    # a failed email can be retried using the same
                    # invitation and token.
                    st.session_state["new_staff_invitation"] = {
                        "invitation_id": invitation_id,
                        "email": email,
                        "role": invited_role,
                        "url": registration_url,
                        "expires_at": expires_at.isoformat(),
                        "email_sent": False,
                    }

                    try:
                        send_invitation_email(
                            email=email,
                            role=invited_role,
                            registration_url=registration_url,
                        )

                        st.session_state[
                            "new_staff_invitation"
                        ]["email_sent"] = True

                        st.success(
                            f"Invitation created and email sent to {email}."
                        )

                    except Exception as email_exc:
                        st.error(
                            "The invitation was saved, but email "
                            "delivery failed. Use the retry option "
                            "below rather than creating another "
                            "invitation."
                        )

                        print(
                            "SAES invitation email error: "
                            f"{type(email_exc).__name__}: {email_exc}"
                        )

            except Exception as exc:
                st.error(
                    "Could not complete the invitation process. "
                    "Check the worksheet and application configuration."
                )
                print(
                    "SAES invitation creation error: "
                    f"{type(exc).__name__}: {exc}"
                )


# --------------------------------------------------
# SHOW NEW INVITATION AND EMAIL STATUS
# --------------------------------------------------

new_invitation = st.session_state.get(
    "new_staff_invitation"
)

if new_invitation:
    st.divider()
    st.subheader("New Invitation")

    st.write(f"**Email:** {new_invitation['email']}")
    st.write(f"**Assigned role:** {new_invitation['role']}")
    st.write(f"**Invitation ID:** {new_invitation['invitation_id']}")
    st.write(f"**Expires:** {new_invitation['expires_at']}")

    if new_invitation.get("email_sent", False):
        st.success(
            "The email was accepted by the configured SMTP server."
        )
    else:
        st.warning(
            "The invitation exists, but email delivery has not "
            "been confirmed."
        )

        if st.button(
            "Retry Sending Invitation Email",
            key="retry_invitation_email",
        ):
            # Avoid retrying an invitation that has already expired
            # or been revoked.
            try:
                current_invitations = load_invitations(
                    invitation_sheet
                )

                match = current_invitations[
                    current_invitations["invitation_id"]
                    .astype(str)
                    .str.strip()
                    .eq(str(new_invitation["invitation_id"]))
                ]

                if match.empty:
                    st.error(
                        "Invitation not found. Create a new invitation "
                        "after checking the worksheet."
                    )

                else:
                    current_record = match.iloc[0]
                    current_status = effective_status(current_record)

                    if current_status != "Pending":
                        st.error(
                            "This invitation is no longer valid "
                            f"(status: {current_status}). "
                            "Create a new invitation if needed."
                        )

                    else:
                        send_invitation_email(
                            email=new_invitation["email"],
                            role=new_invitation["role"],
                            registration_url=new_invitation["url"],
                        )

                        st.session_state[
                            "new_staff_invitation"
                        ]["email_sent"] = True

                        st.success("Invitation email sent.")
                        st.rerun()

            except Exception as retry_exc:
                st.error(
                    "Email retry failed. Check the SMTP settings "
                    "and try again."
                )

                print(
                    "SAES invitation retry error: "
                    f"{type(retry_exc).__name__}: {retry_exc}"
                )

    st.caption(
        "The raw token is not stored in Google Sheets. "
        "Keep the invitation link private."
    )

    # Show the link to the admin for recovery or manual delivery.
    # It is also the link reused for email retries.
    with st.expander("View invitation link"):
        st.code(new_invitation["url"], language=None)

    if st.button(
        "Dismiss Invitation Details",
        key="dismiss_new_invitation",
    ):
        del st.session_state["new_staff_invitation"]
        st.rerun()
