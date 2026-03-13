import streamlit as st
import pandas as pd
import upstox_client
from datetime import datetime

# --- API HELPERS ---

def get_api_instance():
    config = upstox_client.Configuration()
    config.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
    return upstox_client.OptionsApi(upstox_client.ApiClient(config))

@st.cache_data(ttl=3600)  # Cache expiry list for 1 hour
def get_latest_expiry(index_key):
    """Fetches all available expiries and returns the closest one."""
    try:
        api = get_api_instance()
        # Fetching all contracts for the index
        contracts = api.get_option_contracts(index_key)
        if not contracts.data:
            return None
        # Extract unique expiry dates and sort them
        expiries = sorted(list(set(c.expiry for c in contracts.data)))
        return expiries[0] if expiries else None
    except Exception as e:
        st.error(f"Error fetching expiries: {e}")
        return None

def get_live_data(index_key, expiry):
    """Fetches the live option chain for the specified expiry."""
    try:
        api = get_api_instance()
        return api.get_put_call_option_chain(instrument_key=index_key, expiry_date=expiry)
    except Exception as e:
        st.error(f"Upstox API Error: {e}")
        return None

# --- UI CONFIGURATION ---

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

# --- CONTROLS ---

ctrl_col1, ctrl_col2 = st.columns([2, 1])
with ctrl_col1:
    index_name = st.selectbox("Select Index", ["Nifty 50", "Nifty Bank", "FINNIFTY"])
    selected_key = f"NSE_INDEX|{index_name}"
with ctrl_col2:
    refresh = st.button("🔄 Refresh")

# Automatic Expiry Detection
latest_expiry = get_latest_expiry(selected_key)
st.info(f"Using Latest Expiry: **{latest_expiry}**")

# Input Section (Optimized for Thumb-usage)
col1, col2 = st.columns(2)
with col1:
    capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
with col2:
    target_pct = st.number_input("Target Return %", value=20, step=5)

# --- LIVE DATA PROCESSING ---

lot_sizes = {"Nifty 50": 50, "Nifty Bank": 15, "FINNIFTY": 40}
current_lot_size = lot_sizes.get(index_name, 50)

processed_signals = []
if latest_expiry:
    api_resp = get_live_data(selected_key, latest_expiry)
    
    if api_resp and api_resp.data:
        # Show top 5 momentum strikes (middle of the chain)
        mid = len(api_resp.data) // 2
        for item in api_resp.data[mid-2 : mid+3]:
            # Process CALLs
            if item.call_options:
                md = item.call_options.market_data
                # Fix: Manually calculate OI Change % as it's not a direct field in V3
                oi_pct = ((md.oi - md.prev_oi) / md.prev_oi * 100) if md.prev_oi > 0 else 0
                processed_signals.append({
                    "type": "CALL", "strike": f"{item.strike_price} CE",
                    "ltp": md.ltp, "oi_chg": f"{oi_pct:+.1f}%",
                    "iv": round(md.iv, 2), "gamma": "Med"
                })
            # Process PUTs
            if item.put_options:
                md = item.put_options.market_data
                oi_pct = ((md.oi - md.prev_oi) / md.prev_oi * 100) if md.prev_oi > 0 else 0
                processed_signals.append({
                    "type": "PUT", "strike": f"{item.strike_price} PE",
                    "ltp": md.ltp, "oi_chg": f"{oi_pct:+.1f}%",
                    "iv": round(md.iv, 2), "gamma": "Med"
                })

# --- LIVE SIGNAL CARDS ---

if not processed_signals:
    st.warning("No live data available for this selection.")
else:
    for s in processed_signals:
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

st.caption(f"Last Sync: {datetime.now().strftime('%H:%M:%S')} | Upstox API V3")
