import streamlit as st
import pandas as pd

from utils.data import load_events, load_logs

events = load_events()
logs = load_logs()

st.title("📊 Event Intelligence View")

event_id = st.selectbox(
    "Select Event",
    events["event_id"].tolist()
)

# Get event metadata
event_info = events[events["event_id"] == event_id].iloc[0]

st.subheader(f"📅 {event_info['event_name']} ({event_info['type']})")

# Filter logs
event_logs = logs[logs["event_id"] == event_id]

# Handle empty event safely
if event_logs.empty:
    st.warning("No attendance records yet for this event")
    st.stop()

# KPIs
total_students = len(event_logs)

attendance_rate = event_logs["attended"].mean()
participation_rate = event_logs["participated"].mean()

# Display metrics
col1, col2, col3 = st.columns(3)

col1.metric("Total Attendance", total_students)
col2.metric("Attendance Rate", f"{attendance_rate:.0%}")
col3.metric("Participation Rate", f"{participation_rate:.0%}")

# Event score
event_score = (attendance_rate * 0.6) + (participation_rate * 0.4)

st.metric("Event Engagement Score", round(event_score, 2))

st.divider()

# Student list
st.subheader("👥 Student Participation List")

st.dataframe(
    event_logs[[
        "student_id",
        "attended",
        "participated",
        "submitted",
        #"created_at"
    ]]
)