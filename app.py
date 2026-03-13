import streamlit as st
import upstox_client
import threading
import time

# --- 1. GLOBAL STORE & STATE ---
# We use a global dict because background threads can't access st.session_state directly
if "live_data" not in st.session_state:
    st.session_state.live_data = {"price": 0.0, "time": "Connecting...", "symbol": ""}

# Global object to hold the current tick
SHARED_TICK = {"price": 0.0, "time": "Waiting...", "error": None}

# --- 2. SECRETS CHECK ---
if "UPSTOX_ACCESS_TOKEN" not in st.secrets:
    st.error("Missing 'UPSTOX_ACCESS_TOKEN' in Streamlit Secrets!")
    st.stop()

# Upstox Configuration
conf = upstox_client.Configuration()
conf.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
api_client = upstox_client.ApiClient(conf)

# --- 3. UI SETUP ---
st.set_page_config(page_title="Upstox Live Spot", layout="centered")
st.title("🎯 Live Index Spot Price")

INDEX_MAP = {
    "Nifty 50": "NSE_INDEX|Nifty 50",
    "Bank Nifty": "NSE_INDEX|Nifty Bank",
    "FinNifty": "NSE_INDEX|Nifty Fin Service",
    "SENSEX": "BSE_INDEX|SENSEX"
}

selected_label = st.selectbox("Select Index to Monitor", list(INDEX_MAP.keys()))
selected_key = INDEX_MAP[selected_label]

# --- 4. WEBSOCKET HANDLERS ---
def on_message(message):
    """Update global dict when a new tick arrives."""
    if "feeds" in message and selected_key in message["feeds"]:
        feed = message["feeds"][selected_key]
        if "ltpc" in feed:
            SHARED_TICK["price"] = feed["ltpc"]["ltp"]
            SHARED_TICK["time"] = time.strftime("%H:%M:%S")

def run_v3_streamer():
    """Background thread for WebSocket."""
    try:
        streamer = upstox_client.MarketDataStreamerV3(api_client)
        streamer.on("message", on_message)
        streamer.connect()
        # Initial subscription
        streamer.subscribe([selected_key], "ltpc")
        
        # Keep thread alive and handle index changes
        current_subscribed = selected_key
        while True:
            if current_subscribed != selected_key:
                # Unsubscribe old, subscribe new
                streamer.unsubscribe([current_subscribed])
                streamer.subscribe([selected_key], "ltpc")
                current_subscribed = selected_key
            time.sleep(1)
    except Exception as e:
        SHARED_TICK["error"] = str(e)

# Start WebSocket thread once
if "ws_started" not in st.session_state:
    threading.Thread(target=run_v3_streamer, daemon=True).start()
    st.session_state.ws_started = True

# --- 5. DISPLAY LOGIC ---
# Sync shared data to session state
st.session_state.live_data.update(SHARED_TICK)

if st.session_state.live_data["error"]:
    st.error(f"Error: {st.session_state.live_data['error']}")

# Display Big Metric
price = st.session_state.live_data["price"]
st.metric(
    label=f"Live Spot: {selected_label}", 
    value=f"₹{price:,.2f}" if price > 0 else "Fetching..."
)

st.caption(f"Last update at: {st.session_state.live_data['time']}")

# Manual Refresh button for safety
if st.button("Refresh Connection"):
    st.rerun()

# Auto-refresh UI every 1 second
time.sleep(1)
st.rerun()
