import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import streamlit as st
import uuid


# Connect Sheets Func
@st.cache_resource
def connect_sheets():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_file(
        "service_account.json",
        scopes=scope
    )

    client = gspread.authorize(creds)
    return client

# Connect to your SAES Google Sheets
@st.cache_resource
def get_sheet():
    return client.open_by_key("1YT7TAFGOgD5GQll8c4KNUQEsc8kWGfBMVl7chyvVngo")

client = connect_sheets()

@st.cache_resource
def load_worksheets():
    sheet = get_sheet()
    return {
        "students": sheet.worksheet("students"),
        "events": sheet.worksheet("events"),
        "logs": sheet.worksheet("engagement_logs")
    }

# students_sheet = sheet.worksheet("students")
# logs_sheet = sheet.worksheet("engagement_logs")
# events_sheet = sheet.worksheet("events")

# Logs
logs = pd.DataFrame(logs_sheet.get_all_records())

# Students
students = pd.DataFrame(students_sheet.get_all_records())

# Events
events = pd.DataFrame(events_sheet.get_all_records())
#events.columns = events.columns.str.strip().str.lower()

# EVENT DROPDOWN (NOW SAFE TO BUILD)

# enforce schema safety
expected_cols = ["student_id", "name", "email_address", "school", "cohort", "created_at"]

for col in expected_cols:
    if col not in students.columns:
        students[col] = ""



# BASIC LEADERBOARD (EARLY MOTIVATION SYSTEM)
st.subheader("🏆 Top Students (Engagement)")

summary = logs.groupby("student_id").agg({
    "attended": "sum",
    "participated": "sum"
}).reset_index()

summary["score"] = summary["attended"] + summary["participated"]

top = summary.sort_values("score", ascending=False).head(10)

st.dataframe(top)


# EVENT HEALTH VIEW (FOR YOU / STAFF)
st.subheader("📅 Event Engagement Overview")

event_summary = logs.groupby("event_id").agg({
    "attended": "sum",
    "participated": "sum"
}).reset_index()

st.dataframe(event_summary)



# SIMPLE AUTO EVENT ID GENERATOR
# def generate_event_id(df, prefix):

#     if df.empty:
#         return f"{prefix}-001"

#     existing = df[df["event_id"].str.startswith(prefix)]

#     if existing.empty:
#         return f"{prefix}-001"

#     last_num = (
#         existing["event_id"]
#         .str.split("-")
#         .str[-1]
#         .astype(int)
#         .max()
#     )

#     return f"{prefix}-{str(last_num + 1).zfill(3)}"


# HOW EVENTS ARE CREATED IN SAES
def generate_event_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

st.subheader("📅 Create Event")

event_name = st.text_input("Event Name")

event_type = st.selectbox(
    "Type",
    ["DAT", "DEV", "DSN", "CYB", "TCD", "CHKIN"]
)

date = st.date_input("Date")

create = st.button("Create Event")


if create:

    school = event_type
    if event_type in ["TCD", "CHKIN"]:
        school = "ALL"

    event_id = generate_event_id(event_type)

    new_event = [
        event_id,
        event_name,
        event_type,
        str(date),
        school
    ]

    events_sheet.append_row(new_event)

    st.success(f"Event created: {event_id}")


# ID Generation Logic
def generate_student_id(df, school_prefix):

    if df.empty:
        return f"{school_prefix}-001"

    existing = df[df["student_id"].str.startswith(school_prefix)]

    if existing.empty:
        return f"{school_prefix}-001"

    last_num = (
        existing["student_id"]
        .str.split("-")
        .str[-1]
        .astype(int)
        .max()
    )

    return f"{school_prefix}-{str(last_num + 1).zfill(3)}"

# Add Student Registration Form (NEW)
st.subheader("🧾 Student Self Registration")
with st.form("register_student"):

    name = st.text_input("Full Nname")
    email = st.text_input("Email Address")

    school = st.selectbox(
        "School",
        ["DAT", "DEV", "DSN", "CYB"]
    )

    submit = st.form_submit_button("Submit")

    # Save + Generate ID
    if submit:

        # simple validation
        if not name or not email:
            st.error("Please fill all fields")
            st.stop()
        
        if email in students["email_address"].values:
            st.error("You are already registered")
            st.stop()
        
        else:

            student_id = generate_student_id(students, school)

            new_row = [
                student_id,
                name,
                email,
                school,
                4,
                str(pd.Timestamp.now())
            ]

            students_sheet.append_row(new_row)

            st.success(f"Registration successful! Your Student ID is {student_id}.)")
            st.info("Save this ID. You will use it for all classes, Check-in sessions, and TCD sessions.")
            st.write("Next step: Join your next class or event and check in using SAES.")


            # DATA INTEGRITY LAYER
            # A. Prevent duplicate check-ins
            existing = logs[
                (logs["student_id"] == student_id) &
                (logs["event_id"] == event_code)
            ]

            if not existing.empty:
                st.error("You already checked in for this event")
                st.stop()

            # B. Validate event exists
            if event_code not in events["event_id"].values:
                st.error("Invalid event code")
                st.stop()

            # C. Validate student exists
            if student_id not in students["student_id"].values:
                st.error("Invalid student ID")
                st.stop()



# Create Student Lookup UI
st.subheader("📊 Student Progress Dashboard")

student_id_input = st.text_input("Enter your Student ID (e.g. DAT-001)")

# Filter their records
student_logs = logs[logs["student_id"] == student_id_input]

# Safety check
if student_id_input:

    student_logs = logs[logs["student_id"] == student_id_input]

    if student_logs.empty:
        st.warning("No records found for this Student ID")
    else:

        attendance_count = student_logs["attended"].sum()
        participation_count = student_logs["participated"].sum()
        total_sessions = len(student_logs)

        # prevent division by zero
        attendance_rate = attendance_count / total_sessions if total_sessions > 0 else 0
        participation_rate = participation_count / total_sessions if total_sessions > 0 else 0

        engagement_score = (attendance_rate * 0.6) + (participation_rate * 0.4)

        st.metric("Total Sessions", total_sessions)
        st.metric("Attendance Rate", f"{attendance_rate:.0%}")
        st.metric("Participation Rate", f"{participation_rate:.0%}")
        st.metric("Engagement Score", f"{engagement_score:.2f}")



# Update check-in system (IMPORTANT)
# student_id = st.selectbox(
#     "Select Student ID",
#     students["student_id"]
# )

# Load worksheets as DataFrames
students_sheet = sheet.worksheet("students")
events_sheet = sheet.worksheet("events")
logs_sheet = sheet.worksheet("engagement_logs")

students = pd.DataFrame(students_sheet.get_all_records())
events = pd.DataFrame(events_sheet.get_all_records())
logs = pd.DataFrame(logs_sheet.get_all_records())


st.set_page_config(page_title="SAES Dashboard", layout="wide")

st.title("📊 SAES - Sodbridge Academy Engagement System")

# Load data
students = pd.read_csv("students.csv")
events = pd.read_csv("events.csv")
logs = pd.read_csv("engagement_logs.csv")

# Merge datasets
df = logs.merge(students, on="student_id", how="left")
df = df.merge(events, on="event_id", how="left")

# Engagement score
df["engagement_score"] = (
    df["attended"] * 0.3 +
    df["participated"] * 0.4 +
    df["submitted"] * 0.3
) * 100

# Sidebar Filters
st.sidebar.header("🔍 Filters")

school_filter = st.sidebar.multiselect(
    "Select School",
    options=df["school"].unique(),
    default=df["school"].unique()
)

event_type_filter = st.sidebar.multiselect(
    "Select Event Type",
    options=df["type"].unique(),
    default=df["type"].unique()
)

student_filter = st.sidebar.multiselect(
    "Select Students",
    options=df["name"].unique(),
    default=df["name"].unique()
)

# Add Student Selector
st.sidebar.header("👤 Student View")

selected_student = st.sidebar.selectbox(
    "Select a student",
    options=df["name"].unique()
)

# Filter for Selected Student
student_df = df[df["name"] == selected_student]

# Student KPI Card
st.subheader(f"📊 Profile: {selected_student}")

col1, col2, col3 = st.columns(3)

col1.metric("Avg Engagement", round(student_df["engagement_score"].mean(), 2))
col2.metric("Attendance Rate", round(student_df["attended"].mean() * 100, 2))
col3.metric("Participation Rate", round(student_df["participated"].mean() * 100, 2))

# Student Activity Tiemeline
st.subheader("📅 Activity Breakdown")

st.dataframe(
    student_df[[
        "event_name",
        "type",
        "attended",
        "participated",
        "submitted",
        "engagement_score"
    ]]
)

# Simple Performance Trend
st.subheader("📈 Engagement Trend")

st.line_chart(student_df["engagement_score"])

# Apply filters to dataset
df = df[
    (df["school"].isin(school_filter)) &
    (df["type"].isin(event_type_filter)) &
    (df["name"].isin(student_filter))
]

# Risk Score
student_summary = df.groupby("student_id").agg({
    "engagement_score": "mean",
    "attended": "mean"
}).reset_index()

def risk_level(row):
    if row["engagement_score"] >= 75:
        return "🟢 Safe"
    elif row["engagement_score"] >= 50:
        return "🟡 At Risk"
    else:
        return "🔴 Drop Risk"

student_summary["risk"] = student_summary.apply(risk_level, axis=1)

# Show Risk Score
st.subheader("⚠️ Student Risk Analysis")

st.dataframe(student_summary.sort_values("engagement_score"))

# What's Happening This Week?
st.subheader("📊 Weekly Insights")

# Overall Academy Performance
avg_engagement = df["engagement_score"].mean()
attendance_rate = df["attended"].mean() * 100
participation_rate = df["participated"].mean() * 100

col1, col2, col3 = st.columns(3)

col1.metric("Avg Engagement", round(avg_engagement, 2))
col2.metric("Attendance Rate", f"{attendance_rate:.1f}%")
col3.metric("Participation Rate", f"{participation_rate:.1f}%")

# School Performance Comparison (KEY INSIGHT)
st.subheader("🏫 School Performance")

school_perf = df.groupby("school").agg({
    "engagement_score": "mean",
    "attended": "mean",
    "participated": "mean"
}).reset_index()

school_perf["attended"] = school_perf["attended"] * 100
school_perf["participated"] = school_perf["participated"] * 100

st.dataframe(school_perf)

# Top Performers This Week
st.subheader("🏆 Top Performers")

top_students = df.groupby("name").agg({
    "engagement_score": "mean"
}).reset_index()

top_students = top_students.sort_values("engagement_score", ascending=False).head(5)

st.dataframe(top_students)

# At Risk Students
st.subheader("⚠️ At-Risk Students")

risk_students = student_summary[student_summary["risk"] != "🟢 Safe"]

st.dataframe(risk_students)

# UI: Attendance Form
st.subheader("✍️ Mark Attendance (Admin Panel)")

student_names = students["name"].tolist()
event_names = events["event_name"].tolist()

# Student Attendance Form
with st.form("attendance_form"):
    student = st.selectbox("Student", student_names)
    event = st.selectbox("Event", event_names)

    attended = st.checkbox("Attended")
    participated = st.checkbox("Participated")
    submitted = st.checkbox("Submitted")

    submit = st.form_submit_button("Save Attendance")

# WRITE BACK LOGIC to Sheets
if submit:
    # get IDs
    student_id = students[students["name"] == student]["student_id"].values[0]
    event_id = events[events["event_name"] == event]["event_id"].values[0]

    new_row = [
        student_id,
        event_id,
        int(attended),
        int(participated),
        int(submitted)
    ]

    logs_sheet.append_row(new_row)

    st.success("Attendance recorded successfully!")


# Checkin System
st.title("🎓 SAES Student Check-in")
st.write("Enter your details to confirm attendance for this session.")


# Student Check-in Form
with st.form("student_checkin"):
    
    student_id = st.text_input("Enter Student ID")
    event_code = st.selectbox("Select Event", events["event_id"].tolist())

    participation = st.radio(
        "Did you actively participate?",
        ["Yes", "No"]
    )

    submitted = st.form_submit_button("Check In")


if submitted:

    # validate student
    student_match = students[students["student_id"] == student_id]

    # validate event
    event_match = events[events["event_id"] == event_code]

    if student_match.empty:
        st.error("Invalid Student ID")
        st.stop()

    if event_match.empty:
        st.error("Invalid Event Code")
        st.stop()

    # prevent duplicates
    existing = logs[
        (logs["student_id"] == student_id) &
        (logs["event_id"] == event_code)
    ]

    if not existing.empty:
        st.error("Already checked in for this event")
        st.stop()

    # write log
    new_row = [
        student_id,
        event_code,
        1,
        1 if participation == "Yes" else 0,
        str(pd.Timestamp.now())
    ]

    logs_sheet.append_row(new_row)

    st.success("Check-in successful!")


# ---------------- DASHBOARD ---------------- #

col1, col2, col3, col4 = st.columns(4)

col1.metric("Students", len(students))
col2.metric("Events", len(events))
col3.metric("Logs", len(logs))
col4.metric("Avg Score", round(df["engagement_score"].mean(), 2))

st.divider()

# ---------------- LEADERBOARD ---------------- #

st.subheader("🏆 Leaderboard")

leaderboard = df.groupby(["student_id", "name"]).agg({
    "engagement_score": "mean"
}).reset_index()

leaderboard = leaderboard.sort_values("engagement_score", ascending=False)

st.dataframe(leaderboard, use_container_width=True)

st.divider()

# ---------------- SCHOOL BREAKDOWN ---------------- #

st.subheader("📚 School Performance")

school_scores = df.groupby("school").agg({
    "engagement_score": "mean"
}).reset_index()

st.dataframe(school_scores, use_container_width=True)

st.divider()

# ---------------- RAW DATA ---------------- #

with st.expander("📄 View Raw Data"):
    st.dataframe(df)