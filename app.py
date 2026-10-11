
import streamlit as st

st.set_page_config(
    page_title="SAES | Sodbridge Academy Engagement System",
    page_icon="📊",
    layout="wide",
)

st.title("📊 SAES")
st.subheader("Sodbridge Academy Engagement System")

st.write(
    """
    Welcome to the Sodbridge Academy Engagement System (SAES).

    SAES supports student registration, event participation,
    engagement tracking, and programme analytics across
    Sodbridge Academy's schools.
    """
)

st.divider()

st.header("Navigate SAES")

st.markdown(
    """
    Use the sidebar to access the available sections.
    """
)

col1, col2 = st.columns(2)

with col1:
    st.subheader("🎓 Student Services")
    st.markdown(
        """
        - **Registration:** Register as a new student.
        - **Login:** Sign in to your student account.
        - **Student Profile:** View your personal profile
          and engagement activity.
        - **Check-in:** Access event check-in.
        """
    )

with col2:
    st.subheader("📈 Academy Operations")
    st.markdown(
        """
        - **Event Intelligence:** Review event insights.
        - **Leaderboard:** View engagement rankings.
        - **Analytics:** Explore student and event data.
        - **Create Event:** Set up Academy events.
        - **Admin Panel:** Access administrative functions.
        """
    )

st.divider()

st.caption(
    "SAES | Sodbridge Academy | Student Engagement and "
    "Programme Intelligence"
)
