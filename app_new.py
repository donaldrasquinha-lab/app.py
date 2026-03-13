import streamlit as st
import pandas as pd
import upstox_client
from datetime import datetime

# --- API HELPERS ---

def get_api_config():
    config = upstox_client.Configuration()
    config.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
    return config

def get_spot_price(index_key):
    """Fetches the current LTP of the selected Index."""
    try:
        api_instance = upstox_client.MarketQuoteV3Api(upstox_client.ApiClient(get_api_config()))
        resp = api_instance.get_ltp(instrument_key=index_key)
        # Accessing the nested LTP value from the response object
        return resp.data[index_key].last_price
    except Exception:
        return "N/A"

@st.cache_data(ttl=3600)
def get_latest_expiry(index_key):
    try:
        api = upstox_client.OptionsApi(upstox_client.ApiClient(get_api_config()))
        contracts = api.get_option_contracts(index_key)
        if not contracts.data: return None
        expiries = sorted(list(set(c.expiry for c in contracts.data)))
        return expiries[0] if expiries else None
    except Exception:
        return None

# --- UI STYLES ---
st.set_page_config(page_title="Options Alpha", layout="centered")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card { background: rgba(30, 41, 59, 0.7); padding: 20px; border-radius: 15px; border-left: 5px solid #22c55e; margin-bottom: 20px; }
    .put-card { border-left: 5px solid #ef4444; }
    .spot-box { background: #1e293b; padding: 10px 15px; border-radius: 10px; color: #22c55e; font-weight: bold; font-family: monospace; font-size: 1.1rem; border: 1px solid #334155; }
    .metric-label { color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; }
    .metric-value { color: #3b82f6; font-weight: bold; font-size: 1.2rem; }
    </style>
    """, unsafe_allow_html=True)

st.title("🎯 Options Momentum")

# --- CONTROLS WITH SPOT PRICE ---
selected_index = st.selectbox("Select Index", ["Nifty 50", "Nifty Bank", "FINNIFTY"])
selected_key = f"NSE_INDEX|{selected_index}"

# Fetch Spot Price immediately
spot_price = get_spot_price(selected_key)

st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px;">
        <span style="color: #94a3b8;">Current Spot:</span>
        <div class="spot-box">₹{spot_price}</div>
    </div>
    """, unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
with col2:
    target_pct = st.number_input("Target Return %", value=20, step=5)

# --- PROCESSING SINGLE MOMENTUM SIGNAL ---
lot_sizes = {"Nifty 50": 25, "Nifty Bank": 15, "FINNIFTY": 40}
current_lot_size = lot_sizes.get(selected_index, 25)

expiry = get_latest_expiry(selected_key)
best_signal = None

if expiry:
    api = upstox_client.OptionsApi(upstox_client.ApiClient(get_api_config()))
    resp = api.get_put_call_option_chain(instrument_key=selected_key, expiry_date=expiry)
    
    if resp and resp.data:
        all_signals = []
        for item in resp.data:
            # Check both Call and Put for highest OI momentum
            for opt_type, opt_data in [("CALL", item.call_options), ("PUT", item.put_options)]:
                if opt_data:
                    md = opt_data.market_data
                    oi_val = ((md.oi - md.prev_oi) / md.prev_oi * 100) if md.prev_oi > 0 else 0
                    all_signals.append({
                        "type": opt_type,
                        "strike": f"{item.strike_price} {'CE' if opt_type == 'CALL' else 'PE'}",
                        "ltp": md.ltp,
                        "oi_pct_raw": oi_val, # Use for sorting
                        "oi_chg": f"{oi_val:+.1f}%"
                    })
        
        # Select ONLY the one signal with the highest OI Change %
        if all_signals:
            best_signal = max(all_signals, key=lambda x: x['oi_pct_raw'])

# --- RENDER SINGLE CARD ---
if best_signal:
    s = best_signal
    border_class = "card" if s['type'] == "CALL" else "card put-card"
    color = "#22c55e" if s['type'] == "CALL" else "#ef4444"
    
    cost_per_lot = s['ltp'] * current_lot_size
    max_lots = int(capital // cost_per_lot) if cost_per_lot > 0 else 0
    exit_p = s['ltp'] * (1 + (target_pct / 100))
    est_prof = (exit_p - s['ltp']) * (max_lots * current_lot_size)

    st.markdown(f"""
    <div class="{border_class}">
        <div style="display: flex; justify-content: space-between;">
            <h2 style="color: {color}; margin:0;">{s['strike']}</h2>
            <span style="color: white; font-family: monospace; background: #0f172a; padding: 2px 8px; border-radius: 5px;">🔥 TOP MOMENTUM</span>
        </div>
        <div style="margin: 10px 0; font-size: 1.1rem; color: #fff;">LTP: ₹{s['ltp']}</div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; text-align: center; margin-bottom: 15px;">
            <div style="background: #0f172a; padding: 10px; border-radius: 8px;">
                <div class="metric-label">OI Surge</div><div class="metric-value">{s['oi_chg']}</div>
            </div>
            <div style="background: #0f172a; padding: 10px; border-radius: 8px;">
                <div class="metric-label">Buy Lots</div><div class="metric-value" style="color: #a855f7;">{max_lots}</div>
            </div>
        </div>
        <div style="background: #22c55e22; padding: 15px; border-radius: 10px; display: flex; justify-content: space-between;">
            <div><small style="color:#64748b">EXIT TARGET</small><br><b style="color:#22c55e; font-size: 1.2rem;">{exit_p:.2f}</b></div>
            <div style="text-align: right;"><small style="color:#64748b">EST. PROFIT</small><br><b style="color:white; font-size: 1.2rem;">₹{int(est_prof)}</b></div>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.warning("Scanning for high-momentum opportunities...")

st.caption(f"Sync: {datetime.now().strftime('%H:%M:%S')} | Expiry: {expiry}")
