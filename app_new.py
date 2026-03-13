import streamlit as st
import pandas as pd
import upstox_client
from datetime import datetime

# --- CONFIGURATION & API ---
st.set_page_config(page_title="Options Alpha", layout="centered")

def get_api_instance():
    config = upstox_client.Configuration()
    config.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
    return upstox_client.OptionsApi(upstox_client.ApiClient(config))

@st.cache_data(ttl=3600)
def get_latest_expiry(index_key):
    """Fetches all contracts and picks the closest upcoming expiry date."""
    try:
        api = get_api_instance()
        contracts = api.get_option_contracts(index_key)
        if not contracts.data:
            return None
        # Extract unique dates and sort ascending to get the nearest one
        expiries = sorted(list(set(c.expiry for c in contracts.data)))
        return expiries[0] if expiries else None
    except Exception:
        return None

def get_live_data(index_key, expiry):
    """Fetches live chain data for the selected index and date."""
    try:
        api = get_api_instance()
        return api.get_put_call_option_chain(instrument_key=index_key, expiry_date=expiry)
    except Exception as e:
        st.error(f"API Connection Error: {e}")
        return None

# --- GLASSMORPHISM UI STYLES ---
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

# --- CONTROLS SECTION ---
ctrl_col1, ctrl_col2 = st.columns([2, 1])
with ctrl_col1:
    index_name = st.selectbox("Select Index", ["Nifty 50", "Nifty Bank", "FINNIFTY"])
    selected_key = f"NSE_INDEX|{index_name}"
with ctrl_col2:
    st.write("") # Spacer
    refresh = st.button("🔄 Refresh Data")

# Auto-Expiry Logic
expiry_date = get_latest_expiry(selected_key)
if expiry_date:
    st.info(f"Targeting Latest Expiry: **{expiry_date}**")
else:
    st.error("Could not fetch expiry dates. Please check API Token.")

# Trading Parameters
col1, col2 = st.columns(2)
with col1:
    capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
with col2:
    target_pct = st.number_input("Target Return %", value=20, step=5)

# --- LIVE DATA PROCESSING ---
lot_sizes = {"Nifty 50": 25, "Nifty Bank": 15, "FINNIFTY": 40} # Current NSE Lot Sizes
current_lot_size = lot_sizes.get(index_name, 25)

processed_signals = []
if expiry_date:
    api_resp = get_live_data(selected_key, expiry_date)
    
    if api_resp and api_resp.data:
        # Show 10 strikes around the At-the-money (ATM) price
        mid = len(api_resp.data) // 2
        for item in api_resp.data[max(0, mid-5) : min(len(api_resp.data), mid+5)]:
            # Process CALLs
            if item.call_options:
                md = item.call_options.market_data
                oi_pct = ((md.oi - md.prev_oi) / md.prev_oi * 100) if md.prev_oi > 0 else 0
                processed_signals.append({
                    "type": "CALL", "strike": f"{item.strike_price} CE",
                    "ltp": md.ltp, "oi_chg": f"{oi_pct:+.1f}%",
                    "iv": "N/A", "gamma": "N/A" # IV/Greeks not in this endpoint
                })
            # Process PUTs
            if item.put_options:
                md = item.put_options.market_data
                oi_pct = ((md.oi - md.prev_oi) / md.prev_oi * 100) if md.prev_oi > 0 else 0
                processed_signals.append({
                    "type": "PUT", "strike": f"{item.strike_price} PE",
                    "ltp": md.ltp, "oi_chg": f"{oi_pct:+.1f}%",
                    "iv": "N/A", "gamma": "N/A"
                })

# --- RENDER SIGNAL CARDS ---
if not processed_signals:
    st.warning("Waiting for live data feed...")
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
                <div><small style="color:#64748b">MAX LOTS</small><br><b>{max_lots}</b></div>
                <div><small style="color:#64748b">EXIT TARGET</small><br><b style="color:#22c55e">{exit_price:.2f}</b></div>
                <div><small style="color:#64748b">EST. PROFIT</small><br><b>₹{int(est_profit)}</b></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

st.caption(f"Last Updated: {datetime.now().strftime('%H:%M:%S')} | Powered by Upstox V3")
