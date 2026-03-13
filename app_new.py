import streamlit as st
import pandas as pd
import upstox_client
from datetime import datetime

# --- API HELPERS ---
def get_api_client():
    """Initializes the Upstox API Client using secrets."""
    config = upstox_client.Configuration()
    config.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
    return upstox_client.ApiClient(config)

def get_live_market_data(index_key):
    """
    Fetches real-time Spot Price and Daily OHLC to determine market bias.
    Upstox V3 API returns keys with ':' instead of '|' in response bodies.
    """
    try:
        api = upstox_client.MarketQuoteV3Api(get_api_client())
        # LTP Quote V3 for the most recent price
        ltp_resp = api.get_ltp(instrument_key=index_key)
        # OHLC Quote V3 for daily range
        ohlc_resp = api.get_market_quote_ohlc(instrument_key=index_key, interval="1d")
        
        # Handle Upstox response key format (may swap '|' for ':')
        resp_key = index_key.replace('|', ':')
        spot = ltp_resp.data.get(index_key, ltp_resp.data.get(resp_key)).last_price
        ohlc = ohlc_resp.data.get(index_key, ohlc_resp.data.get(resp_key))
        
        # Synthetic VWAP (Typical Price) = (High + Low + Close) / 3
        vwap_proxy = (ohlc.high + ohlc.low + ohlc.close) / 3
        bias = "BULLISH" if spot >= vwap_proxy else "BEARISH"
        
        return spot, vwap_proxy, bias
    except Exception as e:
        st.error(f"Market Data Error: {e}")
        return 0.0, 0.0, "NEUTRAL"

@st.cache_data(ttl=3600)
def get_expiry_list(index_key):
    """Fetches valid future expiry dates for the selected index."""
    try:
        api = upstox_client.OptionsApi(get_api_client())
        contracts = api.get_option_contracts(index_key)
        today = datetime.now().strftime('%Y-%m-%d')
        return sorted(list(set(c.expiry for c in contracts.data if c.expiry >= today)))
    except: return []

# --- UI SETUP ---
st.set_page_config(page_title="Live VWAP Momentum Radar", layout="centered")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card { background: rgba(30, 41, 59, 0.7); padding: 20px; border-radius: 15px; border-left: 10px solid #3b82f6; margin-bottom: 20px; }
    .bullish-card { border-left-color: #22c55e; }
    .bearish-card { border-left-color: #ef4444; }
    .bias-badge { padding: 5px 12px; border-radius: 20px; font-weight: bold; font-size: 0.8rem; }
    .metric-label { color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; }
    </style>
    """, unsafe_allow_html=True)

st.title("🎯 Live VWAP Momentum Radar")

# --- CONTROLS ---
index_map = {
    "Nifty 50": "NSE_INDEX|Nifty 50", 
    "Nifty Bank": "NSE_INDEX|Nifty Bank", 
    "FINNIFTY": "NSE_INDEX|Nifty Fin Service"
}
index_choice = st.selectbox("Select Index", list(index_map.keys()))
selected_key = index_map[index_choice]

# Fetch Real-time Market Bias and Spot Price
spot_price, vwap_val, market_bias = get_live_market_data(selected_key)
badge_color = "#22c55e" if market_bias == "BULLISH" else "#ef4444"

# Display Live Stats Header
st.markdown(f"""
    <div style="background:#1e293b; padding:15px; border-radius:12px; border:1px solid #334155; display:flex; justify-content:space-around; align-items:center; margin-bottom:25px;">
        <div style="text-align:center;"><div class="metric-label">LIVE SPOT</div><div style="font-size:1.6rem; color:white; font-weight:bold;">₹{spot_price:,.2f}</div></div>
        <div style="text-align:center;"><div class="metric-label">VWAP PROXY</div><div style="font-size:1.6rem; color:#3b82f6; font-weight:bold;">₹{vwap_val:,.2f}</div></div>
        <div class="bias-badge" style="background:{badge_color}22; color:{badge_color}; border:1px solid {badge_color};">{market_bias}</div>
    </div>
    """, unsafe_allow_html=True)

# --- PROCESSING SINGLE BEST OPTION ---
if "oi_snapshots" not in st.session_state:
    st.session_state.oi_snapshots = {}

expiry_list = get_expiry_list(selected_key)
best_trade = None

if expiry_list and spot_price > 0:
    target_expiry = expiry_list[0] # Pick nearest expiry
    try:
        api = upstox_client.OptionsApi(get_api_client())
        # Fetching Option Chain
        resp = api.get_put_call_option_chain(instrument_key=selected_key, expiry_date=target_expiry)
        
        if resp and resp.data:
            # Filter: Show 5 strikes closest to current Spot Price
            target_strikes = sorted(resp.data, key=lambda x: abs(x.strike_price - spot_price))[:5]
            options_pool = []
            
            for item in target_strikes:
                # Logic: CALL if Bullish, PUT if Bearish
                trade_type = "CALL" if market_bias == "BULLISH" else "PUT"
                opt_data = item.call_options if trade_type == "CALL" else item.put_options
                
                if opt_data:
                    ikey = opt_data.instrument_key
                    curr_oi = opt_data.market_data.oi
                    
                    # Persistence for 30m Surge tracking
                    if ikey not in st.session_state.oi_snapshots:
                        st.session_state.oi_snapshots[ikey] = {"oi": curr_oi, "time": datetime.now()}
                    
                    snap = st.session_state.oi_snapshots[ikey]
                    # Manual OI calculation using market_data.prev_oi for daily change
                    surge = ((curr_oi - snap["oi"]) / snap["oi"] * 100) if snap["oi"] > 0 else 0
                    
                    options_pool.append({
                        "type": trade_type, 
                        "strike": f"{item.strike_price} {'CE' if trade_type == 'CALL' else 'PE'}",
                        "ltp": opt_data.market_data.ltp, 
                        "surge": surge,
                        "time": round((datetime.now() - snap["time"]).total_seconds() / 60, 1)
                    })
            
            if options_pool:
                best_trade = max(options_pool, key=lambda x: x['surge'])
    except Exception as e:
        st.error(f"Option Chain Error: {e}")

# --- RENDER BEST TRADE CARD ---
if best_trade:
    s = best_trade
    card_class = "card bullish-card" if market_bias == "BULLISH" else "card bearish-card"
    st.markdown(f"""
    <div class="{card_class}">
        <div style="display:flex; justify-content:space-between; align-items:start;">
            <div><div class="metric-label">MOMENTUM PICK</div><h1 style="color:{badge_color}; margin:0; font-size:2.4rem;">{s['strike']}</h1></div>
            <div style="text-align:right;"><div class="metric-label">LTP</div><div style="font-size:1.8rem; color:white; font-family:monospace;">₹{s['ltp']}</div></div>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:15px; margin-top:25px;">
            <div style="background:#0f172a; padding:15px; border-radius:12px; text-align:center;">
                <div class="metric-label">OI SURGE</div><div style="color:#eab308; font-weight:bold; font-size:1.6rem;">{s['surge']:+.2f}%</div>
            </div>
            <div style="background:#0f172a; padding:15px; border-radius:12px; text-align:center;">
                <div class="metric-label">TRACKING</div><div style="color:white; font-weight:bold; font-size:1.6rem;">{s['time']}m</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.info("🔄 Refreshing momentum data... Initializing baseline snapshots.")

st.caption(f"Live Data via Upstox API V3 | Sync: {datetime.now().strftime('%H:%M:%S')}")
