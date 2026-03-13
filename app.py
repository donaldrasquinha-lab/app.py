import streamlit as st
import upstox_client
from upstox_client.rest import ApiException
from streamlit_autorefresh import st_autorefresh
import pandas as pd

# 1. UI Configuration (Mobile-First)
st.set_page_config(page_title="Options Alpha", layout="centered")

# Auto-refresh every 30 seconds
st_autorefresh(interval=30000, limit=100, key="ticker_refresh")

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
        color: white;
    }
    .put-card { border-left: 5px solid #ef4444; }
    .metric-label { color: #94a3b8; font-size: 0.7rem; text-transform: uppercase; }
    .metric-value { color: #3b82f6; font-weight: bold; font-size: 1.1rem; }
    </style>
    """, unsafe_allow_html=True)

# 2. Data Fetching Logic
def get_live_signals():
    try:
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
        api = upstox_client.OptionsApi(upstox_client.ApiClient(config))
        
        # Adjust expiry_date to the current nearest Thursday
        response = api.get_put_call_option_chain(
            instrument_key="NSE_INDEX|Nifty 50", 
            expiry_date="2026-03-19" 
        )
        
        chain = response.data
        parsed_signals = []
        
        # Filter for top 3 ATM Strikes (Call & Put)
        for item in chain[:6]:
            strike = item.strike_price
            if item.call_options:
                c = item.call_options.market_data
                parsed_signals.append({
                    "type": "CALL", "strike": f"NIFTY {strike} CE", 
                    "ltp": c.ltp, "oi_chg": f"{c.oi_change_pct:.1f}%", 
                    "gamma": "High" if c.gamma > 0.005 else "Low", "iv": c.iv
                })
            if item.put_options:
                p = item.put_options.market_data
                parsed_signals.append({
                    "type": "PUT", "strike": f"NIFTY {strike} PE", 
                    "ltp": p.ltp, "oi_chg": f"{p.oi_change_pct:.1f}%", 
                    "gamma": "High" if p.gamma > 0.005 else "Low", "iv": p.iv
                })
        return parsed_signals
    except Exception as e:
        st.error(f"API Error: {str(e)}")
        return []

# 3. Main Dashboard UI
st.title("🎯 Options Momentum")

# Thumb-friendly Inputs
col1, col2 = st.columns(2)
with col1:
    capital = st.number_input("Capital (₹)", value=200000, step=10000)
with col2:
    target_pct = st.number_input("Target %", value=15, step=5)

# Fetch Fresh Data
signals = get_live_signals()

if not signals:
    st.warning("Waiting for market data or API connection...")

# 4. Render Signal Cards
for s in signals:
    # Current SEBI Lot Size for Nifty is 75
    lot_size = 75 
    
    # Financial Calculations
    cost_per_lot = s['ltp'] * lot_size
    max_lots = int(capital // cost_per_lot) if cost_per_lot > 0 else 0
    exit_price = s['ltp'] * (1 + (target_pct / 100))
    est_profit = (exit_price - s['ltp']) * (max_lots * lot_size)

    # Style toggle
    border_class = "card" if s['type'] == "CALL" else "card put-card"
    color = "#22c55e" if s['type'] == "CALL" else "#ef4444"
    
    st.markdown(f"""
    <div class="{border_class}">
        <div style="display: flex; justify-content: space-between;">
            <h3 style="color: {color}; margin:0;">{s['strike']}</h3>
            <span style="font-family: monospace;">LTP: ₹{s['ltp']}</span>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; margin-top: 15px; text-align: center;">
            <div><div class="metric-label">OI Chg</div><div class="metric-value">{s['oi_chg']}</div></div>
            <div><div class="metric-label">IV</div><div class="metric-value" style="color: #eab308;">{s['iv']}</div></div>
            <div><div class="metric-label">Gamma</div><div class="metric-value" style="color: #a855f7;">{s['gamma']}</div></div>
        </div>
        <div style="background: rgba(0,0,0,0.3); margin-top: 12px; padding: 10px; border-radius: 8px; display: grid; grid-template-columns: 1fr 1fr 1fr; text-align: center;">
            <div><small>LOTS</small><br><b>{max_lots}</b></div>
            <div><small>EXIT @</small><br><b style="color:#22c55e">{exit_price:.2f}</b></div>
            <div><small>PROFIT</small><br><b>₹{int(est_profit):,}</b></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.caption("Data: Upstox V3 | Lot Size: 75 | Next refresh in 30s")
