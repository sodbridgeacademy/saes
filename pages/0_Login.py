import streamlit as st

from utils.sheets import get_sheets
from utils.auth import verify_password


def normalize_email(email):
    return str(email).strip().casefold()


st.title("🔐 SAES Student Login")

if st.session_state.get("student_authenticated"):
    st.success(
        f"Logged in as {st.session_state.get('student_email', '')}"
    )

    st.write(
        f"Student ID: {st.session_state.get('student_id', '')}"
    )

    if st.button("Log Out"):
        for key in [
            "student_authenticated",
            "student_id",
            "student_email",
        ]:
            st.session_state.pop(key, None)

        st.rerun()

else:
    with st.form("student_login"):
        email = st.text_input("Email Address")

        password = st.text_input(
            "Password",
            type="password",
        )

        submit = st.form_submit_button("Log In")

    if submit:
        email = normalize_email(email)

        if not email or not password:
            st.error("Enter your email address and password.")

        else:
            try:
                sheets = get_sheets()
                accounts_sheet = sheets["student_accounts"]

                headers = accounts_sheet.row_values(1)

                required_headers = [
                    "email_address",
                    "student_id",
                    "password_hash",
                    "account_status",
                ]

                if not all(
                    header in headers
                    for header in required_headers
                ):
                    st.error(
                        "The student account sheet is not "
                        "configured correctly. Contact the "
                        "Academy administrator."
                    )

                else:
                    accounts = accounts_sheet.get_all_records()

                    matching_accounts = [
                        account
                        for account in accounts
                        if normalize_email(
                            account.get("email_address", "")
                        ) == email
                    ]

                    # Fail closed if duplicate account records exist.
                    if len(matching_accounts) != 1:
                        st.error(
                            "Unable to log in with those details. "
                            "Check your credentials or contact "
                            "the Academy Manager."
                        )

                    else:
                        account = matching_accounts[0]

                        if (
                            str(account.get("account_status", ""))
                            .strip()
                            .casefold() != "active"
                        ):
                            st.error(
                                "This account is not active. "
                                "Please contact the Academy Manager."
                            )

                        elif verify_password(
                            password,
                            str(account.get("password_hash", "")),
                        ):
                            st.session_state[
                                "student_authenticated"
                            ] = True

                            st.session_state["student_id"] = str(
                                account["student_id"]
                            ).strip()

                            st.session_state["student_email"] = email

                            st.success("Login successful!")
                            st.rerun()

                        else:
                            st.error(
                                "Unable to log in with those "
                                "details. Check your credentials "
                                "or contact the Academy Manager."
                            )

            except Exception as exc:
                st.error(
                    "Login is temporarily unavailable. "
                    "Please try again later."
                )

                print(f"SAES login error: {exc}")