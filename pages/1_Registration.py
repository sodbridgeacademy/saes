import streamlit as st
import pandas as pd
import uuid

from utils.sheets import get_sheets
from utils.data import load_students, load_events, load_logs

sheets = get_sheets()

students_sheet = sheets["students"]
# students = pd.DataFrame(students_sheet.get_all_records())


students = load_students()
events = load_events()
logs = load_logs()


def generate_student_id(df, prefix):

    if df.empty:
        return f"{prefix}-001"

    existing = df[df["student_id"].str.startswith(prefix)]

    if existing.empty:
        return f"{prefix}-001"

    last_num = (
        existing["student_id"]
        .str.split("-")
        .str[-1]
        .astype(int)
        .max()
    )

    return f"{prefix}-{str(last_num + 1).zfill(3)}"


st.title("🧾 Student Registration")

with st.form("register"):

    name = st.text_input("Full Name")
    email = st.text_input("Email")

    school = st.selectbox("School", ["DAT", "DEV", "DSN", "CYB"])

    submit = st.form_submit_button("Register")


if submit:

    if email in students["email_address"].values:
        st.error("Already registered")
        st.stop()

    student_id = generate_student_id(students, school)

    students_sheet.append_row([
        student_id,
        name,
        email,
        school,
        4,
        str(pd.Timestamp.now())
    ])

    st.success(f"Registered! Your ID: {student_id}")