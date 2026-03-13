import streamlit as st
import upstox_client
import threading
import time
import urllib.parse

# --- 1. CONFIGURATION ---
# Replace with your actual credentials from Developer Console
CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
REDIRECT_URI = "http://localhost:8501" # Must match Developer Console

# --- 2. SESSION STATE INITIALIZATION ---
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "live_data" not in st.session_state:
    st.session_state.live_data = {"ltp": 0.0, "time": "Waiting..."}

# --- 3. LOGIN PAGE LOGIC ---
def login_page():
    st.title("🔐 Upstox Secure Login")
    st.write("Click below to authenticate with your Upstox account.")
    
    # Official Upstox Login URL
    auth_url = f"https://api.upstox.com{CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code"
    
    st.link_button("Login with Upstox", auth_url)
    
    # Check if we were just redirected back with a code
    query_params = st.query_params
    if "code" in query_params:
        auth_code = query_params["code"]
        st.info("🔄 Exchanging authorization code for access token...")
        generate_token(auth_code)

def generate_token(code):
    """Exchanges auth code for a valid access token."""
    try:
        api_instance = upstox_client.LoginApi()
        api_response = api_instance.token(
            api_version='2.0',
            code=code,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            grant_type='authorization_code'
        )
        st.session_state.access_token = api_response.access_token
        st.success("✅ Login Successful!")
        st.rerun()
    except Exception as e:
        st.error(f"❌ Token Generation Failed: {e}")

# --- 4. LIVE DATA LOGIC ---
def on_message(message):
    """Callback for MarketDataStreamerV3."""
    if "feeds" in message:
        # Example for Nifty 50
        feed = message["feeds"].get("NSE_INDEX|Nifty 50")
        if feed and "ltpc" in feed:
            st.session_state.live_data["ltp"] = feed["ltpc"]["ltp"]
            st.session_state.live_data["time"] = time.strftime("%H:%M:%S")

def start_streamer():
    """Background thread to handle V3 WebSocket connection."""
    try:
        conf = upstox_client.Configuration()
        conf.access_token = st.session_state.access_token
        
        # V3 Streamer handles binary Protobuf decoding automatically
        streamer = upstox_client.MarketDataStreamerV3(
            upstox_client.ApiClient(conf)
        )
        streamer.on("message", on_message)
        streamer.connect()
        streamer.subscribe(["NSE_INDEX|Nifty 50"], "ltpc")
        
        while True: time.sleep(1)
    except Exception as e:
        print(f"Streamer Error: {e}")

# --- 5. MAIN DASHBOARD ---
if not st.session_state.access_token:
    login_page()
else:
    st.title("📈 Real-Time Dashboard")
    st.write(f"Logged in with token: `{st.session_state.access_token[:10]}...`")
    
    # Start WebSocket thread once
    if "ws_active" not in st.session_state:
        threading.Thread(target=start_streamer, daemon=True).start()
        st.session_state.ws_active = True

    # Display Metrics
    st.metric(label="Nifty 50 Spot", value=f"₹{st.session_state.live_data['ltp']:,.2f}")
    st.caption(f"Last updated: {st.session_state.live_data['time']}")
    
    if st.button("Logout"):
        st.session_state.access_token = None
        st.query_params.clear()
        st.rerun()

    time.sleep(1)
    st.rerun()
