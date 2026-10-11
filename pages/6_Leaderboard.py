
import streamlit as st
import pandas as pd

from utils.data import load_students, load_logs

st.set_page_config(
    page_title="SAES Leaderboard",
    page_icon="🏆",
    layout="wide"
)

st.title("🏆 SAES Global Leaderboard")
st.caption(
    "Learner rankings based on recorded attendance "
    "and participation."
)

students = load_students()
logs = load_logs()

# Validate data
if students.empty:
    st.info("No student records are available yet.")
    st.stop()

if logs.empty:
    st.info("No activity records are available yet.")
    st.stop()

required_student_columns = {
    "student_id", "name", "school", "cohort"
}
required_log_columns = {
    "student_id", "attended", "participated"
}

missing_students = (
    required_student_columns - set(students.columns)
)
missing_logs = required_log_columns - set(logs.columns)

if missing_students:
    st.error(
        "Student sheet missing columns: "
        + ", ".join(sorted(missing_students))
    )
    st.stop()

if missing_logs:
    st.error(
        "Logs sheet missing columns: "
        + ", ".join(sorted(missing_logs))
    )
    st.stop()

# Normalise join keys
students = students.copy()
logs = logs.copy()

students["student_id"] = (
    students["student_id"].fillna("").astype(str).str.strip()
)
logs["student_id"] = (
    logs["student_id"].fillna("").astype(str).str.strip()
)

# Convert activity values to numeric
for column in ["attended", "participated"]:
    logs[column] = pd.to_numeric(
        logs[column], errors="coerce"
    ).fillna(0)

# Aggregate activity per student
activity = logs.groupby("student_id").agg(
    attended=("attended", "sum"),
    participated=("participated", "sum"),
    activity_records=("student_id", "size")
).reset_index()

activity["score"] = (
    activity["attended"] + activity["participated"]
)

# Attach student profile data
student_details = students[
    ["student_id", "name", "school", "cohort"]
].drop_duplicates(subset=["student_id"])

leaderboard = activity.merge(
    student_details,
    on="student_id",
    how="inner"
)

if leaderboard.empty:
    st.warning(
        "No activity records could be matched to student profiles."
    )
    st.stop()

# Filters
col1, col2 = st.columns(2)

school_options = sorted(
    leaderboard["school"].dropna().astype(str).unique()
)

selected_school = col1.selectbox(
    "Filter by school",
    ["All Schools"] + school_options
)

cohort_options = sorted(
    leaderboard["cohort"].dropna().astype(str).unique()
)

selected_cohort = col2.selectbox(
    "Filter by cohort",
    ["All Cohorts"] + cohort_options
)

filtered = leaderboard.copy()

if selected_school != "All Schools":
    filtered = filtered[
        filtered["school"].astype(str) == selected_school
    ]

if selected_cohort != "All Cohorts":
    filtered = filtered[
        filtered["cohort"].astype(str) == selected_cohort
    ]

if filtered.empty:
    st.info("No learners match these filters.")
    st.stop()

# Rank by score, with attendance as a tie-breaker.
filtered = filtered.sort_values(
    ["score", "attended", "participated"],
    ascending=[False, False, False]
).reset_index(drop=True)

filtered["rank"] = range(1, len(filtered) + 1)

# Summary metrics
metric1, metric2, metric3 = st.columns(3)

metric1.metric("Ranked Learners", len(filtered))
metric2.metric("Highest Score", int(filtered["score"].max()))
metric3.metric(
    "Total Activity Records",
    int(filtered["activity_records"].sum())
)

st.subheader("🥇 Top 10 Learners")

top_ten = filtered.head(10)

st.dataframe(
    top_ten[
        ["rank", "name", "student_id", "school",
         "cohort", "attended", "participated", "score"]
    ],
    use_container_width=True,
    hide_index=True
)

st.subheader("📋 Full Leaderboard")

st.dataframe(
    filtered[
        ["rank", "name", "student_id", "school",
         "cohort", "attended", "participated", "score"]
    ],
    use_container_width=True,
    hide_index=True
)

st.caption(
    "Score = total recorded attendance + total recorded "
    "participation. This is an activity score, not the "
    "official Certified merit assessment."
)
