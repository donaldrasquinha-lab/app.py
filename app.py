import streamlit as st
import upstox_client
import threading
import time
import pandas as pd

# --- 1. GLOBAL DATA BRIDGE ---
# Threads cannot safely write to st.session_state directly.
# We use a global dictionary to hold the latest tick data.
SHARED_DATA = {"ltp": 0.0, "time": "Waiting...", "error": None}

# --- 2. SECRETS & AUTHENTICATION ---
if "UPSTOX_ACCESS_TOKEN" not in st.secrets:
    st.error("❌ 'UPSTOX_ACCESS_TOKEN' missing in Streamlit Secrets!")
    st.stop()

def get_api_client():
    conf = upstox_client.Configuration()
    conf.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
    return upstox_client.ApiClient(conf)

# --- 3. UI LAYOUT ---
st.set_page_config(page_title="Upstox V3 Live", layout="wide")
st.title("🚀 Upstox Market Data V3 Live Feed")

INDEX_MAP = {
    "Nifty 50": "NSE_INDEX|Nifty 50",
    "Bank Nifty": "NSE_INDEX|Nifty Bank",
    "FinNifty": "NSE_INDEX|Nifty Fin Service",
    "SENSEX": "BSE_INDEX|SENSEX"
}

index_name = st.sidebar.selectbox("Select Index", list(INDEX_MAP.keys()))
index_key = INDEX_MAP[index_name]

# --- 4. WEBSOCKET LOGIC (ALIGNED WITH V3 DOCS) ---
def on_message(message):
    """Callback for V3 Protobuf decoded messages."""
    try:
        # V3 Feed structure: message['feeds'][key]['ltpc']['ltp']
        if "feeds" in message and index_key in message["feeds"]:
            feed = message["feeds"][index_key]
            if "ltpc" in feed:
                SHARED_DATA["ltp"] = feed["ltpc"]["ltp"]
                SHARED_DATA["time"] = time.strftime("%H:%M:%S")
    except Exception as e:
        SHARED_DATA["error"] = f"Processing Error: {e}"

def run_v3_streamer():
    """Background task to maintain V3 WebSocket connection."""
    try:
        api_client = get_api_client()
        # MarketDataStreamerV3 handles binary protocol & redirection automatically
        streamer = upstox_client.MarketDataStreamerV3(api_client)
        streamer.on("message", on_message)
        streamer.connect()
        
        # 'ltpc' mode = LTP, LTT, LTQ, and Close Price
        streamer.subscribe([index_key], "ltpc")
        
        # Keep thread alive and handle dropdown changes
        current_key = index_key
        while True:
            if current_key != index_key:
                streamer.unsubscribe([current_key])
                streamer.subscribe([index_key], "ltpc")
                current_key = index_key
            time.sleep(1)
    except Exception as e:
        SHARED_DATA["error"] = f"V3 Connection Failed: {e}"

# Start the background thread once per app session
if "ws_active" not in st.session_state:
    threading.Thread(target=run_v3_streamer, daemon=True).start()
    st.session_state.ws_active = True

# --- 5. DATA DISPLAY & REFRESH ---
# Sync global thread data to local session display
if SHARED_DATA["error"]:
    st.error(SHARED_DATA["error"])

ltp = SHARED_DATA["ltp"]

col1, col2 = st.columns([1, 2])

with col1:
    st.metric(
        label=f"Live {index_name} Spot", 
        value=f"₹{ltp:,.2f}" if ltp > 0 else "Fetching..."
    )
    st.caption(f"Last Tick Received: {SHARED_DATA['time']}")

with col2:
    if ltp > 0:
        st.subheader("Simulated 10-Strike Option Chain")
        # Interval logic: Nifty/Fin=50, Bank/Sensex=100
        interval = 100 if "Bank" in index_name or "SENSEX" in index_name else 50
        atm = round(ltp / interval) * interval
        
        # Generate 5 ITM and 5 OTM strikes
        strikes = [atm + (i * interval) for i in range(-5, 5)]
        df = pd.DataFrame([
            {"Strike": s, "Position": "ITM" if s < ltp else "OTM"} 
            for s in strikes
        ])
        st.table(df)
    else:
        st.info("🕒 Waiting for data... Ensure it's market hours (9:15 AM - 3:30 PM IST).")

# Force UI to rerun every 1 second to show live updates
time.sleep(1)
st.rerun()
