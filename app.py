import streamlit as st
import urllib.parse

# Construct the login URL using your secrets
client_id = st.secrets["UPSTOX_CLIENT_ID"]
redirect_uri = st.secrets["UPSTOX_REDIRECT_URI"]

# The URL you visit to log in
login_url = (
    f"https://api.upstox.com/v2/login/authorization/dialog?"
    f"client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_uri)}"
)

st.link_button("Login to Upstox", login_url)




import streamlit as st
import pandas as pd
import upstox_client
@@ -113,3 +131,4 @@ def fetch_upstox_data():
st.info("Click 'Refresh' to fetch live Nifty strikes.")

st.caption("Powered by Upstox API V3")
