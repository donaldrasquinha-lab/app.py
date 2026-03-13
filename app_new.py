import streamlit as st
import pandas as pd
import upstox_client
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. UI SETUP (MUST BE FIRST STREAMLIT COMMAND) ---
st.set_page_config(page_title="Price Action & OI Radar", layout="centered")

# --- 2. AUTO-REFRESH (Every 60 Seconds) ---
st_autorefresh(interval=60 * 1000, key="radar_refresh")

# --- 3. SESSION STATE INITIALIZATION ---
if "oi_snapshots" not in st.session_state:
    st.session_state.oi_snapshots = {}

# --- API HELPERS ---
def get_api_client():
    config = upstox_client.Configuration()
    config.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
    return upstox_client.ApiClient(config)

def safe_get_instrument(data_dict, key):
    alt_key = key.replace('|', ':')
    return data_dict.get(key) or data_dict.get(alt_key)

def get_market_data(index_key):
    try:
        api = upstox_client.MarketQuoteV3Api(get_api_client())
        ltp_resp = api.get_ltp(instrument_key=index_key)
        ohlc_resp = api.get_market_quote_ohlc(instrument_key=index_key, interval="1d")
        
        spot_obj = safe_get_instrument(ltp_resp.data, index_key)
        spot = spot_obj.last_price if spot_obj else 0.0
        
        ohlc_obj = safe_get_instrument(ohlc_resp.data, index_key)
        vwap_val, day_high, day_low = spot, spot, spot
        
        if ohlc_obj and hasattr(ohlc_obj, 'ohlc'):
            prices = ohlc_obj.ohlc
            vwap_val = (prices.high + prices.low + prices.close) / 3
            day_high = prices.high
            day_low = prices.low
            
        return spot, vwap_val, day_high, day_low
    except Exception as e:
        st.error(f"Market Data Error: {e}")
        return 0.0, 0.0, 0.0, 0.0

@st.cache_data(ttl=3600)
def get_expiry_list(index_key):
    try:
        api = upstox_client.OptionsApi(get_api_client())
        contracts = api.get_option_contracts(index_key)
        today = datetime.now().strftime('%Y-%m-%d')
        return sorted(list(set(c.expiry for c in contracts.data if c.expiry >= today)))
    except: return []

# --- STYLING ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card { background: rgba(30, 41, 59, 0.7); padding: 20px; border-radius: 15px; border-left: 10px solid #3b82f6; margin-bottom: 20px; }
    .uptrend-bg { background: linear-gradient(90deg, #14532d 0%, #0e1117 100%); border: 1px solid #22c55e; }
    .downtrend-bg { background: linear-gradient(90deg, #450a0a 0%, #0e1117 100%); border: 1px solid #ef4444; }
    .sideways-bg { background: #1e293b; border: 1px solid #334155; }
    .metric-label { color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; margin-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏹 Price Action & Sentiment Radar")

index_map = {
    "Nifty 50": "NSE_INDEX|Nifty 50", 
    "Nifty Bank": "NSE_INDEX|Nifty Bank", 
    "FINNIFTY": "NSE_INDEX|Nifty Fin Service"
}
index_choice = st.selectbox("Select Index", list(index_map.keys()))
selected_key = index_map[index_choice]

# Fetch Market Data
spot_price, vwap_price, d_high, d_low = get_market_data(selected_key)
expiry_list = get_expiry_list(selected_key)

# --- INITIALIZE DEFAULTS (Prevents NameError) ---
trend_status = "INITIALIZING"
trend_class = "sideways-bg"
trend_color = "#94a3b8"
total_ce_oi, total_pe_oi = 0, 0
pcr, best_trade = 0.0, None

# --- CORE LOGIC ---
if expiry_list and spot_price > 0:
    try:
        api = upstox_client.OptionsApi(get_api_client())
        # Use first available expiry
        target_expiry = expiry_list[0]
        resp = api.get_put_call_option_chain(instrument_key=selected_key, expiry_date=target_expiry)
        
        if resp and resp.data:
            # 1. Aggregate OI for Sentiment
            for item in resp.data:
                if item.call_options: total_ce_oi += item.call_options.market_data.oi
                if item.put_options: total_pe_oi += item.put_options.market_data.oi
            
            pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0

            # 2. Trend Determination (Price + Sentiment)
            is_bullish = (spot_price > vwap_price) and (pcr > 1.0)
            is_bearish = (spot_price < vwap_price) and (pcr < 1.0)
            
            trend_status = "UPTREND" if is_bullish else "DOWNTREND" if is_bearish else "SIDEWAYS"
            trend_class = "uptrend-bg" if is_bullish else "downtrend-bg" if is_bearish else "sideways-bg"
            trend_color = "#22c55e" if is_bullish else "#ef4444" if is_bearish else "#94a3b8"

            # 3. Momentum Trade Pick
            trade_side = "CALL" if is_bullish or (not is_bearish and spot_price > vwap_price) else "PUT"
            target_strikes = sorted(resp.data, key=lambda x: abs(x.strike_price - spot_price))[:5]
            options_pool = []
            
            for item in target_strikes:
                opt_data = item.call_options if trade_side == "CALL" else item.put_options
                if opt_data:
                    ikey = opt_data.instrument_key
                    curr_oi = opt_data.market_data.oi
                    
                    if ikey not in st.session_state.oi_snapshots:
                        st.session_state.oi_snapshots[ikey] = {"oi": curr_oi, "time": datetime.now()}
                    
                    snap = st.session_state.oi_snapshots[ikey]
                    surge = ((curr_oi - snap["oi"]) / snap["oi"] * 100) if snap["oi"] > 0 else 0
                    
                    options_pool.append({
                        "strike": f"{item.strike_price} {'CE' if trade_side == 'CALL' else 'PE'}",
                        "ltp": opt_data.market_data.ltp, 
                        "surge": surge,
                        "time": round((datetime.now() - snap["time"]).total_seconds() / 60, 1)
                    })
            
            if options_pool:
                best_trade = max(options_pool, key=lambda x: x['surge'])
    except Exception as e:
        st.error(f"Logic Error: {e}")

# --- UI: OVERALL TREND INDICATOR ---
st.markdown(f"""
    <div class="{trend_class}" style="padding:20px; border-radius:15px; text-align:center; margin-bottom:25px;">
        <div style="color:white; font-size:0.8rem; letter-spacing:3px; font-weight:600; opacity:0.8;">MARKET STRUCTURE</div>
        <div style="color:{trend_color}; font-size:2.8rem; font-weight:900; margin:10px 0;">{trend_status}</div>
        <div style="color:#94a3b8; font-size:0.8rem;">Price vs VWAP: {'ABOVE' if spot_price > vwap_price else 'BELOW'} | PCR: {pcr:.2f}</div>
    </div>
    """, unsafe_allow_html=True)

# --- UI: METRICS GRID ---
col1, col2, col3 = st.columns(3)
with col1: 
    st.metric("LIVE SPOT", f"₹{spot_price:,.2f}", f"{spot_price-vwap_price:+.2f}")
with col2: 
    st.metric("PCR SENTIMENT", f"{pcr:.2f}", f"{(total_pe_oi - total_ce_oi):+,.0f} Net OI")
with col3: 
    st.metric("DAY HIGH", f"₹{d_high:,.0f}", f"Low: ₹{d_low:,.0f}", delta_color="off")

# --- UI: TRADE PICK CARD ---
if best_trade:
    s = best_trade
    st.markdown(f"""
    <div class="card" style="border-left-color:{trend_color};">
        <div style="display:flex; justify-content:space-between; align-items:start;">
            <div><div class="metric-label">MOMENTUM PICK</div><h1 style="color:{trend_color}; margin:0;">{s['strike']}</h1></div>
            <div style="text-align:right;"><div class="metric-label">LTP</div><div style="font-size:1.5rem; color:white; font-weight:bold;">₹{s['ltp']}</div></div>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:15px; margin-top:20px;">
            <div style="background:#0f172a; padding:15px; border-radius:12px; text-align:center;">
                <div class="metric-label">OI SURGE</div><div style="color:#eab308; font-weight:bold; font-size:1.3rem;">{s['surge']:+.2f}%</div>
            </div>
            <div style="background:#0f172a; padding:15px; border-radius:12px; text-align:center;">
                <div class="metric-label">SNAPSHOT AGE</div><div style="color:white; font-weight:bold; font-size:1.3rem;">{s['time']}m</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.info("Gathering live data... Wait for the next 60s cycle to calculate OI surge.")

# --- FOOTER ---
st.caption(f"Last API Sync: {datetime.now().strftime('%H:%M:%S')} | Logic: PCR + VWAP Divergence")
