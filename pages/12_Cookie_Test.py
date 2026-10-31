
import streamlit as st
import extra_streamlit_components as stx
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="SAES Cookie Test")

st.title("SAES Persistent Cookie Test")

cookie_manager = stx.CookieManager(key="saes_cookie_test_manager")

COOKIE_NAME = "saes_test_cookie"

if st.button("Create 24-hour test cookie"):
    expiry = datetime.now(timezone.utc) + timedelta(hours=24)

    cookie_manager.set(
        cookie=COOKIE_NAME,
        val="SAES_COOKIE_TEST_SUCCESS",
        expires_at=expiry,
        path="/",
        secure=True,
        same_site="strict",
        key="saes_test_cookie_set",
    )

    st.success("Test cookie creation requested. Refresh this page to verify.")

st.divider()

cookie_value = cookie_manager.get(COOKIE_NAME)

if cookie_value:
    st.success("Cookie successfully retrieved!")
    st.write("Cookie value:", cookie_value)
else:
    st.warning("No test cookie detected yet. Create one or refresh the page.")

if st.button("Delete test cookie"):
    cookie_manager.delete(
        COOKIE_NAME,
        key="saes_test_cookie_delete",
    )
    st.info("Test cookie deletion requested. Refresh to confirm.")
