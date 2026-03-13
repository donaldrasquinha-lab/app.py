import upstox_client

def get_live_data():
    config = upstox_client.Configuration()
    config.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
    api = upstox_client.OptionsApi(upstox_client.ApiClient(config))
    return api.get_put_call_option_chain(instrument_key="NSE_INDEX|Nifty 50", expiry_date="2024-05-30")


import streamlit as st
import pandas as pd

# Mobile UI Configuration
st.set_page_config(page_title="Options Alpha", layout="centered")

# Custom CSS for Mobile Glassmorphism UI
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

st.title("🎯 Options Momentum")

# --- INPUT SECTION (Optimized for Thumb-usage) ---
col1, col2 = st.columns(2)
with col1:
    capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
with col2:
    target_pct = st.number_input("Target Return %", value=20, step=5)

# --- MOCK DATA (Replace with Upstox API calls) ---
# In a live setup, use: upstox_client.OptionsApi().get_put_call_option_chain()
signals = [
    {"type": "CALL", "strike": "NIFTY 22500 CE", "ltp": 142.0, "oi_chg": "+24%", "gamma": "High", "iv": 14.2},
    {"type": "PUT", "strike": "NIFTY 22300 PE", "ltp": 88.5, "oi_chg": "+18%", "gamma": "Med", "iv": 18.5}
]

# --- LIVE SIGNAL CARDS ---
for s in signals:
    border_class = "card" if s['type'] == "CALL" else "card put-card"
    color = "#22c55e" if s['type'] == "CALL" else "#ef4444"
    
    # Calculations
    lot_size = 50
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

st.caption("Data source: Upstox API V3 | Refresh every 30s")
