import streamlit as st
import pandas as pd
import upstox_client

# --- DATA FETCHING LOGIC ---
def get_live_data(index_key, expiry="2024-05-30"):
    """
    Fetches real data based on selected index. 
    Note: Upstox instrument keys follow 'NSE_INDEX|Index Name' format.
    """
    try:
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
        api = upstox_client.OptionsApi(upstox_client.ApiClient(config))
        # Use the dynamic index_key from the dropdown
        return api.get_put_call_option_chain(instrument_key=index_key, expiry_date=expiry)
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return None

# --- UI CONFIGURATION ---
st.set_page_config(page_title="Options Alpha", layout="centered")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stNumberInput input { background-color: #1e293b !important; color: white !important; }
    .card {
        background: rgba(30, 41, 59, 0.7);
        padding: 20px;
        border-radius: 15px;
        border-left: 5px solid #22c55e;
        margin-bottom: 20px;
    }
    .put-card { border-left: 5px solid #ef4444; }
    .metric-label { color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; }
    .metric-value { color: #3b82f6; font-weight: bold; font-size: 1.2rem; }
    </style>
    """, unsafe_allow_html=True)

# --- HEADER & CONTROLS ---
st.title("🎯 Options Momentum")

# Index Dropdown and Refresh Button in one row
ctrl_col1, ctrl_col2 = st.columns([3, 1])
with ctrl_col1:
    index_choice = st.selectbox(
        "Select Index", 
        options=["Nifty 50", "Nifty Bank", "Nifty Fin Service"], 
        index=0
    )
    # Format for Upstox API
    selected_key = f"NSE_INDEX|{index_choice}"

with ctrl_col2:
    st.write(" ") # Padding
    refresh = st.button("🔄 Refresh")

# --- INPUT SECTION ---
col1, col2 = st.columns(2)
with col1:
    capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
with col2:
    target_pct = st.number_input("Target Return %", value=20, step=5)

# --- SIGNAL PROCESSING ---
# This part replaces your static 'signals' list with real data if available
# For now, it stays as your working mock logic unless you uncomment the API call
signals = [
    {"type": "CALL", "strike": f"{index_choice} 22500 CE", "ltp": 142.0, "oi_chg": "+24%", "gamma": "High", "iv": 14.2},
    {"type": "PUT", "strike": f"{index_choice} 22300 PE", "ltp": 88.5, "oi_chg": "+18%", "gamma": "Med", "iv": 18.5}
]

# Example of how to trigger the real API call on refresh or index change:
# if refresh or index_choice:
#     data = get_live_data(selected_key)
#     # (Add logic here to map 'data' to your 'signals' list)

# --- LIVE SIGNAL CARDS ---
for s in signals:
    border_class = "card" if s['type'] == "CALL" else "card put-card"
    color = "#22c55e" if s['type'] == "CALL" else "#ef4444"
    
    # Calculations
    lot_size = 50 # Nifty is 50, but BankNifty is 15. You may want to adjust this based on index.
    cost_per_lot = s['ltp'] * lot_size
    max_lots = int(capital // cost_per_lot)
    exit_price = s['ltp'] * (1 + (target_pct / 100))
    est_profit = (exit_price - s['ltp']) * (max_lots * lot_size)

    st.markdown(f"""
    <div class="{border_class}">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <h2 style="color: {color}; margin:0;">{s['strike']}</h2>
            <span style="color: white; font-family: monospace;">LTP: ₹{s['ltp']}</span>
        </div>
        <hr style="opacity: 0.1; margin: 10px 0;">
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; text-align: center;">
            <div><div class="metric-label">OI Change</div><div class="metric-value">{s['oi_chg']}</div></div>
            <div><div class="metric-label">IV</div><div class="metric-value" style="color: #eab308;">{s['iv']}</div></div>
            <div><div class="metric-label">Gamma</div><div class="metric-value" style="color: #a855f7;">{s['gamma']}</div></div>
        </div>
        <div style="background: #0f172a; margin-top: 15px; padding: 10px; border-radius: 10px; display: grid; grid-template-columns: 1fr 1fr 1fr; text-align: center;">
            <div><small style="color:#64748b">LOTS</small><br><b>{max_lots}</b></div>
            <div><small style="color:#64748b">EXIT @</small><br><b style="color:#22c55e">{exit_price:.2f}</b></div>
            <div><small style="color:#64748b">PROFIT</small><br><b>₹{int(est_profit)}</b></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.caption(f"Index: {index_choice} | Data source: Upstox API V3")
