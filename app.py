import streamlit as st
import pandas as pd
import time

# Attempt to import nselib; show a nice error if it's missing
try:
    from nselib import market_data
except ImportError:
    st.error("Missing 'nselib' library. Please add 'nselib' to your requirements.txt file.")
    st.stop()

# --- Page Config ---
st.set_page_config(page_title="NSE Live Tracker", layout="wide")
st.title("🇮🇳 NSE Live Index Dashboard")

# --- Sidebar Selection ---
index_map = {
    "NIFTY 50": "NIFTY 50",
    "NIFTY BANK": "NIFTY BANK",
    "NIFTY FIN SERVICE": "NIFTY FIN SERVICE"
}
selected_symbol = st.sidebar.selectbox("Select Index", list(index_map.keys()))

# --- Data Fetching Function ---
def get_nse_data(symbol):
    try:
        # nselib returns a DataFrame of all major indices
        df = market_data.get_indices_reading()
        
        # Clean column names (sometimes they have extra spaces)
        df.columns = [c.strip().lower() for c in df.columns]
        
        # Filter for the selected index
        # Usually the column is 'index' or 'indexname'
        row = df[df['index'].str.contains(symbol, case=False, na=False)]
        
        if not row.empty:
            return row.iloc[0].to_dict()
        return None
    except Exception as e:
        st.error(f"NSE Connection Error: {e}")
        return None

# --- Main Logic ---
data = get_nse_data(selected_symbol)

if data:
    # Safely get values using common NSE keys
    ltp = data.get('last', 0)
    change = data.get('variation', 0)
    p_change = data.get('percentchange', 0)
    
    # --- Display Metrics ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Last Price", f"₹{ltp}")
    col2.metric("Change", f"{change} ({p_change}%)")
    col3.metric("Open", f"₹{data.get('open', 0)}")

    # --- Simulated Option Chain ---
    st.subheader(f"Strikes for {selected_symbol}")
    try:
        spot = float(str(ltp).replace(',', ''))
        interval = 100 if "BANK" in selected_symbol else 50
        atm = round(spot / interval) * interval
        
        strikes = [atm + (i * interval) for i in range(-5, 6)]
        strike_df = pd.DataFrame({
            "Strike Price": strikes,
            "Moneyness": ["ITM" if s < spot else "OTM" for s in strikes]
        })
        st.table(strike_df)
    except:
        st.warning("Could not calculate strikes. LTP might be formatted as string.")

    st.info(f"Last updated: {time.strftime('%H:%M:%S')}. Next update in 30s.")
else:
    st.warning("No data received. The NSE site might be busy or the market is closed.")

# --- Auto Refresh ---
# NSE will block you if you refresh faster than 30 seconds
time.sleep(30)
st.rerun()
