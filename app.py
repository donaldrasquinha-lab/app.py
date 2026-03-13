import streamlit as st
import yfinance as yf
import time

# Page Configuration
st.set_page_config(page_title="Nifty 50 Live Tracker", layout="centered")
st.title("📈 Nifty 50 Live Price")

# Placeholder for the metric to avoid page flickering
placeholder = st.empty()

def get_nifty_data():
    # Fetch Nifty 50 data (Ticker: ^NSEI)
    nifty = yf.Ticker("^NSEI")
    data = nifty.history(period="1d", interval="1m")
    
    if not data.empty:
        current_price = data['Close'].iloc[-1]
        previous_close = nifty.info.get('previousClose', current_price)
        change = current_price - previous_close
        return round(current_price, 2), round(change, 2)
    return None, None

# Infinite loop to refresh data
while True:
    price, change = get_nifty_data()
    
    with placeholder.container():
        if price:
            st.metric(label="NSE Nifty 50", value=f"₹{price}", delta=f"{change}")
            st.write(f"Last updated: {time.strftime('%H:%M:%S')}")
        else:
            st.error("Could not fetch live data. Please check your connection.")
    
    # Refresh every 60 seconds to stay within API limits
    time.sleep(60)
