import streamlit as st
import upstox_client
import threading
import time
import pandas as pd

# --- 1. INITIALIZE SESSION STATE & GLOBAL STORE ---
# We use a simple global dict for the background thread to avoid "Missing Script Context" errors
if "data_store" not in st.session_state:
    st.session_state.data_store = {"ltp": 0.0, "time": "Connecting...", "error": None}

# This global variable is accessible by the background thread
LIVE_TICK = {"ltp": 0.0, "time": "Connecting...", "error": None}

# --- 2. FAILSAFE SECRETS CHECK ---
if "UPSTOX_ACCESS_TOKEN" not in st.secrets:
    st.error("❌ Secret Key 'UPSTOX_ACCESS_TOKEN' Not Found in Settings!")
    st.stop()

ACCESS_TOKEN = st.secrets["UPSTOX_ACCESS_TOKEN"]
configuration = upstox_client.Configuration()
configuration.access_token = ACCESS_TOKEN
api_client = upstox_client.ApiClient(configuration)

# --- 3. UI SETUP ---
st.set_page_config(page_title="Upstox Live Feed", layout="wide")
st.title("📈 Upstox Real-Time Dashboard")

INDEX_MAP = {
    "Nifty 50": "NSE_INDEX|Nifty 50",
    "Bank Nifty": "NSE_INDEX|Nifty Bank",
    "FinNifty": "NSE_INDEX|Nifty Fin Service",
    "SENSEX": "BSE_INDEX|SENSEX"
}
index_display = st.sidebar.selectbox("Select Index", list(INDEX_MAP.keys()))
index_key = INDEX_MAP[index_display]

# --- 4. WEBSOCKET LOGIC ---
def on_message(message):
    try:
        if "feeds" in message and index_key in message["feeds"]:
            data = message["feeds"][index_key]
            if "ltpc" in data:
                LIVE_TICK["ltp"] = data["ltpc"]["ltp"]
                LIVE_TICK["time"] = time.strftime("%H:%M:%S")
    except Exception as e:
        LIVE_TICK["error"] = str(e)

def start_upstox_stream():
    try:
        streamer = upstox_client.MarketDataStreamerV3(api_client)
        streamer.on("message", on_message)
        streamer.connect()
        streamer.subscribe([index_key], "ltpc")
    except Exception as e:
        LIVE_TICK["error"] = f"Connection Failed: {e}"

# Start thread only once
if "ws_active" not in st.session_state:
    t = threading.Thread(target=start_upstox_stream, daemon=True)
    t.start()
    st.session_state.ws_active = True

# --- 5. SYNC GLOBAL DATA TO SESSION STATE ---
st.session_state.data_store.update(LIVE_TICK)

# --- 6. DISPLAY ---
if st.session_state.data_store["error"]:
    st.error(f"⚠️ {st.session_state.data_store['error']}")
    st.info("Check if your token is expired or if you have too many tabs open.")

ltp = st.session_state.data_store["ltp"]
col1, col2 = st.columns(2)

with col1:
    st.metric(label=f"{index_display} Spot", value=f"₹{ltp:,.2f}")
    st.caption(f"Last updated: {st.session_state.data_store['time']}")

with col2:
    if ltp > 0:
        interval = 100 if "Bank" in index_display or "SENSEX" in index_display else 50
        atm = round(ltp / interval) * interval
        strikes = [atm + (i * interval) for i in range(-5, 5)]
        df = pd.DataFrame([{"Strike": s, "Pos": "ITM" if s < ltp else "OTM"} for s in strikes])
        st.table(df)
    else:
        st.warning("Waiting for data... Ensure market is open (9:15 AM - 3:30 PM).")

time.sleep(1)
st.rerun()
