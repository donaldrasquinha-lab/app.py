import streamlit as st
import upstox_client
import urllib.parse
from upstox_client.rest import ApiException

# 1. UI Configuration
st.set_page_config(page_title="Options Alpha Live", layout="centered")

# Custom CSS for Professional Mobile UI
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .card {
        background: rgba(30, 41, 59, 0.7);
        padding: 15px;
        border-radius: 12px;
        border-left: 5px solid #22c55e;
        margin-bottom: 15px;
    }
    .put-card { border-left: 5px solid #ef4444; }
    .metric-label { color: #94a3b8; font-size: 0.7rem; text-transform: uppercase; }
    .metric-value { color: #3b82f6; font-weight: bold; font-size: 1rem; }
    </style>
    """, unsafe_allow_html=True)

# 2. Login Section
client_id = st.secrets["UPSTOX_CLIENT_ID"]
redirect_uri = st.secrets["UPSTOX_REDIRECT_URI"]
login_url = (
    f"https://api.upstox.com?"
    f"client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_uri)}"
)
st.link_button("🔑 Login to Upstox", login_url)

# 3. FIXED: Data Fetching Function
def fetch_upstox_data():
    try:
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_EXTENDED_TOKEN"]
        
        api_client = upstox_client.ApiClient(config)
        options_api = upstox_client.OptionsApi(api_client)
        
        # Using your specific secrets
        instrument = st.secrets["SYMBOL"]
        expiry = st.secrets["EXPIRY"]
        
        response = options_api.get_put_call_option_chain(
            instrument_key=instrument, 
            expiry_date=expiry
        )
        
        processed_signals = []
        if response and response.data:
            # response.data is a list of PutCallOptionChainData (strike rows)
            for strike_row in response.data:
                # Check both CE and PE inside each strike row
                for opt_key in ['call_options', 'put_options']:
                    opt_data = getattr(strike_row, opt_key, None)
                    
                    if opt_data:
                        # Extract nested values safely
                        market = getattr(opt_data, 'market_data', None)
                        greeks = getattr(opt_data, 'option_greeks', None)
                        
                        processed_signals.append({
                            "type": "CE" if opt_key == 'call_options' else "PE",
                            "strike": opt_data.trading_symbol, # FIX: Symbol is inside opt_data
                            "ltp": market.ltp if market else 0.0,
                            "oi_chg": f"{market.oi_change_percentage:.1f}%" if market else "0.0%",
                            "gamma": f"{greeks.gamma:.4f}" if greeks else "0.00",
                            "iv": round(greeks.iv, 2) if greeks else 0.0
                        })
        return processed_signals
    except Exception as e:
        st.error(f"⚠️ Connection Error: {str(e)}")
        return []

# 4. UI Layout & Logic
st.title("🎯 Options Momentum")
capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
target_pct = st.number_input("Target Return %", value=20, step=5)

if st.button('🔄 Refresh Live Data'):
    with st.spinner("Fetching Nifty Data..."):
        signals = fetch_upstox_data()
    
    if not signals:
        st.warning(f"No data found for {st.secrets['EXPIRY']}. Ensure your Token is fresh.")
    else:
        # Show top 10 active contracts
        for s in signals[:10]:
            is_call = s['type'] == "CE"
            border_class = "card" if is_call else "card put-card"
            color = "#22c55e" if is_call else "#ef4444"
            
            # Position sizing (Nifty Lot = 50)
            lot_size = 50 
            cost_per_lot = s['ltp'] * lot_size
            
            if cost_per_lot > 0:
                max_lots = int(capital // cost_per_lot)
                exit_price = s['ltp'] * (1 + (target_pct / 100))
                est_profit = (exit_price - s['ltp']) * (max_lots * lot_size)
                
                st.markdown(f"""
                <div class="{border_class}">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h3 style="color: {color}; margin:0; font-size: 1rem;">{s['strike']}</h3>
                        <span style="color: white; font-family: monospace; font-weight: bold;">₹{s['ltp']}</span>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; margin-top: 12px; text-align: center;">
                        <div><div class="metric-label">OI Chg</div><div class="metric-value">{s['oi_chg']}</div></div>
                        <div><div class="metric-label">IV</div><div class="metric-value" style="color: #eab308;">{s['iv']}</div></div>
                        <div><div class="metric-label">Gamma</div><div class="metric-value" style="color: #a855f7;">{s['gamma']}</div></div>
                    </div>
                    <div style="background: #0f172a; margin-top: 12px; padding: 10px; border-radius: 8px; display: grid; grid-template-columns: 1fr 1fr 1fr; text-align: center;">
                        <div><small style="color:#64748b">LOTS</small><br><b>{max_lots}</b></div>
                        <div><small style="color:#64748b">EXIT @</small><br><b style="color:#22c55e">{exit_price:.2f}</b></div>
                        <div><small style="color:#64748b">PROFIT</small><br><b>₹{int(est_profit)}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
else:
    st.info(f"Press Refresh to load {st.secrets['EXPIRY']} strikes.")
