import streamlit as st
import pandas as pd

from utils.data import load_students, load_logs

students = load_students()
logs = load_logs()

st.title("👤 Student Profile")

student_id = st.text_input("Enter your Student ID")

if student_id:

    student_logs = logs[logs["student_id"] == student_id]
    st.write(student_logs)

    if student_logs.empty:
        st.warning("No records found")
        st.stop()

    # ======================
    # CORE METRICS
    # ======================
    total_sessions = len(student_logs)
    attendance = student_logs["attended"].sum()
    participation = student_logs["participated"].sum()

    attendance_rate = attendance / total_sessions if total_sessions else 0
    participation_rate = participation / total_sessions if total_sessions else 0

    engagement_score = (attendance_rate * 0.6) + (participation_rate * 0.4)

    col1, col2, col3 = st.columns(3)

    col1.metric("Total Sessions", total_sessions)
    col2.metric("Attendance Rate", f"{attendance_rate:.0%}")
    col3.metric("Participation Rate", f"{participation_rate:.0%}")

    st.metric("Engagement Score", round(engagement_score, 2))

    # ======================
    # ACTIVITY BREAKDOWN
    # ======================
    st.subheader("📅 My Activity Breakdown")

    st.dataframe(
        student_logs[[
            "event_id",
            "attended",
            "participated",
            "submitted",
            "created_at"
        ]]
    )

    # ======================
    # TREND (KEEP THIS)
    # ======================
    st.subheader("📈 Engagement Trend")

    student_logs["engagement_score"] = (
        student_logs["attended"] * 0.6 +
        student_logs["participated"] * 0.4
    )

    st.line_chart(student_logs["engagement_score"])

    # ======================
    # RISK LEVEL (SIMPLIFIED)
    # ======================
    avg_score = engagement_score

    if avg_score >= 0.75:
        risk = "🟢 Safe"
    elif avg_score >= 0.5:
        risk = "🟡 At Risk"
    else:
        risk = "🔴 Drop Risk"

    st.subheader("⚠️ Status")
    st.write(risk)

