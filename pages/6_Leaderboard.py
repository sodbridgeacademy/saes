import streamlit as st
import pandas as pd

from utils.data import load_students, load_logs

students = load_students()
logs = load_logs()

st.title("🏆 Global Leaderboard")

leaderboard = logs.groupby("student_id").agg({
    "attended": "sum",
    "participated": "sum"
}).reset_index()

leaderboard["score"] = leaderboard["attended"] + leaderboard["participated"]

leaderboard = leaderboard.sort_values("score", ascending=False)

leaderboard["rank"] = range(1, len(leaderboard) + 1)

st.subheader("Top Students")

st.dataframe(leaderboard.head(10))