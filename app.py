import streamlit as st
import upstox_client
import threading
import time
import pandas as pd

# --- 1. SAFE SECRETS LOADING ---
# This block prevents the KeyError and tells you exactly what to do.
if "UPSTOX_ACCESS_TOKEN" not in st.secrets:
    st.error("❌ **Secret Key Missing!**")
    st.info("""
    Please follow these steps:
    1. Go to your **Streamlit Cloud Dashboard**.
    2. Click **Manage App** -> **Settings** -> **Secrets**.
    3. Paste your credentials exactly like this:
    ```toml
    UPSTOX_ACCESS_TOKEN = "your_extended_token_here"
    ```
    4. Click **Save** and the app will restart.
    """)
    st.stop()

# Load credentials from Streamlit Secrets
ACCESS_TOKEN = st.secrets["UPSTOX_ACCESS_TOKEN"]

# Initialize Upstox API Client
configuration = upstox_client.Configuration()
configuration.access_token = ACCESS_TOKEN
api_client = upstox_client.ApiClient(configuration)

# --- 2. UI SETUP ---
st.set_page_config(page_title="Upstox Live Feed", layout="wide")
st.title("📈 Upstox Real-Time Index & Options")

# Index mapping with correct instrument keys
INDEX_MAP = {
    "Nifty 50": "NSE_INDEX|Nifty 50",
    "Bank Nifty": "NSE_INDEX|Nifty Bank",
    "FinNifty": "NSE_INDEX|Nifty Fin Service",
    "SENSEX": "BSE_INDEX|SENSEX"
}

index_display_name = st.sidebar.selectbox("Select Index", list(INDEX_MAP.keys()))
index_key = INDEX_MAP[index_display_name]

# Persistent storage for live data across reruns
if "data_store" not in st.session_state:
    st.session_state.data_store = {"ltp": 0.0, "time": "Connecting..."}

# --- 3. WEBSOCKET LOGIC ---
def on_message(message):
    """Callback for tick data from WebSocket V3."""
    # V3 returns data in a 'feeds' dictionary
    if "feeds" in message and index_key in message["feeds"]:
        feed = message["feeds"][index_key]
        if "ltpc" in feed:
            st.session_state.data_store["ltp"] = feed["ltpc"]["ltp"]
            st.session_state.data_store["time"] = time.strftime("%H:%M:%S")

def start_stream():
    """Initializes and runs the Upstox MarketDataStreamerV3."""
    try:
        streamer = upstox_client.MarketDataStreamerV3(api_client)
        streamer.on("message", on_message)
        streamer.connect()
        streamer.subscribe([index_key], "ltpc")
    except Exception as e:
        print(f"WebSocket Error: {e}")

# Start the background thread once per session
if "thread_active" not in st.session_state:
    threading.Thread(target=start_stream, daemon=True).start()
    st.session_state.thread_active = True

# --- 4. DATA DISPLAY ---
spot = st.session_state.data_store["ltp"]
col1, col2 = st.columns([1, 2])

with col1:
    st.metric(label=f"Current {index_display_name} Spot", value=f"₹{spot:,.2f}")
    st.caption(f"Last updated: {st.session_state.data_store['time']}")

with col2:
    if spot > 0:
        st.subheader("Live Option Chain (Approximate Strikes)")
        
        # Determine strike interval (50 for Nifty/FinNifty, 100 for Bank/SENSEX)
        interval = 100 if "Bank" in index_display_name or "SENSEX" in index_display_name else 50
        atm_strike = round(spot / interval) * interval
        
        # Build 10-strike list (5 ITM and 5 OTM)
        strikes = [atm_strike + (i * interval) for i in range(-5, 5)]
        chain_list = []
        for s in strikes:
            chain_list.append({
                "Strike Price": s,
                "Moneyness": "ITM" if (s < spot) else "OTM",
                "Distance": f"{abs(s - spot):.2f} pts"
            })
        
        st.table(pd.DataFrame(chain_list))
    else:
        st.warning("Waiting for data from Upstox... Ensure your token is valid and the market is open.")

# Auto-refresh UI every 1 second
time.sleep(1)
st.rerun()

