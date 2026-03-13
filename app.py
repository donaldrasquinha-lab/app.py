import streamlit as st
import upstox_client
import urllib.parse
from datetime import datetime, timedelta
from upstox_client.rest import ApiException

# 1. UI SETUP
st.set_page_config(page_title="Nifty Live Alpha", layout="centered")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    [data-testid="stMetric"] { background-color: #1e293b; padding: 15px; border-radius: 12px; border: 1px solid #334155; }
    .card { background: rgba(30, 41, 59, 0.7); padding: 15px; border-radius: 12px; border-left: 5px solid #22c55e; margin-bottom: 15px; }
    .put-card { border-left: 5px solid #ef4444; }
    </style>
    """, unsafe_allow_html=True)

# 2. HELPER: Calculate Next Tuesday Expiry
def get_upcoming_expiry():
    today = datetime.now()
    # Nifty Weekly Expiry is Tuesday (Weekday 1)
    days_ahead = (1 - today.weekday() + 7) % 7
    if days_ahead == 0 and today.hour >= 15: # After market close, move to next week
        days_ahead = 7
    return (today + timedelta(days_ahead)).strftime("%Y-%m-%d")

# 3. FETCH DATA (Integrated Fix for Token/Resource Error)
def get_live_data():
    try:
        config = upstox_client.Configuration()
        config.access_token = st.secrets["UPSTOX_EXTENDED_TOKEN"]
        api_client = upstox_client.ApiClient(config)
        
        # A. Fetch Spot Price
        quote_api = upstox_client.MarketQuoteApi(api_client)
        quote_res = quote_api.get_full_market_quote("NSE_INDEX|Nifty 50", '2.0')
        
        # B. Fetch Option Chain
        options_api = upstox_client.OptionsApi(api_client)
        current_expiry = get_upcoming_expiry()
        chain_res = options_api.get_put_call_option_chain("NSE_INDEX|Nifty 50", current_expiry)
        
        return quote_res, chain_res, current_expiry
    except Exception as e:
        if "401" in str(e) or "UDAPI100060" in str(e):
            st.error("🔑 **Token Expired or Invalid.** Please regenerate UPSTOX_EXTENDED_TOKEN in secrets.")
        else:
            st.error(f"⚠️ Error: {str(e)}")
        return None, None, None

# 4. MAIN UI
st.title("🎯 Options Momentum")

# Login Link
login_url = f"https://api.upstox.com{st.secrets['UPSTOX_CLIENT_ID']}&redirect_uri={urllib.parse.quote(st.secrets['UPSTOX_REDIRECT_URI'])}"
st.link_button("🔑 Login to Upstox", login_url)

if st.button('🔄 Refresh Live Data'):
    quote, chain, expiry = get_live_data()
    
    if quote and "NSE_INDEX|Nifty 50" in quote.data:
        data = quote.data["NSE_INDEX|Nifty 50"]
        st.metric("NIFTY 50 SPOT", f"₹{data.last_price:,.2f}", f"{data.last_price - data.close:+.2f}")
        
        st.write(f"### Options Chain for Expiry: {expiry}")
        if chain and chain.data:
            for row in chain.data[:8]:
                for side in ['call_options', 'put_options']:
                    opt = getattr(row, side, None)
                    if opt:
                        market = getattr(opt, 'market_data', None)
                        st.markdown(f"""
                        <div class="card {'put-card' if side=='put_options' else ''}">
                            <div style="display: flex; justify-content: space-between;">
                                <b>{opt.trading_symbol}</b>
                                <b>₹{market.ltp if market else 0}</b>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
