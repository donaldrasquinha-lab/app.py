import streamlit as st
import upstox_client
from upstox_client.rest import ApiException
from datetime import datetime, timedelta

# --- 1. PAGE SETUP ---
st.set_page_config(page_title="Options Momentum Pro", layout="centered")

# Custom CSS for Mobile Glassmorphism UI
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: white; }
    .stNumberInput input { background-color: #1e293b !important; color: white !important; }
    .card {
        background: rgba(30, 41, 59, 0.7);
        padding: 18px;
        border-radius: 12px;
        border-left: 5px solid #22c55e;
        margin-bottom: 15px;
    }
    .put-card { border-left: 5px solid #ef4444; }
    .metric-label { color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; }
    .metric-value { color: #3b82f6; font-weight: bold; font-size: 1.1rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DYNAMIC EXPIRY CALCULATION ---
def get_current_expiry():
    """Finds the upcoming Thursday for Nifty expiry."""
    today = datetime.now()
    days_until_thursday = (3 - today.weekday() + 7) % 7
    # If today is Thursday after market hours (3:30 PM), move to next week
    if days_until_thursday == 0 and today.hour >= 15 and today.minute >= 30:
        days_until_thursday = 7
    target_date = today + timedelta(days=days_until_thursday)
    return target_date.strftime("%Y-%m-%d")

# --- 3. LIVE DATA FETCHING ---
def get_live_data():
    if "UPSTOX_EXTENDED_TOKEN" not in st.secrets:
        st.error("Missing 'UPSTOX_EXTENDED_TOKEN' in Streamlit Secrets!")
        return []

    config = upstox_client.Configuration()
    config.access_token = st.secrets["UPSTOX_EXTENDED_TOKEN"]
    
    api_instance = upstox_client.OptionsApi(upstox_client.ApiClient(config))
    
    try:
        instrument = st.secrets.get("SYMBOL", "NSE_INDEX|Nifty 50")
        expiry = st.secrets.get("EXPIRY", get_current_expiry())
        
        # Upstox API v3 call
        response = api_instance.get_put_call_option_chain(instrument, expiry)
        
        live_list = []
        if response and response.data:
            for item in response.data:
                # Handling separate call/put objects in the response
                for side in ['call_options', 'put_options']:
                    opt = getattr(item, side, None)
                    if opt:
                        greeks = getattr(opt, 'option_greeks', None)
                        live_list.append({
                            "type": "CE" if side == 'call_options' else "PE",
                            "strike": opt.trading_symbol,
                            "ltp": getattr(opt, 'market_data', {}).last_price if hasattr(opt, 'market_data') else 0.0,
                            "oi": getattr(opt, 'market_data', {}).oi if hasattr(opt, 'market_data') else 0.0,
                            "gamma": f"{greeks.gamma:.4f}" if greeks else "0.00",
                            "iv": round(greeks.iv, 2) if greeks else 0.0
                        })
        return live_list
    except ApiException as e:
        st.error(f"API Error: {e.body}")
        return []

# --- 4. DASHBOARD UI ---
st.title("🎯 Options Momentum")

col1, col2 = st.columns(2)
with col1:
    capital = st.number_input("Capital (₹)", value=50000, step=5000)
with col2:
    target = st.number_input("Exit Target %", value=20, step=5)

if st.button('🔄 Refresh Real-Time Data'):
    data = get_live_data()
    
    if not data:
        st.warning("No data found. Verify your Token and Expiry date.")
    else:
        # Show top signals based on Nifty Lot Size (50)
        for s in data[:8]:
            is_ce = s['type'] == "CE"
            card_style = "card" if is_ce else "card put-card"
            accent_color = "#22c55e" if is_ce else "#ef4444"
            
            # Position Math
            lot_size = 50
            cost = s['ltp'] * lot_size
            if cost > 0:
                lots = int(capital // cost)
                exit_px = s['ltp'] * (1 + (target / 100))
                profit = (exit_px - s['ltp']) * (lots * lot_size)
            else:
                lots, exit_px, profit = 0, 0, 0

            st.markdown(f"""
            <div class="{card_style}">
                <div style="display: flex; justify-content: space-between;">
                    <b style="color: {accent_color}; font-size: 1.1rem;">{s['strike']}</b>
                    <span style="font-family: monospace;">₹{s['ltp']:.2f}</span>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; margin-top: 15px; text-align: center;">
                    <div><div class="metric-label">IV</div><div class="metric-value">{s['iv']}</div></div>
                    <div><div class="metric-label">Gamma</div><div class="metric-value" style="color: #a855f7;">{s['gamma']}</div></div>
                    <div><div class="metric-label">Lots</div><div class="metric-value" style="color: white;">{lots}</div></div>
                </div>
                <div style="background: #0f172a; margin-top: 15px; padding: 10px; border-radius: 8px; display: flex; justify-content: space-around; text-align: center;">
                    <div><small style="color:#64748b">EXIT AT</small><br><b style="color:#22c55e">₹{exit_px:.2f}</b></div>
                    <div><small style="color:#64748b">POTENTIAL PROFIT</small><br><b>₹{int(profit)}</b></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
else:
    st.info("Tap 'Refresh' to fetch live Nifty data.")

st.caption(f"Calculated Expiry: {get_current_expiry()} | Powered by Upstox V3")
