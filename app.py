import streamlit as st
import upstox_client
import threading
import time
import pandas as pd

# --- INITIALIZATION ---
# Use the official snake_case formatting required by the V3 SDK
if "live_data" not in st.session_state:
    st.session_state.live_data = {"ltp": 0.0, "time": "Waiting...", "error": None}

# Global dictionary for background thread updates
SHARED_TICK = {"ltp": 0.0, "time": "Waiting...", "error": None}

# --- FAILSAFE SECRETS CHECK ---
if "UPSTOX_ACCESS_TOKEN" not in st.secrets:
    st.error("❌ 'UPSTOX_ACCESS_TOKEN' not found in Streamlit Secrets.")
    st.stop()

# Initialize API Client
conf = upstox_client.Configuration()
conf.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
api_client = upstox_client.ApiClient(conf)

# --- UI SETUP ---
st.set_page_config(page_title="Upstox V3 Live", layout="wide")
st.title("📈 Upstox Market Data Feed V3")

INDEX_MAP = {
    "Nifty 50": "NSE_INDEX|Nifty 50",
    "Bank Nifty": "NSE_INDEX|Nifty Bank",
    "FinNifty": "NSE_INDEX|Nifty Fin Service",
    "SENSEX": "BSE_INDEX|SENSEX"
}
index_display = st.sidebar.selectbox("Select Index", list(INDEX_MAP.keys()))
index_key = INDEX_MAP[index_display]

# --- WEBSOCKET HANDLERS (V3 SPECIFIC) ---
def on_message(message):
    """Processes live_feed type messages from V3 Streamer."""
    # V3 feeds are structured as: message['feeds'][instrument_key]['ltpc']['ltp']
    if "feeds" in message and index_key in message["feeds"]:
        data = message["feeds"][index_key]
        if "ltpc" in data:
            SHARED_TICK["ltp"] = data["ltpc"]["ltp"]
            SHARED_TICK["time"] = time.strftime("%H:%M:%S")

def start_v3_streamer():
    """Connects to V3 Market Data Feed with automatic redirection."""
    try:
        # MarketDataStreamerV3 is the documented interface for effortless connection
        streamer = upstox_client.MarketDataStreamerV3(api_client)
        streamer.on("message", on_message)
        streamer.connect()
        # Subscription mode 'ltpc' provides LTP, LTT, LTQ, and Close Price
        streamer.subscribe([index_key], "ltpc")
        
        # Handle index changes dynamically
        last_key = index_key
        while True:
            if last_key != index_key:
                streamer.unsubscribe([last_key])
                streamer.subscribe([index_key], "ltpc")
                last_key = index_key
            time.sleep(1)
    except Exception as e:
        SHARED_TICK["error"] = f"V3 Connection Error: {e}"

# Start background thread once
if "ws_active" not in st.session_state:
    threading.Thread(target=start_v3_streamer, daemon=True).start()
    st.session_state.ws_active = True

# --- SYNC & DISPLAY ---
st.session_state.live_data.update(SHARED_TICK)

if st.session_state.live_data["error"]:
    st.error(st.session_state.live_data["error"])

ltp = st.session_state.live_data["ltp"]
col1, col2 = st.columns(2)

with col1:
    st.metric(label=f"{index_display} Spot (LTP)", value=f"₹{ltp:,.2f}" if ltp > 0 else "Fetching...")
    st.caption(f"Last Tick: {st.session_state.live_data['time']}")

with col2:
    if ltp > 0:
        st.subheader("Dynamic 10-Strike Option Chain")
        interval = 100 if "Bank" in index_display or "SENSEX" in index_display else 50
        atm = round(ltp / interval) * interval
        strikes = [atm + (i * interval) for i in range(-5, 5)]
        st.table(pd.DataFrame([{"Strike": s, "Type": "CE/PE", "Moneyness": "ITM" if s < ltp else "OTM"} for s in strikes]))
    else:
        st.info("🕒 Waiting for first tick... (Market hours: 9:15 AM - 3:30 PM IST)")

# Auto-refresh UI
time.sleep(1)
st.rerun()
