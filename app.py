import streamlit as st
from nselib import market_data
import pandas as pd
import time

# --- Page Config ---
st.set_page_config(page_title="NSE Live Tracker", layout="wide")
st.title("🇮🇳 NSE Live Index Dashboard")

# --- Sidebar Selection ---
index_map = {
    "Nifty 50": "NIFTY 50",
    "Bank Nifty": "NIFTY BANK",
    "FinNifty": "NIFTY FIN SERVICE"
}
selected_label = st.sidebar.selectbox("Select Index", list(index_map.keys()))
selected_symbol = index_map[selected_label]

# --- Data Fetching Function ---
def get_nse_data(symbol):
    try:
        # Fetch index data as a Pandas DataFrame
        df = market_data.get_indices_reading()
        # Filter for the selected index
        row = df[df['index'] == symbol]
        if not row.empty:
            return row.iloc[0].to_dict()
        return None
    except Exception as e:
        st.error(f"NSE Connection Error: {e}")
        return None

# --- Main Logic ---
data = get_nse_data(selected_symbol)

if data:
    # Extract data using the exact keys from nselib/NSE
    # Typical keys: 'last', 'variation', 'percentChange', 'open', 'high', 'low'
    ltp = data.get('last', 0)
    change = data.get('variation', 0)
    p_change = data.get('percentChange', 0)
    
    # --- Display Metrics ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Last Price", f"₹{ltp:,.2f}")
    col2.metric("Change", f"{change} ({p_change}%)", delta=float(change))
    col3.metric("Open", f"₹{data.get('open', 0):,.2f}")

    # --- Simulated Option Chain ---
    st.subheader(f"Strikes for {selected_label}")
    try:
        spot = float(ltp)
        interval = 100 if "Bank" in selected_label else 50
        atm = round(spot / interval) * interval
        
        # Generate 5 ITM and 5 OTM strikes
        strikes = [atm + (i * interval) for i in range(-5, 6)]
        strike_df = pd.DataFrame({
            "Strike Price": strikes,
            "Moneyness": ["ITM" if s < spot else "OTM" for s in strikes],
            "Distance": [f"{abs(s - spot):.2f}" for s in strikes]
        })
        st.table(strike_df)
    except:
        st.warning("Could not calculate strikes. Check if LTP is valid.")

    st.info(f"Last fetched at: {time.strftime('%H:%M:%S')}. Auto-refreshing in 30s...")
else:
    st.warning("No data received. NSE might be blocking the request or the market is closed.")
    if st.button("Retry Now"):
        st.rerun()

# --- Auto Refresh ---
# Do not set below 30s or NSE will block your Streamlit Cloud IP
time.sleep(30)
st.rerun()
