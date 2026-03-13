import streamlit as st
import pandas as pd
import upstox_client
from datetime import datetime
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
        # Ensure we access the dictionary correctly
        return resp.data[index_key].last_price
    except Exception as e:
        st.error(f"Error fetching spot: {e}")
        return 0.0

@st.cache_data(ttl=3600)
def get_latest_expiry(index_key):
    """Fetches valid expiry dates. Upstox uses YYYY-MM-DD."""
    try:
        api = upstox_client.OptionsApi(get_api_client())
        contracts = api.get_option_contracts(index_key)
        if not contracts.data: return None
        # Filter out past dates and sort
        today = datetime.now().strftime('%Y-%m-%d')
        expiries = sorted([c.expiry for c in contracts.data if c.expiry >= today])
        return expiries[0] if expiries else None
    except: return None

# --- UI STYLING ---
st.set_page_config(page_title="Options Alpha", layout="centered")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card { background: rgba(30, 41, 59, 0.7); padding: 20px; border-radius: 15px; border-left: 10px solid #3b82f6; margin-bottom: 20px; }
    .spot-box { background: #1e293b; padding: 15px; border-radius: 12px; border: 1px solid #334155; text-align: center; }
    .metric-label { color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; }
    .metric-value { color: #ffffff; font-weight: bold; font-size: 1.3rem; }
    </style>
    """, unsafe_allow_html=True)

st.title("🎯 30-Min Momentum Radar")

# --- CONTROLS ---
index_name = st.selectbox("Select Index", ["Nifty 50", "Nifty Bank", "FINNIFTY"])
# Fixed Key Format for Upstox
selected_key = f"NSE_INDEX|{index_name}"
spot_price = get_spot_price(selected_key)

st.markdown(f"""<div class="spot-box"><div class="metric-label">{index_name} SPOT</div>
<div style="font-size: 2rem; color: #22c55e; font-weight: 800;">₹{spot_price:,.2f}</div></div>""", unsafe_allow_html=True)

# --- 30-MINUTE PERSISTENCE ---
if "oi_snapshots" not in st.session_state:
    st.session_state.oi_snapshots = {}

# --- LIVE PROCESSING ---
expiry = get_latest_expiry(selected_key)
best_option = None

if expiry and spot_price > 0:
    api = upstox_client.OptionsApi(get_api_client())
    try:
        resp = api.get_put_call_option_chain(instrument_key=selected_key, expiry_date=expiry)
        
        if resp and resp.data:
            all_options = []
            # Logic: Filter the 5 strikes closest to the Spot Price
            sorted_chain = sorted(resp.data, key=lambda x: abs(x.strike_price - spot_price))
            target_strikes = sorted_chain[:5] 
            
            now = datetime.now()
            for item in target_strikes:
                for opt_type, opt_data in [("CALL", item.call_options), ("PUT", item.put_options)]:
                    if opt_data and opt_data.market_data.oi > 0:
                        ikey = opt_data.instrument_key
                        curr_oi = opt_data.market_data.oi
                        
                        # Snapshot logic for 30m tracking
                        if ikey not in st.session_state.oi_snapshots:
                            st.session_state.oi_snapshots[ikey] = {"oi": curr_oi, "time": now}
                        
                        snap = st.session_state.oi_snapshots[ikey]
                        old_oi = snap["oi"]
                        surge = ((curr_oi - old_oi) / old_oi * 100) if old_oi > 0 else 0
                        
                        all_options.append({
                            "type": opt_type,
                            "strike": f"{item.strike_price} {'CE' if opt_type == 'CALL' else 'PE'}",
                            "ltp": opt_data.market_data.ltp,
                            "surge": surge,
                            "time_diff": round((now - snap["time"]).total_seconds() / 60, 1)
                        })
            
            if all_options:
                # Get the single best surge
                best_option = max(all_options, key=lambda x: x['surge'])
        else:
            st.warning(f"No active option chain data found for expiry {expiry}.")
            
    except Exception as e:
        st.error(f"Failed to load Option Chain: {e}")

# --- DISPLAY ---
if best_option:
    s = best_option
    accent = "#22c55e" if s['type'] == "CALL" else "#ef4444"
    st.markdown(f"""
    <div class="card" style="border-left-color: {accent};">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div><div class="metric-label">TOP 30M SURGE</div><h1 style="color:{accent}; margin:0;">{s['strike']}</h1></div>
            <div style="text-align:right;"><div class="metric-label">LTP</div><div style="font-size:1.5rem; color:white;">₹{s['ltp']}</div></div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top:20px;">
            <div style="background:#0f172a; padding:12px; border-radius:10px; text-align:center;">
                <div class="metric-label">OI SURGE %</div><div class="metric-value" style="color:#eab308;">{s['surge']:+.2f}%</div>
            </div>
            <div style="background:#0f172a; padding:12px; border-radius:10px; text-align:center;">
                <div class="metric-label">TRACKING TIME</div><div class="metric-value">{s['time_diff']}m</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.info("Searching for high-momentum trades... Data will appear once OI change is detected.")

st.caption(f"Status: Connected | Expiry: {expiry} | Server Time: {datetime.now().strftime('%H:%M:%S')}")
