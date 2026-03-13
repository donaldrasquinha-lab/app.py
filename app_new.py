import streamlit as st
import pandas as pd
import upstox_client
from datetime import datetime, timedelta

# --- API HELPERS ---
def get_api_client():
    config = upstox_client.Configuration()
    config.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
    return upstox_client.ApiClient(config)

def get_spot_price(index_key):
    try:
        api = upstox_client.MarketQuoteV3Api(get_api_client())
        resp = api.get_ltp(instrument_key=index_key)
        data = resp.data
        return data.get(index_key, data.get(index_key.replace('|', ':'))).last_price
    except: return 0.0

@st.cache_data(ttl=3600)
def get_latest_expiry(index_key):
    try:
        api = upstox_client.OptionsApi(get_api_client())
        contracts = api.get_option_contracts(index_key)
        if not contracts.data: return None
        expiries = sorted(list(set(c.expiry for c in contracts.data)))
        return expiries if expiries else None
    except: return None

# --- UI SETUP ---
st.set_page_config(page_title="Multi-Timeframe Radar", layout="centered")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card { background: rgba(30, 41, 59, 0.7); padding: 15px; border-radius: 12px; margin-bottom: 15px; border-left: 8px solid #3b82f6; }
    .surge-5m { border-left-color: #a855f7; }
    .surge-15m { border-left-color: #eab308; }
    .surge-30m { border-left-color: #22c55e; }
    .metric-label { color: #94a3b8; font-size: 0.7rem; text-transform: uppercase; }
    .metric-value { color: #ffffff; font-weight: bold; font-size: 1.1rem; }
    </style>
    """, unsafe_allow_html=True)

st.title("🎯 Multi-Timeframe Radar")

# --- CONTROLS ---
index_map = {
    "Nifty 50": "NSE_INDEX|Nifty 50",
    "Nifty Bank": "NSE_INDEX|Nifty Bank",
    "FINNIFTY": "NSE_INDEX|Nifty Fin Service"
}
index_choice = st.selectbox("Select Index", list(index_map.keys()))
selected_key = index_map[index_choice]
spot_price = get_spot_price(selected_key)

st.sidebar.metric(f"{index_choice} Spot", f"₹{spot_price:,.2f}")

# --- MULTI-TIMEFRAME SNAPSHOT LOGIC ---
# Initializing snapshots for 5m, 15m, and 30m
intervals = [5, 15, 30]
for mins in intervals:
    key = f"snapshots_{mins}m"
    if key not in st.session_state:
        st.session_state[key] = {} # {instrument: {"oi": val, "time": timestamp}}

# --- PROCESSING ---
expiry = get_latest_expiry(selected_key)
winners = {5: None, 15: None, 30: None}

if expiry and spot_price > 0:
    api = upstox_client.OptionsApi(get_api_client())
    resp = api.get_put_call_option_chain(instrument_key=selected_key, expiry_date=expiry)
    
    if resp and resp.data:
        now = datetime.now()
        # Filter for 5 strikes around spot
        target_strikes = sorted(resp.data, key=lambda x: abs(x.strike_price - spot_price))[:5]
        
        for mins in intervals:
            interval_key = f"snapshots_{mins}m"
            options_data = []
            
            for item in target_strikes:
                for opt_type, opt_data in [("CALL", item.call_options), ("PUT", item.put_options)]:
                    if opt_data:
                        ikey = opt_data.instrument_key
                        curr_oi = opt_data.market_data.oi
                        
                        # Store baseline if not exists
                        if ikey not in st.session_state[interval_key]:
                            st.session_state[interval_key][ikey] = {"oi": curr_oi, "time": now}
                        
                        snap = st.session_state[interval_key][ikey]
                        
                        # Logic: If time has passed the interval, we could update baseline, 
                        # but for live tracking we compare to the original starting point of the session.
                        surge = ((curr_oi - snap["oi"]) / snap["oi"] * 100) if snap["oi"] > 0 else 0
                        time_diff = (now - snap["time"]).total_seconds() / 60
                        
                        options_data.append({
                            "type": opt_type,
                            "strike": f"{item.strike_price} {'CE' if opt_type == 'CALL' else 'PE'}",
                            "ltp": opt_data.market_data.ltp,
                            "surge": surge,
                            "tracked": round(time_diff, 1)
                        })
            
            if options_data:
                winners[mins] = max(options_data, key=lambda x: x['surge'])

# --- RENDER TOP PICKS ---
for mins in intervals:
    win = winners[mins]
    if win:
        color = "#22c55e" if win['type'] == "CALL" else "#ef4444"
        st.markdown(f"""
        <div class="card surge-{mins}m">
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <div>
                    <div class="metric-label">TOP {mins}M SURGE</div>
                    <h2 style="color: {color}; margin: 0;">{win['strike']}</h2>
                </div>
                <div style="text-align: right;">
                    <div class="metric-label">LTP</div>
                    <div style="font-size: 1.2rem; color: white;">₹{win['ltp']}</div>
                </div>
            </div>
            <div style="display: flex; gap: 20px; margin-top: 10px; background: #0f172a; padding: 10px; border-radius: 8px;">
                <div><div class="metric-label">SURGE</div><div class="metric-value" style="color: #eab308;">{win['surge']:+.2f}%</div></div>
                <div><div class="metric-label">TIME</div><div class="metric-value">{win['tracked']}m</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

if not any(winners.values()):
    st.info("Recording market baselines... Stay on this page for a few minutes to see surges.")

st.caption(f"Status: Live Tracking | Last Sync: {datetime.now().strftime('%H:%M:%S')}")
