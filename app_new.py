import streamlit as st
import pandas as pd
import upstox_client
from datetime import datetime

# --- CONFIGURATION & API ---
st.set_page_config(page_title="Options Alpha", layout="centered")

def get_live_data(index_key, expiry):
    try:
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
        api = upstox_client.OptionsApi(upstox_client.ApiClient(config))
        # Fetching the live chain for the selected index and expiry
        return api.get_put_call_option_chain(instrument_key=index_key, expiry_date=expiry)
    except Exception as e:
        st.error(f"Upstox API Error: {e}")
        return None

# --- CUSTOM UI STYLES ---
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

# --- CONTROLS ---
ctrl_col1, ctrl_col2 = st.columns([2, 1])
with ctrl_col1:
    index_name = st.selectbox("Index", ["Nifty 50", "Nifty Bank", "FINNIFTY"])
    selected_key = f"NSE_INDEX|{index_name}"
with ctrl_col2:
    # Example expiry - in production, fetch this dynamically via get_expiry
    expiry_date = st.text_input("Expiry (YYYY-MM-DD)", "2024-05-30")

col1, col2 = st.columns(2)
with col1:
    capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
with col2:
    target_pct = st.number_input("Target Return %", value=20, step=5)

# --- LIVE DATA PROCESSING ---
lot_sizes = {"Nifty 50": 50, "Nifty Bank": 15, "FINNIFTY": 40}
current_lot_size = lot_sizes.get(index_name, 50)

# Fetch data and filter for ATM (At-the-money) contracts
api_resp = get_live_data(selected_key, expiry_date)
processed_signals = []

if api_resp and api_resp.data:
    # Sort by proximity to spot price to find ATM
    for item in api_resp.data:
        # Check if call/put data exists in the response
        if item.call_options:
            processed_signals.append({
                "type": "CALL",
                "strike": f"{index_name} {item.strike_price} CE",
                "ltp": item.call_options.market_data.ltp,
                "oi_chg": f"{item.call_options.market_data.oi_change_pct:.1f}%",
                "iv": round(item.call_options.market_data.iv, 2),
                "gamma": "N/A" # Greeks often require separate MarketQuoteV3Api call
            })
        if item.put_options:
            processed_signals.append({
                "type": "PUT",
                "strike": f"{index_name} {item.strike_price} PE",
                "ltp": item.put_options.market_data.ltp,
                "oi_chg": f"{item.put_options.market_data.oi_change_pct:.1f}%",
                "iv": round(item.put_options.market_data.iv, 2),
                "gamma": "N/A"
            })

# --- UI RENDERING ---
# Display top 2 momentum signals (e.g., highest OI change)
for s in processed_signals[:4]: # Showing top 4 for variety
    border_class = "card" if s['type'] == "CALL" else "card put-card"
    color = "#22c55e" if s['type'] == "CALL" else "#ef4444"
    
    # Real-time calculations
    cost_per_lot = s['ltp'] * current_lot_size
    max_lots = int(capital // cost_per_lot) if cost_per_lot > 0 else 0
    exit_price = s['ltp'] * (1 + (target_pct / 100))
    est_profit = (exit_price - s['ltp']) * (max_lots * current_lot_size)

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

st.caption(f"Last Sync: {datetime.now().strftime('%H:%M:%S')} | Data: Upstox API V3")
