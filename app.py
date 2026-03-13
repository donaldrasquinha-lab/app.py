import streamlit as st
import upstox_client
import threading
import time

# --- 1. INITIALIZE SESSION STATE ---
if "live_price" not in st.session_state:
    st.session_state.live_price = 0.0
    st.session_state.last_update = "Connecting..."

# Global dictionary to bridge the background thread and the UI
# Threads in Streamlit cannot access st.session_state directly
SHARED_DATA = {"price": 0.0, "time": "Waiting..."}

# --- 2. AUTHENTICATION & CONNECTION ---
# This part connects to your token from the secrets
def get_api_client():
    try:
        access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
        configuration = upstox_client.Configuration()
        configuration.access_token = access_token
        return upstox_client.ApiClient(configuration)
    except Exception as e:
        st.error(f"Authentication Failed: Check your Token in Secrets. Error: {e}")
        st.stop()

api_client = get_api_client()

# --- 3. UI LAYOUT ---
st.set_page_config(page_title="Upstox Live Spot", page_icon="📈")
st.title("🎯 Upstox Live Index Tracker")

INDEX_MAP = {
    "Nifty 50": "NSE_INDEX|Nifty 50",
    "Bank Nifty": "NSE_INDEX|Nifty Bank",
    "FinNifty": "NSE_INDEX|Nifty Fin Service",
    "SENSEX": "BSE_INDEX|SENSEX"
}

selected_label = st.selectbox("Select Index", list(INDEX_MAP.keys()))
selected_key = INDEX_MAP[selected_label]

# --- 4. WEBSOCKET HANDLER ---
def on_message(message):
    """Callback function when a new price tick arrives from Upstox."""
    if "feeds" in message and selected_key in message["feeds"]:
        tick = message["feeds"][selected_key]
        if "ltpc" in tick:
            SHARED_DATA["price"] = tick["ltpc"]["ltp"]
            SHARED_DATA["time"] = time.strftime("%H:%M:%S")

def start_websocket_thread():
    """Runs the Upstox Streamer in the background."""
    try:
        # MarketDataStreamerV3 is the official way to get live data
        streamer = upstox_client.MarketDataStreamerV3(api_client)
        streamer.on("message", on_message)
        streamer.connect()
        streamer.subscribe([selected_key], "ltpc")
        
        # Keep tracking if the user changes the dropdown index
        last_subscribed = selected_key
        while True:
            if last_subscribed != selected_key:
                streamer.unsubscribe([last_subscribed])
                streamer.subscribe([selected_key], "ltpc")
                last_subscribed = selected_key
            time.sleep(0.5)
    except Exception as e:
        print(f"WebSocket Error: {e}")

# Start the background thread once per session
if "ws_started" not in st.session_state:
    threading.Thread(target=start_websocket_thread, daemon=True).start()
    st.session_state.ws_started = True

# --- 5. DATA SYNC & DISPLAY ---
# Pull data from the global SHARED_DATA into Streamlit's UI state
st.session_state.live_price = SHARED_DATA["price"]
st.session_state.last_update = SHARED_DATA["time"]

# Display the Big Metric
price_display = f"₹{st.session_state.live_price:,.2f}" if st.session_state.live_price > 0 else "Fetching..."
st.metric(label=f"Live {selected_label} Spot", value=price_display)
st.caption(f"Last updated at: {st.session_state.last_update}")

# Auto-refresh the UI every 1 second to show the moving price
time.sleep(1)
st.rerun()
