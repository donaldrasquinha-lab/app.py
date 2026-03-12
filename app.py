import streamlit as st
import upstox_client
from upstox_client.rest import ApiException

def get_live_option_chain():
    """
    Fetches the live option chain from Upstox using 
    credentials stored in Streamlit Secrets.
    """
    try:
        # 1. Setup Configuration from Secrets
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_ACCESS_TOKEN"]
        
        # 2. Initialize API Client
        api_client = upstox_client.ApiClient(config)
        api_instance = upstox_client.OptionsApi(api_client)
        
        # 3. Fetch Data using parameters from Secrets
        instrument = st.secrets["SYMBOL"]
        expiry = st.secrets["EXPIRY"]
        
        api_response = api_instance.get_put_call_option_chain(
            instrument_key=instrument, 
            expiry_date=expiry
        )
        
        return api_response.data
        
    except ApiException as e:
        st.error(f"Upstox API Error: {e}")
        return None
    except KeyError:
        st.error("Secret 'UPSTOX_ACCESS_TOKEN' not found in Streamlit Secrets!")
        return None

# --- Streamlit UI ---
st.title("Upstox Live Monitor")

if st.button('Fetch Live Data'):
    data = get_live_option_chain()
    if data:
        st.success("Data fetched successfully!")
        st.write(data) # Displays the raw JSON/Object data
import streamlit as st
import pandas as pd

# Mobile UI Configuration
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

# --- INPUT SECTION (Optimized for Thumb-usage) ---
col1, col2 = st.columns(2)
with col1:
    capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
with col2:
    target_pct = st.number_input("Target Return %", value=20, step=5)

import streamlit as st
import upstox_client
from upstox_client.rest import ApiException

# --- PAGE SETUP ---
st.set_page_config(page_title="Live Options Alpha", layout="centered")

# Custom CSS for Mobile Glassmorphism UI (Same as before)
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
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

# --- LIVE DATA FETCHING ---
def get_live_signals():
    """Fetches and filters live option chain data from Upstox."""
    config = upstox_client.Configuration()
    config.access_token = st.secrets["UPSTOX_EXTENDED_TOKEN"]
    
    api_client = upstox_client.ApiClient(config)
    options_api = upstox_client.OptionsApi(api_client)
    
    try:
        # Fetch data for NIFTY 50
        # Ensure your expiry_date matches the current active weekly/monthly expiry
        response = options_api.get_put_call_option_chain(
            instrument_key="NSE_INDEX|Nifty 50", 
            expiry_date="2024-05-30" 
        )
        
        # Mapping Upstox response to our Dashboard UI
        live_data = []
        for contract in response.data:
            # We typically want near-the-money (NTM) strikes for high Gamma
            # You can add a filter here to only show strikes near Spot Price
            live_data.append({
                "type": contract.instrument_type,      # 'CE' or 'PE'
                "strike": contract.trading_symbol,
                "ltp": contract.last_price,
                "oi_chg": f"{contract.oi_change_percentage:.1f}%",
                "gamma": f"{contract.option_greeks.gamma:.4f}",
                "iv": round(contract.option_greeks.iv, 2)
            })
        return live_data
    except ApiException as e:
        st.error(f"Upstox API Error: {e.body}")
        return []

# --- UI LOGIC ---
st.title("🎯 Live Options Monitor")

# User Inputs for Calculator
col1, col2 = st.columns(2)
with col1:
    capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
with col2:
    target_pct = st.number_input("Target Return %", value=20, step=5)

# Trigger Live Refresh
if st.button('🔄 Refresh Live Data'):
    signals = get_live_signals()
    
    if not signals:
        st.warning("No data found. Check your API Token and Expiry Date.")
    else:
        for s in signals[:6]:  # Showing top 6 most active strikes for mobile performance
            border_class = "card" if s['type'] == "CE" else "card put-card"
            color = "#22c55e" if s['type'] == "CE" else "#ef4444"
            
            # Position & Exit Logic
            lot_size = 50  # Nifty lot size
            cost_per_lot = s['ltp'] * lot_size
            max_lots = int(capital // cost_per_lot) if cost_per_lot > 0 else 0
            exit_price = s['ltp'] * (1 + (target_pct / 100))
            est_profit = (exit_price - s['ltp']) * (max_lots * lot_size)

            st.markdown(f"""
            <div class="{border_class}">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h2 style="color: {color}; margin:0;">{s['strike']}</h2>
                    <span style="color: white; font-family: monospace;">₹{s['ltp']}</span>
                </div>
                <hr style="opacity: 0.1; margin: 10px 0;">
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; text-align: center;">
                    <div><div class="metric-label">OI % Chg</div><div class="metric-value">{s['oi_chg']}</div></div>
                    <div><div class="metric-label">IV</div><div class="metric-value" style="color: #eab308;">{s['iv']}</div></div>
                    <div><div class="metric-label">Gamma</div><div class="metric-value" style="color: #a855f7;">{s['gamma']}</div></div>
                </div>
                <div style="background: #0f172a; margin-top: 15px; padding: 10px; border-radius: 10px; display: grid; grid-template-columns: 1fr 1fr 1fr; text-align: center;">
                    <div><small style="color:#64748b">MAX LOTS</small><br><b>{max_lots}</b></div>
                    <div><small style="color:#64748b">EXIT @</small><br><b style="color:#22c55e">{exit_price:.2f}</b></div>
                    <div><small style="color:#64748b">PROFIT</small><br><b>₹{int(est_profit)}</b></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
else:
    st.info("Tap 'Refresh' to load real-time Nifty Option Chain.")

# --- LIVE SIGNAL CARDS ---
for s in signals:
    border_class = "card" if s['type'] == "CALL" else "card put-card"
    color = "#22c55e" if s['type'] == "CALL" else "#ef4444"
    
    # Calculations
    lot_size = 50
    cost_per_lot = s['ltp'] * lot_size
    max_lots = int(capital // cost_per_lot)
    exit_price = s['ltp'] * (1 + (target_pct / 100))
    est_profit = (exit_price - s['ltp']) * (max_lots * lot_size)

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

st.caption("Data source: Upstox API V3 | Refresh every 30s")






