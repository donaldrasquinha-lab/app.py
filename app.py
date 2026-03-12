import streamlit as st
import pandas as pd
import upstox_client
from upstox_client.rest import ApiException

# 1. Mobile UI Configuration
st.set_page_config(page_title="Options Alpha Live", layout="centered")

# Custom CSS for Mobile UI
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

# 2. LIVE DATA FETCHING FUNCTION
def fetch_upstox_data():
    try:
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_EXTENDED_TOKEN"]
        
        api_client = upstox_client.ApiClient(config)
        options_api = upstox_client.OptionsApi(api_client)
        
        # Pull parameters from secrets or use defaults
        instrument = st.secrets.get("SYMBOL", "NSE_INDEX|Nifty 50")
        expiry = st.secrets.get("EXPIRY", "2024-03-28") # Update this to current Thursday
        
        response = options_api.get_put_call_option_chain(
            instrument_key=instrument, 
            expiry_date=expiry
        )
        
        processed_signals = []
        if response and response.data:
            for contract in response.data:
                greeks = getattr(contract, 'option_greeks', None)
                processed_signals.append({
                    "type": contract.instrument_type, # CE or PE
                    "strike": contract.trading_symbol,
                    "ltp": contract.last_price,
                    "oi_chg": f"{contract.oi_change_percentage:.1f}%",
                    "gamma": f"{greeks.gamma:.4f}" if greeks else "0.00",
                    "iv": round(greeks.iv, 2) if greeks else 0.0
                })
        return processed_signals
    except Exception as e:
        st.error(f"Connection Error: {str(e)}")
        return []

# 3. UI LAYOUT
st.title("🎯 Options Momentum")

col1, col2 = st.columns(2)
with col1:
    capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
with col2:
    target_pct = st.number_input("Target Return %", value=20, step=5)

# 4. DATA EXECUTION
if st.button('🔄 Refresh Live Data'):
    signals = fetch_upstox_data()
    
    if not signals:
        st.warning("No live data found. Check Expiry Date in Secrets.")
    else:
        # Show top 8 active contracts to keep mobile view clean
        for s in signals[:8]:
            is_call = s['type'] == "CE"
            border_class = "card" if is_call else "card put-card"
            color = "#22c55e" if is_call else "#ef4444"
            
            # Position & Exit Calculations
            lot_size = 50  # Nifty Lot
            cost_per_lot = s['ltp'] * lot_size
            
            if cost_per_lot > 0:
                max_lots = int(capital // cost_per_lot)
                exit_price = s['ltp'] * (1 + (target_pct / 100))
                est_profit = (exit_price - s['ltp']) * (max_lots * lot_size)
                
                st.markdown(f"""
                <div class="{border_class}">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h2 style="color: {color}; margin:0; font-size: 1.1rem;">{s['strike']}</h2>
                        <span style="color: white; font-family: monospace;">₹{s['ltp']}</span>
                    </div>
                    <hr style="opacity: 0.1; margin: 10px 0;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; text-align: center;">
                        <div><div class="metric-label">OI Chg</div><div class="metric-value">{s['oi_chg']}</div></div>
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
else:
    st.info("Click 'Refresh' to fetch live Nifty strikes.")

st.caption("Powered by Upstox API V3")
