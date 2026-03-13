import streamlit as st
import upstox_client
import urllib.parse
from upstox_client.rest import ApiException

# 1. UI Configuration
st.set_page_config(page_title="Nifty Live Alpha", layout="centered")

# Custom CSS for Professional Mobile-Friendly UI
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    /* Custom Styling for the Spot Price Metric Container */
    [data-testid="stMetric"] {
        background-color: #1e293b;
        padding: 20px;
        border-radius: 15px;
        border: 1px solid #334155;
        margin-bottom: 25px;
    }
    .card { background: rgba(30, 41, 59, 0.7); padding: 15px; border-radius: 12px; border-left: 5px solid #22c55e; margin-bottom: 15px; }
    .put-card { border-left: 5px solid #ef4444; }
    .metric-label { color: #94a3b8; font-size: 0.7rem; text-transform: uppercase; }
    .metric-value { color: #3b82f6; font-weight: bold; font-size: 1rem; }
    </style>
    """, unsafe_allow_html=True)

# 2. HELPER: Fetch Nifty Spot Price
def get_nifty_spot():
    try:
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_EXTENDED_TOKEN"]
        api_instance = upstox_client.MarketQuoteApi(upstox_client.ApiClient(config))
        
        # 'NSE_INDEX|Nifty 50' is the standard instrument key for spot
        response = api_instance.get_full_market_quote(st.secrets["SYMBOL"], '2.0')
        
        if response and response.data:
            quote = response.data[st.secrets["SYMBOL"]]
            ltp = quote.last_price
            prev_close = quote.close
            change = ltp - prev_close
            change_pct = (change / prev_close) * 100
            return ltp, change, change_pct
    except Exception:
        return None, None, None

# 3. HELPER: Fetch Option Chain
def fetch_option_chain():
    try:
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_EXTENDED_TOKEN"]
        options_api = upstox_client.OptionsApi(upstox_client.ApiClient(config))
        
        response = options_api.get_put_call_option_chain(
            instrument_key=st.secrets["SYMBOL"], 
            expiry_date=st.secrets["EXPIRY"]
        )
        
        processed = []
        if response and response.data:
            for row in response.data:
                for side in ['call_options', 'put_options']:
                    opt = getattr(row, side, None)
                    if opt:
                        market = getattr(opt, 'market_data', None)
                        greeks = getattr(opt, 'option_greeks', None)
                        processed.append({
                            "type": "CE" if side == 'call_options' else "PE",
                            "strike": getattr(opt, 'trading_symbol', 'N/A'),
                            "ltp": getattr(market, 'ltp', 0.0),
                            "oi_chg": f"{getattr(market, 'oi_change_percentage', 0.0):.1f}%",
                            "gamma": f"{getattr(greeks, 'gamma', 0.0):.4f}",
                            "iv": round(getattr(greeks, 'iv', 0.0), 2)
                        })
        return processed
    except Exception as e:
        st.error(f"Chain Error: {str(e)}")
        return []

# 4. MAIN UI EXECUTION
st.title("🎯 Options Momentum")

# Fetch Spot Price First
spot_ltp, spot_change, spot_pct = get_nifty_spot()

# Integrated Spot Display
if spot_ltp:
    st.metric(
        label="NIFTY 50 LIVE SPOT", 
        value=f"₹{spot_ltp:,.2f}", 
        delta=f"{spot_change:+.2f} ({spot_pct:+.2f}%)"
    )
else:
    st.error("Could not fetch Nifty Spot price. Check your API Token.")

# Trading Controls
capital = st.number_input("Trading Capital (₹)", value=50000, step=5000)
target_pct = st.number_input("Target Return %", value=20, step=5)

if st.button('🔄 Refresh Live Data'):
    signals = fetch_option_chain()
    
    if not signals:
        st.warning(f"No chain data for {st.secrets['EXPIRY']}. Token might be expired.")
    else:
        for s in signals[:10]:
            is_call = s['type'] == "CE"
            color = "#22c55e" if is_call else "#ef4444"
            lot_size = 75 # Standard Nifty Lot Size
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
else:
    st.info(f"Press Refresh to sync current strikes for {st.secrets['EXPIRY']}.")

st.caption("Data source: Upstox API v2 [MarketQuoteApi & OptionsApi]")
