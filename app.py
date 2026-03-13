import streamlit as st
import upstox_client
import urllib.parse
from datetime import datetime, timedelta

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

# 2. Login URL Setup
client_id = st.secrets["UPSTOX_CLIENT_ID"]
redirect_uri = st.secrets["UPSTOX_REDIRECT_URI"]
login_url = (
    f"https://api.upstox.com?"
    f"client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_uri)}"
)
st.link_button("Login to Upstox", login_url)

# 3. HELPER: Calculate Next Tuesday Expiry
def get_next_expiry():
    today = datetime.now()
    # NSE Nifty weekly expiry is now Tuesday (Day 1)
    # If today is Tuesday, it might still fetch today's data until market close
    days_ahead = (1 - today.weekday() + 7) % 7
    if days_ahead == 0 and today.hour >= 15: # If today is Tuesday after 3 PM, move to next week
        days_ahead = 7
    next_tuesday = today + timedelta(days_ahead)
    
    # Handle Holiday Shift (e.g., March 31, 2026 is a holiday, shifts to March 30)
    # This is a basic check for March 2026 specific holiday shifts
    expiry_str = next_tuesday.strftime("%Y-%m-%d")
    if expiry_str == "2026-03-31":
        return "2026-03-30"
    return expiry_str

# 4. FIXED: Live Data Fetching Function
def fetch_upstox_data():
    try:
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_EXTENDED_TOKEN"]
        
        api_client = upstox_client.ApiClient(config)
        options_api = upstox_client.OptionsApi(api_client)
        
        instrument = "NSE_INDEX|Nifty 50"
        expiry = get_next_expiry() # DYNAMICALLY CALCULATED
        
        response = options_api.get_put_call_option_chain(
            instrument_key=instrument, 
            expiry_date=expiry
        )
        
        processed_signals = []
        if response and response.data:
            for strike_row in response.data:
                for opt_key in ['call_options', 'put_options']:
                    opt_data = getattr(strike_row, opt_key, None)
                    if opt_data:
                        market = getattr(opt_data, 'market_data', None)
                        greeks = getattr(opt_data, 'option_greeks', None)
                        
                        processed_signals.append({
                            "type": "CE" if opt_key == 'call_options' else "PE",
                            "strike": opt_data.trading_symbol,
                            "ltp": market.ltp if market else 0.0,
                            "oi_chg": f"{market.oi_change_percentage:.1f}%" if market else "0.0%",
                            "gamma": f"{greeks.gamma:.4f}" if greeks else "0.00",
                            "iv": round(greeks.iv, 2) if greeks else 0.0
                        })
        return processed_signals, expiry
    except Exception as e:
        st.error(f"Connection Error: {str(e)}")
        return [], None

# 5. UI Layout
st.title("🎯 Options Momentum")
capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
target_pct = st.number_input("Target Return %", value=20, step=5)

if st.button('🔄 Refresh Live Data'):
    signals, used_expiry = fetch_upstox_data()
    
    if not signals:
        st.warning(f"No data for {used_expiry}. Ensure your API token is valid.")
    else:
        st.success(f"Showing data for Expiry: {used_expiry}")
        for s in signals[:10]:
            is_call = s['type'] == "CE"
            border_class = "card" if is_call else "card put-card"
            color = "#22c55e" if is_call else "#ef4444"
            
            lot_size = 50 
            cost_per_lot = s['ltp'] * lot_size
            if cost_per_lot > 0:
                max_lots = int(capital // cost_per_lot)
                exit_price = s['ltp'] * (1 + (target_pct / 100))
                est_profit = (exit_price - s['ltp']) * (max_lots * lot_size)
                
                st.markdown(f"""
                <div class="{border_class}">
                    <div style="display: flex; justify-content: space-between;">
                        <h2 style="color: {color}; margin:0; font-size: 1.1rem;">{s['strike']}</h2>
                        <b style="color: white;">₹{s['ltp']}</b>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; margin-top:10px; text-align: center;">
                        <div><div class="metric-label">OI Chg</div><div class="metric-value">{s['oi_chg']}</div></div>
                        <div><div class="metric-label">IV</div><div class="metric-value">{s['iv']}</div></div>
                        <div><div class="metric-label">Gamma</div><div class="metric-value">{s['gamma']}</div></div>
                    </div>
                    <div style="background: #0f172a; margin-top: 10px; padding: 8px; border-radius: 8px; display: grid; grid-template-columns: 1fr 1fr 1fr; text-align: center;">
                        <div><small>LOTS</small><br><b>{max_lots}</b></div>
                        <div><small>EXIT @</small><br><b style="color:#22c55e">{exit_price:.2f}</b></div>
                        <div><small>PROFIT</small><br><b>₹{int(est_profit)}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
