
import streamlit as st
import pandas as pd

from utils.data import load_events, load_logs

st.set_page_config(
    page_title="Event Intelligence",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Event Intelligence")
st.caption(
    "Analyse event attendance, participation "
    "and engagement across Sodbridge Academy."
)

# Load data
events = load_events()
logs = load_logs()

# Validate event data
if events.empty or "event_id" not in events.columns:
    st.info(
        "No events are available yet, or the events "
        "sheet is missing the event_id column."
    )
    st.stop()

# Select event
event_options = events["event_id"].dropna().tolist()

if not event_options:
    st.info("No valid events are available.")
    st.stop()

event_id = st.selectbox(
    "Select Event",
    event_options,
    format_func=str
)

event_info = events[
    events["event_id"] == event_id
].iloc[0]

event_name = event_info.get("event_name", "Unnamed Event")
event_type = event_info.get("type", "Not specified")

st.subheader(f"📅 {event_name}")
st.caption(f"Event ID: {event_id} · Type: {event_type}")

# Validate log data
required_columns = {
    "event_id",
    "student_id",
    "attended",
    "participated",
    "submitted"
}

missing_columns = required_columns - set(logs.columns)

if missing_columns:
    st.error(
        "The logs sheet is missing required columns: "
        + ", ".join(sorted(missing_columns))
    )
    st.stop()

# Filter event logs
event_logs = logs[
    logs["event_id"].astype(str) == str(event_id)
].copy()

if event_logs.empty:
    st.warning(
        "No attendance records have been recorded "
        "for this event yet."
    )
    st.stop()

# Convert relevant fields to numeric values.
# Invalid/missing values are excluded from rate calculations.
for column in ["attended", "participated", "submitted"]:
    event_logs[column] = pd.to_numeric(
        event_logs[column], errors="coerce"
    )

# Use one record per student for event-level metrics.
# This avoids duplicate records inflating counts.
unique_logs = event_logs.drop_duplicates(
    subset=["student_id"],
    keep="last"
).copy()

attended = unique_logs["attended"].eq(1)
participated = unique_logs["participated"].eq(1)
submitted = unique_logs["submitted"].eq(1)

total_records = len(event_logs)
unique_students = unique_logs["student_id"].nunique()
total_attended = int(attended.sum())
total_participated = int(participated.sum())
total_submitted = int(submitted.sum())

attendance_rate = (
    unique_logs["attended"].eq(1).mean()
    if unique_logs["attended"].notna().any()
    else None
)

participation_rate = (
    unique_logs["participated"].eq(1).mean()
    if unique_logs["participated"].notna().any()
    else None
)

submission_rate = (
    unique_logs["submitted"].eq(1).mean()
    if unique_logs["submitted"].notna().any()
    else None
)

# Preserve the original 60/40 score.
# Only calculate it when both rates are available.
if attendance_rate is not None and participation_rate is not None:
    engagement_score = (
        attendance_rate * 0.6
        + participation_rate * 0.4
    )
else:
    engagement_score = None

# Key metrics
st.subheader("Event Performance")

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Unique Students",
    unique_students
)

col2.metric(
    "Attended",
    total_attended,
    help="Unique students recorded as attended."
)

col3.metric(
    "Participated",
    total_participated,
    help="Unique students recorded as participating."
)

col4.metric(
    "Submitted",
    total_submitted,
    help="Unique students recorded as submitting."
)

col1, col2, col3 = st.columns(3)

col1.metric(
    "Attendance Rate",
    f"{attendance_rate:.0%}"
    if attendance_rate is not None else "N/A"
)

col2.metric(
    "Participation Rate",
    f"{participation_rate:.0%}"
    if participation_rate is not None else "N/A"
)

col3.metric(
    "Submission Rate",
    f"{submission_rate:.0%}"
    if submission_rate is not None else "N/A"
)

if engagement_score is not None:
    st.metric(
        "Event Engagement Score",
        f"{engagement_score:.0%}",
        help=(
            "Weighted indicator: 60% attendance rate "
            "+ 40% participation rate. This is an "
            "operational indicator, not a validated "
            "measure of event quality."
        )
    )
else:
    st.info(
        "The engagement score is unavailable because "
        "attendance or participation data is missing."
    )

st.divider()

# Student participation table
st.subheader("👥 Student Participation Records")

display_columns = [
    "student_id",
    "attended",
    "participated",
    "submitted"
]

student_view = unique_logs[display_columns].copy()

student_view = student_view.rename(columns={
    "student_id": "Student ID",
    "attended": "Attended",
    "participated": "Participated",
    "submitted": "Submitted"
})

for column in ["Attended", "Participated", "Submitted"]:
    student_view[column] = student_view[column].map({
        1: "Yes",
        0: "No"
    }).fillna("Not recorded")

st.dataframe(
    student_view,
    use_container_width=True,
    hide_index=True
)

# Data-quality information
with st.expander("Data quality and calculation notes"):
    st.write(
        f"Raw log records for this event: {total_records}"
    )
    st.write(
        f"Unique students in the records: {unique_students}"
    )

    if total_records > unique_students:
        st.warning(
            "Duplicate student records exist for this event. "
            "The summary uses the last record per student, "
            "but you should investigate the duplicates."
        )

    st.caption(
        "Rates use the unique student records currently "
        "available in the logs sheet. They are not rates "
        "among all enrolled learners unless every eligible "
        "learner has a corresponding event record."
    )
