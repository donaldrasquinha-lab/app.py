import streamlit as st
import upstox_client
import threading
import time
import pandas as pd

# --- 1. ACCESS SECRETS FROM TOML ---
# st.secrets automatically reads from .streamlit/secrets.toml
if "UPSTOX_ACCESS_TOKEN" not in st.secrets:
    st.error("❌ Token not found! Ensure .streamlit/secrets.toml is configured.")
    st.stop()

ACCESS_TOKEN = st.secrets["UPSTOX_ACCESS_TOKEN"]

# --- 2. GLOBAL DATA STORE ---
# Shared dictionary to pass data from background thread to UI
SHARED_DATA = {"ltp": 0.0, "time": "Waiting...", "error": None}

# --- 3. UI SETUP ---
st.set_page_config(page_title="Upstox TOML Dashboard", layout="wide")
st.title("📈 Upstox Live Feed (Connected via TOML)")

INDEX_MAP = {
    "Nifty 50": "NSE_INDEX|Nifty 50",
    "Bank Nifty": "NSE_INDEX|Nifty Bank",
    "FinNifty": "NSE_INDEX|Nifty Fin Service",
    "SENSEX": "BSE_INDEX|SENSEX"
}
index_name = st.sidebar.selectbox("Select Index", list(INDEX_MAP.keys()))
index_key = INDEX_MAP[index_name]

# --- 4. WEBSOCKET LOGIC (V3) ---
def on_message(message):
    """Decodes live ticks from the Upstox V3 stream."""
    if "feeds" in message and index_key in message["feeds"]:
        feed = message["feeds"][index_key]
        if "ltpc" in feed:
            SHARED_DATA["ltp"] = feed["ltpc"]["ltp"]
            SHARED_DATA["time"] = time.strftime("%H:%M:%S")

def start_v3_streamer():
    """Initializes connection using credentials from TOML."""
    try:
        conf = upstox_client.Configuration()
        conf.access_token = ACCESS_TOKEN
        api_client = upstox_client.ApiClient(conf)
        
        # StreamerV3 handles binary Protobuf decoding automatically
        streamer = upstox_client.MarketDataStreamerV3(api_client)
        streamer.on("message", on_message)
        streamer.connect()
        streamer.subscribe([index_key], "ltpc")
        
        # Monitor for dropdown changes
        current_key = index_key
        while True:
            if current_key != index_key:
                streamer.unsubscribe([current_key])
                streamer.subscribe([index_key], "ltpc")
                current_key = index_key
            time.sleep(1)
    except Exception as e:
        SHARED_DATA["error"] = f"Connection Failed: {e}"

# Start background thread once
if "ws_active" not in st.session_state:
    threading.Thread(target=start_v3_streamer, daemon=True).start()
    st.session_state.ws_active = True

# --- 5. DISPLAY ---
if SHARED_DATA["error"]:
    st.error(SHARED_DATA["error"])

ltp = SHARED_DATA["ltp"]
col1, col2 = st.columns(2)

with col1:
    st.metric(label=f"Live {index_name} Spot", value=f"₹{ltp:,.2f}" if ltp > 0 else "Fetching...")
    st.caption(f"Last update: {SHARED_DATA['time']}")

with col2:
    if ltp > 0:
        st.subheader("10-Strike Option Chain")
        interval = 100 if "Bank" in index_name or "SENSEX" in index_name else 50
        atm = round(ltp / interval) * interval
        strikes = [atm + (i * interval) for i in range(-5, 5)]
        st.table(pd.DataFrame([{"Strike": s, "Moneyness": "ITM" if s < ltp else "OTM"} for s in strikes]))

time.sleep(1)
st.rerun()
