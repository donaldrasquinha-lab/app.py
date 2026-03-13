import streamlit as st
import pandas as pd
import upstox_client
from datetime import datetime

# --- API HELPERS ---

def get_api_client():
    config = upstox_client.Configuration()
    config.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
    return upstox_client.ApiClient(config)

def get_spot_price(index_key):
    """Fetches the current LTP of the Index."""
    try:
        api = upstox_client.MarketQuoteV3Api(get_api_client())
        resp = api.get_ltp(instrument_key=index_key)
        return resp.data[index_key].last_price
    except:
        return 0.0

@st.cache_data(ttl=3600)
def get_latest_expiry(index_key):
    """Detects the nearest expiry date."""
    try:
        api = upstox_client.OptionsApi(get_api_client())
        contracts = api.get_option_contracts(index_key)
        if not contracts.data: return None
        expiries = sorted(list(set(c.expiry for c in contracts.data)))
        return expiries[0] if expiries else None
    except:
        return None

# --- UI STYLING ---
st.set_page_config(page_title="Options Alpha", layout="centered")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card {
        background: rgba(30, 41, 59, 0.7);
        padding: 20px;
        border-radius: 15px;
        border-left: 10px solid #3b82f6;
        margin-bottom: 20px;
    }
    .spot-container {
        background: #1e293b;
        padding: 15px;
        border-radius: 12px;
        text-align: center;
        margin-bottom: 20px;
        border: 1px solid #334155;
    }
    .metric-label { color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; }
    .metric-value { color: #ffffff; font-weight: bold; font-size: 1.3rem; }
    </style>
    """, unsafe_allow_html=True)

st.title("🎯 Options Momentum")

# --- TOP BAR: INDEX & SPOT ---
index_name = st.selectbox("Select Index", ["Nifty 50", "Nifty Bank", "FINNIFTY"])
selected_key = f"NSE_INDEX|{index_name}"
spot_price = get_spot_price(selected_key)

st.markdown(f"""
    <div class="spot-container">
        <div class="metric-label">{index_name} SPOT</div>
        <div style="font-size: 1.8rem; color: #22c55e; font-weight: 800;">₹{spot_price:,.2f}</div>
    </div>
    """, unsafe_allow_html=True)

# --- INPUTS ---
col1, col2 = st.columns(2)
with col1:
    capital = st.number_input("Capital (₹)", value=50000, step=5000)
with col2:
    target_pct = st.number_input("Target %", value=20, step=5)

# --- DATA PROCESSING ---
lot_sizes = {"Nifty 50": 25, "Nifty Bank": 15, "FINNIFTY": 40}
current_lot_size = lot_sizes.get(index_name, 25)

expiry = get_latest_expiry(selected_key)
best_option = None

if expiry:
    api = upstox_client.OptionsApi(get_api_client())
    resp = api.get_put_call_option_chain(instrument_key=selected_key, expiry_date=expiry)
    
    if resp and resp.data:
        all_options = []
        for item in resp.data:
            # Check Call and Put for highest OI Change
            for opt_type, opt_data in [("CALL", item.call_options), ("PUT", item.put_options)]:
                if opt_data:
                    md = opt_data.market_data
                    # Manual OI Calculation
                    oi_surge = ((md.oi - md.prev_oi) / md.prev_oi * 100) if md.prev_oi > 0 else 0
                    
                    all_options.append({
                        "type": opt_type,
                        "strike": f"{item.strike_price} {'CE' if opt_type == 'CALL' else 'PE'}",
                        "ltp": md.ltp,
                        "oi_raw": oi_surge,
                        "oi_display": f"{oi_surge:+.1f}%"
                    })
        
        # FIND THE SINGLE BEST MOMENTUM OPTION
        if all_options:
            best_option = max(all_options, key=lambda x: x['oi_raw'])

# --- DISPLAY SINGLE OPTION CARD ---
if best_option:
    s = best_option
    accent_color = "#22c55e" if s['type'] == "CALL" else "#ef4444"
    
    # Calculations
    cost_per_lot = s['ltp'] * current_lot_size
    max_lots = int(capital // cost_per_lot) if cost_per_lot > 0 else 0
    exit_price = s['ltp'] * (1 + (target_pct / 100))
    est_profit = (exit_price - s['ltp']) * (max_lots * current_lot_size)

    st.markdown(f"""
    <div class="card" style="border-left-color: {accent_color};">
        <div style="display: flex; justify-content: space-between; align-items: start;">
            <div>
                <div class="metric-label">TOP MOMENTUM PICK</div>
                <h1 style="color: {accent_color}; margin: 0; font-size: 2.2rem;">{s['strike']}</h1>
            </div>
            <div style="text-align: right;">
                <div class="metric-label">CURRENT LTP</div>
                <div style="font-size: 1.5rem; font-family: monospace; color: white;">₹{s['ltp']}</div>
            </div>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 20px;">
            <div style="background: #0f172a; padding: 12px; border-radius: 10px; text-align: center;">
                <div class="metric-label">OI SURGE</div>
                <div class="metric-value" style="color: #eab308;">{s['oi_display']}</div>
            </div>
            <div style="background: #0f172a; padding: 12px; border-radius: 10px; text-align: center;">
                <div class="metric-label">MAX LOTS</div>
                <div class="metric-value">{max_lots}</div>
            </div>
        </div>

        <div style="background: {accent_color}15; margin-top: 20px; padding: 15px; border-radius: 10px; display: flex; justify-content: space-between; border: 1px solid {accent_color}33;">
            <div>
                <div class="metric-label" style="color: {accent_color}">EXIT TARGET</div>
                <div style="font-size: 1.4rem; font-weight: bold; color: white;">{exit_price:.2f}</div>
            </div>
            <div style="text-align: right;">
                <div class="metric-label" style="color: {accent_color}">EST. PROFIT</div>
                <div style="font-size: 1.4rem; font-weight: bold; color: white;">₹{int(est_profit):,}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.warning("No high-momentum data found for this expiry.")

st.caption(f"Refresh: {datetime.now().strftime('%H:%M:%S')} | Expiry: {expiry}")
