import streamlit as st
import pandas as pd
import upstox_client
from datetime import datetime, timedelta
import time

# --- API HELPERS ---
def get_api_client():
    config = upstox_client.Configuration()
    config.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
    return upstox_client.ApiClient(config)

def get_spot_price(index_key):
    try:
        api = upstox_client.MarketQuoteV3Api(get_api_client())
        resp = api.get_ltp(instrument_key=index_key)
        return resp.data[index_key].last_price
    except: return 0.0

@st.cache_data(ttl=3600)
def get_latest_expiry(index_key):
    try:
        api = upstox_client.OptionsApi(get_api_client())
        contracts = api.get_option_contracts(index_key)
        if not contracts.data: return None
        return sorted(list(set(c.expiry for c in contracts.data)))[0]
    except: return None

# --- UI STYLING ---
st.set_page_config(page_title="Options Alpha", layout="centered")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card { background: rgba(30, 41, 59, 0.7); padding: 20px; border-radius: 15px; border-left: 10px solid #3b82f6; margin-bottom: 20px; }
    .spot-container { background: #1e293b; padding: 15px; border-radius: 12px; text-align: center; margin-bottom: 20px; border: 1px solid #334155; }
    .metric-label { color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; }
    .metric-value { color: #ffffff; font-weight: bold; font-size: 1.3rem; }
    </style>
    """, unsafe_allow_html=True)

st.title("🎯 30-Min Momentum Radar")

# --- TOP BAR & SPOT ---
index_name = st.selectbox("Select Index", ["Nifty 50", "Nifty Bank", "FINNIFTY"])
selected_key = f"NSE_INDEX|{index_name}"
spot_price = get_spot_price(selected_key)

st.markdown(f"""<div class="spot-container"><div class="metric-label">{index_name} SPOT</div>
<div style="font-size: 1.8rem; color: #22c55e; font-weight: 800;">₹{spot_price:,.2f}</div></div>""", unsafe_allow_html=True)

# --- 30-MINUTE TRACKING LOGIC ---
# We store 'snapshots' in Streamlit session state to calculate the 30-min difference
if "oi_snapshots" not in st.session_state:
    st.session_state.oi_snapshots = {} # {instrument_key: {"oi": val, "time": timestamp}}

# --- DATA PROCESSING ---
expiry = get_latest_expiry(selected_key)
best_option = None

if expiry:
    api = upstox_client.OptionsApi(get_api_client())
    resp = api.get_put_call_option_chain(instrument_key=selected_key, expiry_date=expiry)
    
    if resp and resp.data:
        all_options = []
        # Find 5 strikes above and below the spot price
        # Sorted by strike price, we find the index of the strike closest to spot
        sorted_chain = sorted(resp.data, key=lambda x: abs(x.strike_price - spot_price))
        target_strikes = sorted_chain[:5] # The 5 closest strikes to spot
        
        current_time = datetime.now()

        for item in target_strikes:
            for opt_type, opt_data in [("CALL", item.call_options), ("PUT", item.put_options)]:
                if opt_data:
                    ikey = opt_data.instrument_key
                    current_oi = opt_data.market_data.oi
                    
                    # 1. Update/Get Snapshot Logic
                    if ikey not in st.session_state.oi_snapshots:
                        st.session_state.oi_snapshots[ikey] = {"oi": current_oi, "time": current_time}
                    
                    snapshot = st.session_state.oi_snapshots[ikey]
                    time_diff = (current_time - snapshot["time"]).total_seconds() / 60
                    
                    # If snapshot is older than 30 mins, we have our baseline
                    # For a fresh app start, it compares to the first time you opened the app
                    old_oi = snapshot["oi"]
                    oi_change_30m = current_oi - old_oi
                    surge_pct = (oi_change_30m / old_oi * 100) if old_oi > 0 else 0
                    
                    all_options.append({
                        "type": opt_type,
                        "strike": f"{item.strike_price} {'CE' if opt_type == 'CALL' else 'PE'}",
                        "ltp": opt_data.market_data.ltp,
                        "surge": surge_pct,
                        "oi_current": current_oi,
                        "time_tracked": round(time_diff, 1)
                    })
        
        if all_options:
            best_option = max(all_options, key=lambda x: x['surge'])

# --- RENDER CARD ---
if best_option:
    s = best_option
    accent = "#22c55e" if s['type'] == "CALL" else "#ef4444"
    st.markdown(f"""
    <div class="card" style="border-left-color: {accent};">
        <div style="display: flex; justify-content: space-between;">
            <div><div class="metric-label">30-MIN SURGE WINNER</div><h1 style="color: {accent}; margin: 0;">{s['strike']}</h1></div>
            <div style="text-align: right;"><div class="metric-label">LTP</div><div style="font-size: 1.5rem; color: white;">₹{s['ltp']}</div></div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 20px;">
            <div style="background: #0f172a; padding: 12px; border-radius: 10px; text-align: center;">
                <div class="metric-label">OI SURGE (30M)</div><div class="metric-value" style="color: #eab308;">{s['surge']:+.2f}%</div>
            </div>
            <div style="background: #0f172a; padding: 12px; border-radius: 10px; text-align: center;">
                <div class="metric-label">TRACKING MINS</div><div class="metric-value">{s['time_tracked']}m</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.info("Recording OI baselines... Please wait a few minutes for surge calculation.")

st.caption(f"Last Sync: {datetime.now().strftime('%H:%M:%S')} | Logic: Tracking OI change from first app load.")
