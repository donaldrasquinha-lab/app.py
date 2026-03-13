import streamlit as st
import upstox_client
import urllib.parse
from upstox_client.rest import ApiException

# 1. UI SETUP
st.set_page_config(page_title="Nifty Live Momentum", layout="centered")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    [data-testid="stMetric"] { background-color: #1e293b; padding: 20px; border-radius: 15px; border: 1px solid #334155; margin-bottom: 20px; }
    .card { background: rgba(30, 41, 59, 0.7); padding: 15px; border-radius: 12px; border-left: 5px solid #22c55e; margin-bottom: 15px; }
    .put-card { border-left: 5px solid #ef4444; }
    .metric-label { color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; }
    .metric-value { color: #3b82f6; font-weight: bold; font-size: 1.1rem; }
    </style>
    """, unsafe_allow_html=True)

# 2. LOGIN URL (Verify Redirect URI in Upstox Dashboard matches this exactly)
login_url = (
    f"https://api.upstox.com?"
    f"client_id={st.secrets['UPSTOX_CLIENT_ID']}&redirect_uri={urllib.parse.quote(st.secrets['UPSTOX_REDIRECT_URI'])}"
)
st.link_button("🔑 Login to Upstox", login_url)

# 3. HELPER: FETCH NIFTY SPOT
def get_nifty_spot(api_client):
    try:
        quote_api = upstox_client.MarketQuoteApi(api_client)
        # Using '2.0' as required for Full Market Quotes
        response = quote_api.get_full_market_quote(st.secrets["SYMBOL"], '2.0')
        if response and response.data:
            data = response.data[st.secrets["SYMBOL"]]
            return data.last_price, (data.last_price - data.close), ((data.last_price - data.close)/data.close)*100
        return None, None, None
    except Exception:
        return None, None, None

# 4. HELPER: FETCH OPTION CHAIN
def fetch_options(api_client):
    try:
        options_api = upstox_client.OptionsApi(api_client)
        # Verify EXPIRY in secrets is "YYYY-MM-DD"
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
                        mkt = getattr(opt, 'market_data', None)
                        greeks = getattr(opt, 'option_greeks', None)
                        processed.append({
                            "type": "CE" if side == 'call_options' else "PE",
                            "strike": getattr(opt, 'trading_symbol', 'N/A'),
                            "ltp": getattr(mkt, 'ltp', 0.0),
                            "oi_chg": f"{getattr(mkt, 'oi_change_percentage', 0.0):.1f}%",
                            "iv": round(getattr(greeks, 'iv', 0.0), 2) if greeks else 0.0,
                            "gamma": f"{getattr(greeks, 'gamma', 0.0):.4f}" if greeks else "0.0000"
                        })
        return processed
    except ApiException as e:
        st.error(f"API Error: {e.body}") # Detailed error from Upstox
        return []

# 5. MAIN PAGE EXECUTION
st.title("🎯 Options Momentum")

# Setup Client
conf = upstox_client.Configuration()
conf.access_token = st.secrets["UPSTOX_EXTENDED_TOKEN"]
client = upstox_client.ApiClient(conf)

# Show Spot Price Metric
ltp, diff, pct = get_nifty_spot(client)
if ltp:
    st.metric("NIFTY 50 LIVE SPOT", f"₹{ltp:,.2f}", f"{diff:+.2f} ({pct:+.2f}%)")
else:
    st.error("⚠️ Token Expired or Invalid Symbol. Please update UPSTOX_EXTENDED_TOKEN.")

# Refresh Logic
if st.button('🔄 Refresh Live Chain'):
    signals = fetch_options(client)
    if not signals:
        st.warning(f"No chain data for {st.secrets['EXPIRY']}. Is it a valid trading day?")
    else:
        for s in signals[:10]:
            is_call = s['type'] == "CE"
            color = "#22c55e" if is_call else "#ef4444"
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
            </div>
            """, unsafe_allow_html=True)
