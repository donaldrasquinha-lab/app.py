import streamlit as st
import upstox_client
import urllib.parse
from upstox_client.rest import ApiException

# 1. UI Configuration
st.set_page_config(page_title="Options Alpha Live", layout="centered")

# Custom CSS for Mobile UI
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

# 2. Login URL Setup (using your secrets)
client_id = st.secrets["UPSTOX_CLIENT_ID"]
redirect_uri = st.secrets["UPSTOX_REDIRECT_URI"]
login_url = (
    f"https://api.upstox.com?"
    f"client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_uri)}"
)
st.link_button("Login to Upstox", login_url)

# 3. FIXED: Live Data Fetching Function
def fetch_upstox_data():
    try:
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_EXTENDED_TOKEN"]
        
        api_client = upstox_client.ApiClient(config)
        options_api = upstox_client.OptionsApi(api_client)
        
        # Pull parameters from your secrets
        instrument = st.secrets["SYMBOL"]
        expiry = st.secrets["EXPIRY"]
        
        response = options_api.get_put_call_option_chain(
            instrument_key=instrument, 
            expiry_date=expiry
        )
        
        processed_signals = []
        if response and response.data:
            # Each 'strike_row' is a PutCallOptionChainData object
            for strike_row in response.data:
                
                # Check for Call Options (CE) and Put Options (PE) in the row
                for side in ['call_options', 'put_options']:
                    opt_data = getattr(strike_row, side, None)
                    
                    if opt_data:
                        # Extract nested values safely using getattr
                        market = getattr(opt_data, 'market_data', None)
                        greeks = getattr(opt_data, 'option_greeks', None)
                        
                        processed_signals.append({
                            "type": "CE" if side == 'call_options' else "PE",
                            "strike": opt_data.trading_symbol, # FIX: Symbol is inside the option object
                            "ltp": market.ltp if market else 0.0,
                            "oi_chg": f"{market.oi_change_percentage:.1f}%" if market else "0.0%",
                            "gamma": f"{greeks.gamma:.4f}" if greeks else "0.00",
                            "iv": round(greeks.iv, 2) if greeks else 0.0
                        })
        return processed_signals
    except Exception as e:
        st.error(f"Connection Error: {str(e)}")
        return []

# 4. UI Layout & Execution
st.title("🎯 Options Momentum")

col1, col2 = st.columns(2)
with col1:
    capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
with col2:
    target_pct = st.number_input("Target Return %", value=20, step=5)

if st.button('🔄 Refresh Live Data'):
    signals = fetch_upstox_data()
    
    if not signals:
        st.warning(f"No live data found for {st.secrets['EXPIRY']}. Please check your Token or Expiry date.")
    else:
        # Sort or filter if needed, here we show the first 12 results (CE and PE)
        for s in signals[:12]:
            is_call = s['type'] == "CE"
            border_class = "card" if is_call else "card put-card"
            color = "#22c55e" if is_call else "#ef4444"
            
            # Position & Exit Calculations (Nifty Lot Size = 75)
            lot_size = 75  
            cost_per_lot = s['ltp'] * lot_size
            
            if cost_per_lot > 0:
                max_lots = int(capital // cost_per_lot)
                exit_price = s['ltp'] * (1 + (target_pct / 100))
                est_profit = (exit_price - s['ltp']) * (max_lots * lot_size)
                
                st.markdown(f"""
                <div class="{border_class}">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h2 style="color: {color}; margin:0; font-size: 1.1rem;">{s['strike']}</h2>
                        <span style="color: white; font-family: monospace; font-weight: bold;">₹{s['ltp']}</span>
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
    st.info(f"Currently monitoring {st.secrets['SYMBOL']} for {st.secrets['EXPIRY']}.")

st.caption("Powered by Upstox API V2")
