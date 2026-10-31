
import streamlit as st
import pandas as pd

from utils.data import load_students, load_logs
from utils.auth import require_student_login, logout_user

st.set_page_config(
    page_title="Student Profile",
    page_icon="👤",
    layout="wide",
)

# Authenticate before loading or displaying private records.
student_id = str(require_student_login()).strip()

st.title("👤 Student Profile")
st.caption(
    "Review your learner information, programme, "
    "attendance and engagement."
)

students = load_students()
logs = load_logs()

# Validate the student data structure.
student_columns = {
    "student_id",
    "name",
    "school",
    "cohort",
    "status",
    "programme_type",
}

log_columns = {
    "student_id",
    "event_id",
    "attended",
    "participated",
    "submitted",
    "created_at",
}

if not student_columns.issubset(students.columns):
    missing_columns = student_columns - set(students.columns)

    st.error(
        "The student sheet is missing required columns: "
        + ", ".join(sorted(missing_columns))
    )
    st.stop()

# Normalise IDs for matching.
students = students.copy()

students["student_id"] = (
    students["student_id"]
    .fillna("")
    .astype(str)
    .str.strip()
)

# Find the profile using the authenticated account's ID.
matches = students[
    students["student_id"].str.casefold()
    == student_id.casefold()
]

if len(matches) != 1:
    st.error(
        "Your student profile could not be verified. "
        "Please contact the Academy Manager."
    )
    st.stop()

student = matches.iloc[0]

# Format profile fields for display.
student_name = str(student["name"]).strip()
student_name = (
    student_name
    if student_name and student_name.lower() != "nan"
    else "Student"
)

def display_value(value, default="Not recorded"):
    """Return a readable value for a profile field."""
    if pd.isna(value):
        return default

    value = str(value).strip()

    if not value or value.casefold() in {"nan", "none", "nat"}:
        return default

    return value


def format_label(value, default="Not recorded"):
    """Convert values such as 'professional' to 'Professional'."""
    value = display_value(value, default)

    if value == default:
        return value

    return value.replace("_", " ").title()


student_status = format_label(student["status"])
programme_type = format_label(
    student["programme_type"],
    default="Not recorded",
)

school = display_value(student["school"])
cohort = display_value(student["cohort"])

st.subheader(f"Welcome, {student_name}")

# Student information.
st.divider()
st.subheader("👤 My Information")

col1, col2, col3 = st.columns(3)

col1.metric("Student ID", display_value(student["student_id"]))
col2.metric("School", school)
col3.metric("Cohort", cohort)

col4, col5 = st.columns(2)

col4.metric("Student Status", student_status)
col5.metric("Programme Type", programme_type)


# Account Logout section
st.divider()
st.subheader("Account")

if st.button(
    "🚪 Logout",
    key="student_logout",
    use_container_width=True,
):
    logout_user()
    st.switch_page("pages/0_Login.py")


# Load and validate activity data.
if logs.empty:
    st.divider()
    st.info(
        "Your profile is registered, but no activity "
        "records have been recorded yet."
    )
    st.stop()

if not log_columns.issubset(logs.columns):
    missing_columns = log_columns - set(logs.columns)

    st.error(
        "The logs sheet is missing required columns: "
        + ", ".join(sorted(missing_columns))
    )
    st.stop()

logs = logs.copy()

logs["student_id"] = (
    logs["student_id"]
    .fillna("")
    .astype(str)
    .str.strip()
)

# Filter activity strictly to the authenticated student.
student_logs = logs[
    logs["student_id"].str.casefold()
    == student_id.casefold()
].copy()

if student_logs.empty:
    st.divider()
    st.info(
        "Your profile is registered, but no activity "
        "records have been recorded yet."
    )
    st.stop()

# Convert metric fields safely.
for column in ["attended", "participated", "submitted"]:
    student_logs[column] = pd.to_numeric(
        student_logs[column],
        errors="coerce",
    )

# Use records with known attendance and participation values.
valid_sessions = student_logs.dropna(
    subset=["attended", "participated"]
).copy()

# Core metrics.
st.divider()
st.subheader("📊 Core Metrics")

if valid_sessions.empty:
    st.warning(
        "Attendance and participation data is not available "
        "for calculating engagement metrics."
    )
else:
    total_sessions = len(valid_sessions)

    attendance_count = int(
        valid_sessions["attended"].eq(1).sum()
    )

    participation_count = int(
        valid_sessions["participated"].eq(1).sum()
    )

    attendance_rate = (
        valid_sessions["attended"].eq(1).mean()
    )

    participation_rate = (
        valid_sessions["participated"].eq(1).mean()
    )

    engagement_score = (
        attendance_rate * 0.6
        + participation_rate * 0.4
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Recorded Sessions",
        total_sessions,
    )

    col2.metric(
        "Attendance Rate",
        f"{attendance_rate:.0%}",
        help="Share of recorded sessions marked as attended.",
    )

    col3.metric(
        "Participation Rate",
        f"{participation_rate:.0%}",
        help="Share of recorded sessions marked as participated.",
    )

    st.metric(
        "Engagement Score",
        f"{engagement_score:.0%}",
        help=(
            "Calculated as 60% attendance rate "
            "plus 40% participation rate."
        ),
    )

    # Engagement status.
    st.subheader("📌 Engagement Status")

    if engagement_score >= 0.75:
        st.success("High recorded engagement")
    elif engagement_score >= 0.50:
        st.warning("Moderate recorded engagement")
    else:
        st.error("Low recorded engagement")

    st.caption(
        "This status summarises recorded attendance and "
        "participation only. It is not a prediction of "
        "academic performance or learner dropout."
    )

# Activity breakdown.
st.divider()
st.subheader("📅 My Activity Breakdown")

display_columns = [
    "event_id",
    "attended",
    "participated",
    "submitted",
    "created_at",
]

activity = student_logs[display_columns].copy()

for column in ["attended", "participated", "submitted"]:
    activity[column] = activity[column].map({
        1: "Yes",
        0: "No",
    }).fillna("Not recorded")

st.dataframe(
    activity,
    width="stretch",
    hide_index=True
)

# Engagement trend.
st.divider()
st.subheader("📈 Engagement Trend")

trend = student_logs.copy()

trend["created_at"] = pd.to_datetime(
    trend["created_at"],
    errors="coerce",
)

trend = trend.dropna(
    subset=["created_at"]
).sort_values("created_at")

if not trend.empty:
    trend["attended"] = pd.to_numeric(
        trend["attended"],
        errors="coerce",
    )

    trend["participated"] = pd.to_numeric(
        trend["participated"],
        errors="coerce",
    )

    trend["engagement_score"] = (
        trend["attended"] * 0.6
        + trend["participated"] * 0.4
    )

    trend = trend.dropna(
        subset=["engagement_score"]
    )

    if not trend.empty:
        chart_data = trend.set_index("created_at")[
            ["engagement_score"]
        ]

        st.line_chart(chart_data)
    else:
        st.info(
            "There is not enough valid data to plot a trend."
        )
else:
    st.info(
        "No valid activity timestamps are available."
    )
