import streamlit as st
import upstox_client
import urllib.parse
from upstox_client.rest import ApiException

# 1. UI Configuration
st.set_page_config(page_title="Nifty Alpha Live", layout="centered")

# Custom CSS for Professional Mobile UI
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    [data-testid="stMetric"] {
        background-color: #1e293b;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #334155;
    }
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

# 2. Login Logic
client_id = st.secrets["UPSTOX_CLIENT_ID"]
redirect_uri = st.secrets["UPSTOX_REDIRECT_URI"]
login_url = (
    f"https://api.upstox.com?"
    f"client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_uri)}"
)
st.link_button("🔑 Login to Upstox", login_url)

# 3. Fetch Spot Price & Daily Change
def get_nifty_spot():
    try:
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_EXTENDED_TOKEN"]
        api_instance = upstox_client.MarketQuoteApi(upstox_client.ApiClient(config))
        
        # Fetching Full Quote for Nifty Index
        response = api_instance.get_full_market_quote(st.secrets["SYMBOL"], '2.0')
        
        if response and response.data:
            data = response.data[st.secrets["SYMBOL"]]
            ltp = data.last_price
            prev_close = data.close
            change = ltp - prev_close
            pct_change = (change / prev_close) * 100
            return ltp, change, pct_change
        return None, None, None
    except Exception:
        return None, None, None

# 4. Fetch Option Chain Data (Fixed Attribute Errors)
def fetch_option_chain():
    try:
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_EXTENDED_TOKEN"]
        options_api = upstox_client.OptionsApi(upstox_client.ApiClient(config))
        
        response = options_api.get_put_call_option_chain(
            instrument_key=st.secrets["SYMBOL"], 
            expiry_date=st.secrets["EXPIRY"]
        )
        
        processed_signals = []
        if response and hasattr(response, 'data') and response.data:
            for strike_row in response.data:
                # Check both Call (CE) and Put (PE) in the strike row
                for side in ['call_options', 'put_options']:
                    opt_data = getattr(strike_row, side, None)
                    
                    if opt_data:
                        # Access nested market data and greeks
                        market = getattr(opt_data, 'market_data', None)
                        greeks = getattr(opt_data, 'option_greeks', None)
                        
                        processed_signals.append({
                            "type": "CE" if side == 'call_options' else "PE",
                            "strike": getattr(opt_data, 'trading_symbol', 'N/A'),
                            "ltp": getattr(market, 'ltp', 0.0),
                            "oi_chg": f"{getattr(market, 'oi_change_percentage', 0.0):.1f}%",
                            "gamma": f"{getattr(greeks, 'gamma', 0.0):.4f}",
                            "iv": round(getattr(greeks, 'iv', 0.0), 2)
                        })
        return processed_signals
    except Exception as e:
        st.error(f"⚠️ Chain Fetch Error: {str(e)}")
        return []

# 5. UI Layout Execution
st.title("🎯 Options Momentum")

# Display Integrated Spot Price at the top
spot_price, diff, diff_pct = get_nifty_spot()
if spot_price:
    st.metric(
        label="NIFTY 50 LIVE SPOT", 
        value=f"₹{spot_price:,.2f}", 
        delta=f"{diff:+.2f} ({diff_pct:+.2f}%)"
    )
else:
    st.warning("Spot price currently unavailable. Check your API Token.")

# User Inputs
capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
target_pct = st.number_input("Target Return %", value=20, step=5)

if st.button('🔄 Refresh Live Data'):
    with st.spinner("Fetching data..."):
        signals = fetch_option_chain()
    
    if not signals:
        st.error(f"No chain data for {st.secrets['EXPIRY']}. Is the token expired?")
    else:
        # Show top 10 contracts
        for s in signals[:10]:
            is_call = s['type'] == "CE"
            color = "#22c55e" if is_call else "#ef4444"
            
            # Calculations (Nifty Lot Size = 75)
            lot_size = 75 
            exit_price = s['ltp'] * (1 + (target_pct / 100))
            max_lots = int(capital // (s['ltp'] * lot_size)) if s['ltp'] > 0 else 0
            est_profit = (exit_price - s['ltp']) * (max_lots * lot_size)
            
            st.markdown(f"""
            <div class="card {'put-card' if not is_call else ''}">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <b style="color: {color}; font-size: 1rem;">{s['strike']}</b>
                    <b style="color: white; font-family: monospace;">₹{s['ltp']}</b>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; margin-top: 10px; text-align: center;">
                    <div><div class="metric-label">OI Chg</div><div class="metric-value">{s['oi_chg']}</div></div>
                    <div><div class="metric-label">IV</div><div class="metric-value" style="color: #eab308;">{s['iv']}</div></div>
                    <div><div class="metric-label">Gamma</div><div class="metric-value" style="color: #a855f7;">{s['gamma']}</div></div>
                </div>
                <div style="background: #0f172a; margin-top: 10px; padding: 10px; border-radius: 8px; display: grid; grid-template-columns: 1fr 1fr 1fr; text-align: center;">
                    <div><small style="color:#64748b">LOTS</small><br><b>{max_lots}</b></div>
                    <div><small style="color:#64748b">EXIT @</small><br><b style="color:#22c55e">{exit_price:.2f}</b></div>
                    <div><small style="color:#64748b">PROFIT</small><br><b>₹{int(est_profit)}</b></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
else:
    st.info(f"Press Refresh to sync data for {st.secrets['EXPIRY']}.")

st.caption("Data source: Upstox API v2 [MarketQuoteApi & OptionsApi]")
