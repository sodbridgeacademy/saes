import streamlit as st
import pandas as pd

from utils.data import load_students, load_logs
from utils.auth import require_student_login

st.set_page_config(
    page_title="Student Profile",
    page_icon="👤",
    layout="wide",
)

# Authenticate before loading or displaying private records.
student_id = str(require_student_login()).strip()

st.title("👤 Student Profile")
st.caption(
    "Review your learner activity, attendance and engagement."
)

students = load_students()
logs = load_logs()

# Validate the student data structure.
student_columns = {
    "student_id", "name", "school", "cohort"
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
    st.error(
        "The student sheet is missing required columns."
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

if not logs.empty:
    if not log_columns.issubset(logs.columns):
        st.error(
            "The logs sheet is missing required columns."
        )
        st.stop()

    logs = logs.copy()

    logs["student_id"] = (
        logs["student_id"]
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

st.subheader(str(student["name"]))

col1, col2, col3 = st.columns(3)

col1.metric("Student ID", student["student_id"])
col2.metric("School", student["school"])
col3.metric("Cohort", student["cohort"])

# Filter activity strictly to the authenticated student.
if logs.empty:
    st.info(
        "Your profile is registered, but no activity "
        "records have been recorded yet."
    )
    st.stop()

student_logs = logs[
    logs["student_id"].str.casefold()
    == student_id.casefold()
].copy()

if student_logs.empty:
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

if valid_sessions.empty:
    st.warning(
        "Attendance and participation data is not available "
        "for calculating engagement metrics."
    )
    st.stop()

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

# Core metrics.
st.divider()
st.subheader("📊 Core Metrics")

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

# Activity breakdown.
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
    use_container_width=True,
    hide_index=True,
)

# Engagement trend.
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
    trend["engagement_score"] = (
        pd.to_numeric(
            trend["attended"],
            errors="coerce",
        ) * 0.6
        + pd.to_numeric(
            trend["participated"],
            errors="coerce",
        ) * 0.4
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
