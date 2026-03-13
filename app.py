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
    .stMetric { background-color: #1e293b; padding: 15px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #334155; }
    .card { background: rgba(30, 41, 59, 0.7); padding: 15px; border-radius: 12px; border-left: 5px solid #22c55e; margin-bottom: 15px; }
    .put-card { border-left: 5px solid #ef4444; }
    .metric-label { color: #94a3b8; font-size: 0.7rem; text-transform: uppercase; }
    .metric-value { color: #3b82f6; font-weight: bold; font-size: 1rem; }
    </style>
    """, unsafe_allow_html=True)

# 2. Login Section
login_url = (
    f"https://api.upstox.com?"
    f"client_id={st.secrets['UPSTOX_CLIENT_ID']}&redirect_uri={urllib.parse.quote(st.secrets['UPSTOX_REDIRECT_URI'])}"
)
st.link_button("🔑 Login to Upstox", login_url)

# 3. Fetch Spot Price & Change
def get_market_quote():
    try:
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_EXTENDED_TOKEN"]
        api_instance = upstox_client.MarketQuoteApi(upstox_client.ApiClient(config))
        
        # Fetching Full Quote for Nifty Index
        quote_response = api_instance.get_full_market_quote(st.secrets["SYMBOL"], '2.0')
        
        if quote_response and quote_response.data:
            data = quote_response.data[st.secrets["SYMBOL"]]
            current_price = data.last_price
            close_price = data.close
            change = current_price - close_price
            return current_price, change
        return None, None
    except Exception:
        return None, None

# 4. Fetch Option Chain Data
def fetch_upstox_data():
    try:
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_EXTENDED_TOKEN"]
        options_api = upstox_client.OptionsApi(upstox_client.ApiClient(config))
        
        response = options_api.get_put_call_option_chain(
            instrument_key=st.secrets["SYMBOL"], 
            expiry_date=st.secrets["EXPIRY"]
        )
        
        processed_signals = []
        if response and response.data:
            for strike_row in response.data:
                for side in ['call_options', 'put_options']:
                    opt = getattr(strike_row, side, None)
                    if opt:
                        symbol = getattr(opt, 'trading_symbol', getattr(opt, 'instrument_key', "N/A"))
                        market = getattr(opt, 'market_data', None)
                        greeks = getattr(opt, 'option_greeks', None)
                        processed_signals.append({
                            "type": "CE" if side == 'call_options' else "PE",
                            "strike": symbol,
                            "ltp": getattr(market, 'ltp', 0.0) if market else 0.0,
                            "oi_chg": f"{getattr(market, 'oi_change_percentage', 0.0):.1f}%",
                            "gamma": f"{getattr(greeks, 'gamma', 0.0):.4f}",
                            "iv": round(getattr(greeks, 'iv', 0.0), 2)
                        })
        return processed_signals
    except Exception as e:
        st.error(f"⚠️ Chain Fetch Error: {str(e)}")
        return []

# 5. UI Layout
st.title("🎯 Options Momentum")

# Display Spot Price Metric
spot, diff = get_market_quote()
if spot:
    st.metric(label="NIFTY 50 SPOT", value=f"₹{spot:,.2f}", delta=f"{diff:,.2f} ({ (diff/ (spot-diff))*100 :.2f}%)")

capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
target_pct = st.number_input("Target Return %", value=20, step=5)

if st.button('🔄 Refresh Live Data'):
    signals = fetch_upstox_data()
    if not signals:
        st.warning("No data found. Check Token or Expiry.")
    else:
        for s in signals[:10]:
            is_call = s['type'] == "CE"
            color = "#22c55e" if is_call else "#ef4444"
            lot_size = 75 
            exit_price = s['ltp'] * (1 + (target_pct / 100))
            max_lots = int(capital // (s['ltp'] * lot_size)) if s['ltp'] > 0 else 0
            
            st.markdown(f"""
            <div class="card {'put-card' if not is_call else ''}">
                <div style="display: flex; justify-content: space-between;">
                    <b style="color: {color};">{s['strike']}</b>
                    <b style="color: white;">₹{s['ltp']}</b>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; margin-top: 10px; text-align: center;">
                    <div><div class="metric-label">OI Chg</div><div class="metric-value">{s['oi_chg']}</div></div>
                    <div><div class="metric-label">IV</div><div class="metric-value">{s['iv']}</div></div>
                    <div><div class="metric-label">Gamma</div><div class="metric-value">{s['gamma']}</div></div>
                </div>
                <div style="background: #0f172a; margin-top: 10px; padding: 8px; border-radius: 8px; display: grid; grid-template-columns: 1fr 1fr 1fr; text-align: center;">
                    <div><small>LOTS</small><br><b>{max_lots}</b></div>
                    <div><small>EXIT</small><br><b style="color:#22c55e">{exit_price:.2f}</b></div>
                    <div><small>PROFIT</small><br><b>₹{int((exit_price-s['ltp'])*max_lots*lot_size) if max_lots > 0 else 0}</b></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
