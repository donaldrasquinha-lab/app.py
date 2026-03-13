import streamlit as st
import upstox_client
import threading
import time
import pandas as pd

# --- CONFIGURATION ---
ACCESS_TOKEN = st.secrets["UPSTOX_ACCESS_TOKEN"]
configuration = upstox_client.Configuration()
configuration.access_token = ACCESS_TOKEN
api_client = upstox_client.ApiClient(configuration)

# --- UI SETUP ---
st.set_page_config(page_title="Upstox Live Feed", layout="wide")
st.title("📈 Real-Time Index & Option Chain")

# Index mapping with correct instrument keys
INDEX_MAP = {
    "Nifty 50": "NSE_INDEX|Nifty 50",
    "Bank Nifty": "NSE_INDEX|Nifty Bank",
    "FinNifty": "NSE_INDEX|Nifty Fin Service",
    "SENSEX": "BSE_INDEX|SENSEX"
}

index_name = st.sidebar.selectbox("Select Index", list(INDEX_MAP.keys()))
index_key = INDEX_MAP[index_name]

# Initialize session state for live data
if "live_feed" not in st.session_state:
    st.session_state.live_feed = {"ltp": 0.0, "last_updated": "Waiting..."}

# --- WEBSOCKET LOGIC ---
def on_message(message):
    """Callback triggered on every tick."""
    if "feeds" in message:
        feed_data = message["feeds"].get(index_key)
        if feed_data and "ltpc" in feed_data:
            st.session_state.live_feed["ltp"] = feed_data["ltpc"]["ltp"]
            st.session_state.live_feed["last_updated"] = time.strftime("%H:%M:%S")

def run_streamer():
    """Background thread to handle WebSocket connection."""
    streamer = upstox_client.MarketDataStreamerV3(api_client)
    streamer.on("message", on_message)
    streamer.connect()
    streamer.subscribe([index_key], "ltpc") # LTPC mode for basic live price

# Start WebSocket thread if not already running
if "ws_started" not in st.session_state:
    threading.Thread(target=run_streamer, daemon=True).start()
    st.session_state.ws_started = True

# --- DISPLAY ---
spot = st.session_state.live_feed["ltp"]
st.metric(label=f"Live Spot: {index_name}", value=f"₹{spot:,.2f}", delta_color="normal")
st.caption(f"Last updated: {st.session_state.live_feed['last_updated']}")

if spot > 0:
    st.subheader("Simulated 10-Strike Option Chain")
    
    # Determine strike interval based on index
    interval = 100 if "Bank" in index_name or "SENSEX" in index_name else 50
    atm_strike = round(spot / interval) * interval
    
    # Generate 5 ITM and 5 OTM strikes
    strikes = [atm_strike + (i * interval) for i in range(-5, 5)]
    
    chain_data = []
    for s in strikes:
        chain_data.append({
            "Strike": s,
            "Type": "CE/PE",
            "Moneyness": "ITM" if (s < spot) else "OTM",
            "Status": "ATM" if s == atm_strike else "Active"
        })
    
    st.table(pd.DataFrame(chain_data))

# Auto-refresh UI
time.sleep(1)
st.rerun()
