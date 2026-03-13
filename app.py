import streamlit as st
from nsepython import *
import pandas as pd
import time

# --- UI SETUP ---
st.set_page_config(page_title="NSE Live Dashboard", layout="wide")
st.title("🇮🇳 NSE India Live Market Data")

# Index selection
index_map = {
    "Nifty 50": "NIFTY 50",
    "Bank Nifty": "NIFTY BANK",
    "FinNifty": "NIFTY FIN SERVICE"
}
selected_index = st.sidebar.selectbox("Select Index", list(index_map.keys()))

# --- DATA FETCHING ---
def get_live_data():
    try:
        # Fetching index quote
        index_data = nse_get_index_quote(index_map[selected_index])
        return index_data
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return None

# Display data
data = get_live_data()

if data:
    # Display Key Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Last Price", f"₹{data['last']}")
    col2.metric("Change", f"{data['variation']} ({data['percentChange']}%)")
    col3.metric("Open", f"₹{data['open']}")

    # Simulated Option Chain / Strike Prices
    st.subheader(f"Strikes around {selected_index}")
    spot = float(data['last'])
    interval = 100 if "Bank" in selected_index else 50
    atm = round(spot / interval) * interval
    
    strikes = [atm + (i * interval) for i in range(-5, 6)]
    strike_df = pd.DataFrame({
        "Strike Price": strikes,
        "Moneyness": ["ITM" if s < spot else "OTM" for s in strikes]
    })
    st.table(strike_df)

# Auto-refresh UI every 30 seconds (NSE limits frequent requests)
time.sleep(30)
st.rerun()
