import streamlit as st
import upstox_client
import threading
import time
import pandas as pd

# --- 1. FAILSAFE SECRETS CHECK ---
# This prevents the "KeyError" crash and shows you instructions instead.
if "UPSTOX_ACCESS_TOKEN" not in st.secrets:
    st.error("❌ **Secret Key 'UPSTOX_ACCESS_TOKEN' Not Found!**")
    st.markdown("""
    **How to fix this:**
    1. Go to your [Streamlit Cloud Dashboard](https://share.streamlit.io).
    2. Click the **three dots (⋮)** next to your app -> **Settings** -> **Secrets**.
    3. Paste the following line (replace with your actual token):
       `UPSTOX_ACCESS_TOKEN = "your_long_extended_token_here"`
    4. Click **Save**.
    """)
    st.stop()

# --- 2. INITIALIZATION ---
ACCESS_TOKEN = st.secrets["UPSTOX_ACCESS_TOKEN"]
configuration = upstox_client.Configuration()
configuration.access_token = ACCESS_TOKEN
api_client = upstox_client.ApiClient(configuration)

# --- 3. UI SETUP ---
st.set_page_config(page_title="Upstox Live Dashboard", layout="wide")
st.title("📈 Upstox Real-Time Index Feed")

INDEX_MAP = {
    "Nifty 50": "NSE_INDEX|Nifty 50",
    "Bank Nifty": "NSE_INDEX|Nifty Bank",
    "FinNifty": "NSE_INDEX|Nifty Fin Service",
    "SENSEX": "BSE_INDEX|SENSEX"
}

index_display_name = st.sidebar.selectbox("Select Index", list(INDEX_MAP.keys()))
index_key = INDEX_MAP[index_display_name]

# Global storage for live data across app reruns
if "live_feed" not in st.session_state:
    st.session_state.live_feed = {"ltp": 0.0, "time": "Connecting...", "error": None}

# --- 4. WEBSOCKET LOGIC (Upstox V3) ---
def on_message(message):
    """Handles incoming market data ticks."""
    try:
        if "feeds" in message and index_key in message["feeds"]:
            data = message["feeds"][index_key]
            if "ltpc" in data:
                st.session_state.live_feed["ltp"] = data["ltpc"]["ltp"]
                st.session_state.live_feed["time"] = time.strftime("%H:%M:%S")
    except Exception as e:
        st.session_state.live_feed["error"] = str(e)

def start_upstox_stream():
    """Initializes the background WebSocket streamer."""
    try:
        # MarketDataStreamerV3 handles binary/protobuf decoding automatically
        streamer = upstox_client.MarketDataStreamerV3(api_client)
        streamer.on("message", on_message)
        streamer.connect()
        streamer.subscribe([index_key], "ltpc")
    except Exception as e:
        st.session_state.live_feed["error"] = f"Streamer Error: {e}"

# Start thread if not already active
if "thread_active" not in st.session_state:
    threading.Thread(target=start_upstox_stream, daemon=True).start()
    st.session_state.thread_active = True

# --- 5. DATA DISPLAY ---
if st.session_state.live_feed["error"]:
    st.error(f"Connection Error: {st.session_state.live_feed['error']}")

ltp = st.session_state.live_feed["ltp"]
col1, col2 = st.columns([1, 2])

with col1:
    st.metric(label=f"{index_display_name} Spot", value=f"₹{ltp:,.2f}")
    st.caption(f"Last updated: {st.session_state.live_feed['time']}")

with col2:
    if ltp > 0:
        st.subheader("Simulated 10-Strike Option Chain")
        # Interval: Nifty/Fin=50, Bank/Sensex=100
        interval = 100 if "Bank" in index_display_name or "SENSEX" in index_display_name else 50
        atm_strike = round(ltp / interval) * interval
        
        # Build 10-strike list (5 ITM, 5 OTM)
        strikes = [atm_strike + (i * interval) for i in range(-5, 5)]
        df = pd.DataFrame([
            {"Strike Price": s, "Type": "CE/PE", "Moneyness": "ITM" if s < ltp else "OTM"} 
            for s in strikes
        ])
        st.table(df)
    else:
        st.info("🕒 Waiting for market data... (Market must be open: 9:15 AM - 3:30 PM IST)")

# Auto-refresh UI every 1 second
time.sleep(1)
st.rerun()
