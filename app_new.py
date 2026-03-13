import streamlit as st
import pandas as pd
import upstox_client
from datetime import datetime

# --- API CONFIGURATION ---
def get_api_client():
    config = upstox_client.Configuration()
    config.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
    return upstox_client.ApiClient(config)

def get_spot_price(index_key):
    """Fetches real-time Spot Price with fixed key formatting."""
    try:
        api = upstox_client.MarketQuoteV3Api(get_api_client())
        resp = api.get_ltp(instrument_key=index_key)
        # Upstox returns a dictionary where keys might use ':' instead of '|' in response
        # We try both to ensure data is captured
        data = resp.data
        return data.get(index_key, data.get(index_key.replace('|', ':'))).last_price
    except Exception:
        return 0.0

@st.cache_data(ttl=3600)
def get_latest_expiry(index_key):
    """Fetches the nearest valid expiry date for the index."""
    try:
        api = upstox_client.OptionsApi(get_api_client())
        contracts = api.get_option_contracts(index_key)
        if not contracts.data: return None
        # Sort and return the first (closest) upcoming date
        expiries = sorted(list(set(c.expiry for c in contracts.data)))
        return expiries[0] if expiries else None
    except:
        return None

# --- UI SETUP ---
st.set_page_config(page_title="30-Min Momentum Radar", layout="centered")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card { background: rgba(30, 41, 59, 0.7); padding: 20px; border-radius: 15px; border-left: 10px solid #22c55e; margin-bottom: 20px; }
    .put-card { border-left-color: #ef4444; }
    .spot-box { background: #1e293b; padding: 15px; border-radius: 12px; border: 1px solid #334155; text-align: center; margin-bottom: 20px; }
    .metric-label { color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; }
    .metric-value { color: #ffffff; font-weight: bold; font-size: 1.4rem; }
    </style>
    """, unsafe_allow_html=True)

st.title("🎯 30-Min Momentum Radar")

# --- CONTROLS ---
# Fixed Keys: Nifty 50, Nifty Bank, Nifty Fin Service
index_map = {
    "Nifty 50": "NSE_INDEX|Nifty 50",
    "Nifty Bank": "NSE_INDEX|Nifty Bank",
    "FINNIFTY": "NSE_INDEX|Nifty Fin Service"
}

index_choice = st.selectbox("Select Index", list(index_map.keys()))
selected_key = index_map[index_choice]
spot_price = get_spot_price(selected_key)

st.markdown(f"""<div class="spot-box"><div class="metric-label">{index_choice} SPOT</div>
<div style="font-size: 2rem; color: #22c55e; font-weight: 800;">₹{spot_price:,.2f}</div></div>""", unsafe_allow_html=True)

# --- 30-MINUTE MOMENTUM TRACKER ---
if "oi_snapshots" not in st.session_state:
    st.session_state.oi_snapshots = {}

expiry = get_latest_expiry(selected_key)
best_option = None

if expiry and spot_price > 0:
    api = upstox_client.OptionsApi(get_api_client())
    resp = api.get_put_call_option_chain(instrument_key=selected_key, expiry_date=expiry)
    
    if resp and resp.data:
        all_options = []
        # Filter Logic: Find 5 strikes closest to the Spot Price
        sorted_chain = sorted(resp.data, key=lambda x: abs(x.strike_price - spot_price))
        target_strikes = sorted_chain[:5]
        
        now = datetime.now()
        for item in target_strikes:
            for opt_type, opt_data in [("CALL", item.call_options), ("PUT", item.put_options)]:
                if opt_data:
                    ikey = opt_data.instrument_key
                    curr_oi = opt_data.market_data.oi
                    
                    # Store first seen OI as baseline for 30-min comparison
                    if ikey not in st.session_state.oi_snapshots:
                        st.session_state.oi_snapshots[ikey] = {"oi": curr_oi, "time": now}
                    
                    snap = st.session_state.oi_snapshots[ikey]
                    # Calculate Surge % from the baseline snapshot
                    surge = ((curr_oi - snap["oi"]) / snap["oi"] * 100) if snap["oi"] > 0 else 0
                    time_diff = (now - snap["time"]).total_seconds() / 60
                    
                    all_options.append({
                        "type": opt_type,
                        "strike": f"{item.strike_price} {'CE' if opt_type == 'CALL' else 'PE'}",
                        "ltp": opt_data.market_data.ltp,
                        "surge": surge,
                        "time_diff": round(time_diff, 1)
                    })
        
        # Pick the SINGLE option with the highest surge
        if all_options:
            best_option = max(all_options, key=lambda x: x['surge'])

# --- RENDER RADAR ---
if best_option:
    s = best_option
    border_class = "card" if s['type'] == "CALL" else "card put-card"
    color = "#22c55e" if s['type'] == "CALL" else "#ef4444"
    
    st.markdown(f"""
    <div class="{border_class}">
        <div style="display: flex; justify-content: space-between; align-items: start;">
            <div><div class="metric-label">TOP 30M SURGE PICK</div><h1 style="color:{color}; margin:0;">{s['strike']}</h1></div>
            <div style="text-align:right;"><div class="metric-label">LTP</div><div style="font-size:1.5rem; color:white;">₹{s['ltp']}</div></div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 20px;">
            <div style="background:#0f172a; padding:12px; border-radius:10px; text-align:center;">
                <div class="metric-label">OI SURGE %</div><div class="metric-value" style="color:#eab308;">{s['surge']:+.2f}%</div>
            </div>
            <div style="background:#0f172a; padding:12px; border-radius:10px; text-align:center;">
                <div class="metric-label">TRACKING</div><div class="metric-value">{s['time_diff']}m</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.info("Taking initial snapshots... Data will reflect once OI changes from baseline.")

st.caption(f"Sync: {datetime.now().strftime('%H:%M:%S')} | Expiry: {expiry}")
