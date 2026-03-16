import streamlit as st
import pandas as pd
import upstox_client
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. UI SETUP ---
st.set_page_config(page_title="Price Action & OI Radar", layout="centered")

# --- 2. AUTO-REFRESH (Every 60 Seconds) ---
st_autorefresh(interval=60 * 1000, key="radar_refresh")

# --- 3. SESSION STATE INITIALIZATION ---
if "oi_snapshots" not in st.session_state:
    st.session_state.oi_snapshots = {}          # { ikey: {"baseline_oi": x, "prev_oi": x, "time": t} }
if "surge_history" not in st.session_state:
    st.session_state.surge_history = []         # list of {"time": t, "strike": s, "surge": v}
if "prev_trend" not in st.session_state:
    st.session_state.prev_trend = None


# --- API HELPERS ---
def get_api_client():
    token = st.secrets.get("UPSTOX_ACCESS_TOKEN", "")
    if not token:
        st.error("⚠️ UPSTOX_ACCESS_TOKEN is missing from Streamlit secrets.")
        st.stop()
    config = upstox_client.Configuration()
    config.access_token = token
    return upstox_client.ApiClient(config)


def safe_get_instrument(data_dict, key):
    alt_key = key.replace('|', ':')
    return data_dict.get(key) or data_dict.get(alt_key)


def get_market_data(index_key):
    """Fetch spot price + intraday OHLC for a proper VWAP approximation."""
    try:
        api = upstox_client.MarketQuoteV3Api(get_api_client())
        ltp_resp = api.get_ltp(instrument_key=index_key)
        ohlc_resp = api.get_market_quote_ohlc(instrument_key=index_key, interval="1d")

        spot_obj = safe_get_instrument(ltp_resp.data, index_key)
        spot = spot_obj.last_price if spot_obj else 0.0

        ohlc_obj = safe_get_instrument(ohlc_resp.data, index_key)
        vwap_val, day_high, day_low = spot, spot, spot

        if ohlc_obj and hasattr(ohlc_obj, 'ohlc'):
            prices = ohlc_obj.ohlc
            # Improved VWAP: weighted toward close (close counts double)
            vwap_val = (prices.high + prices.low + prices.close * 2) / 4
            day_high = prices.high
            day_low = prices.low

        return spot, vwap_val, day_high, day_low
    except Exception as e:
        st.error(f"Market Data Error: {e}")
        return 0.0, 0.0, 0.0, 0.0


@st.cache_data(ttl=3600)
def get_expiry_list(index_key):
    try:
        api = upstox_client.OptionsApi(get_api_client())
        contracts = api.get_option_contracts(index_key)
        today = datetime.now().strftime('%Y-%m-%d')
        return sorted(list(set(c.expiry for c in contracts.data if c.expiry >= today)))
    except:
        return []


def fetch_option_chain(index_key, expiry):
    """Fetch option chain for a given expiry. Returns list of option chain items."""
    try:
        api = upstox_client.OptionsApi(get_api_client())
        resp = api.get_put_call_option_chain(instrument_key=index_key, expiry_date=expiry)
        return resp.data if resp and resp.data else []
    except Exception as e:
        st.error(f"Option Chain Error ({expiry}): {e}")
        return []


# --- STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

    html, body, .main { background-color: #080c14 !important; font-family: 'IBM Plex Sans', sans-serif; }

    .card {
        background: rgba(15, 23, 42, 0.85);
        padding: 20px;
        border-radius: 12px;
        border-left: 4px solid #3b82f6;
        margin-bottom: 18px;
        backdrop-filter: blur(6px);
    }
    .uptrend-bg  { background: linear-gradient(120deg, #052e16 0%, #080c14 60%); border: 1px solid #16a34a; }
    .downtrend-bg{ background: linear-gradient(120deg, #3f0d0d 0%, #080c14 60%); border: 1px solid #dc2626; }
    .sideways-bg { background: #0f172a; border: 1px solid #334155; }

    .metric-label { color: #64748b; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 4px; font-family: 'IBM Plex Mono', monospace; }
    .sr-badge { display:inline-block; padding:4px 10px; border-radius:6px; font-size:0.75rem; font-family:'IBM Plex Mono',monospace; font-weight:600; margin:2px 4px; }
    .tag-support    { background:#052e16; color:#4ade80; border:1px solid #16a34a; }
    .tag-resistance { background:#3f0d0d; color:#f87171; border:1px solid #dc2626; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏹 Price Action & Sentiment Radar")

index_map = {
    "Nifty 50":   "NSE_INDEX|Nifty 50",
    "Nifty Bank":  "NSE_INDEX|Nifty Bank",
    "FINNIFTY":    "NSE_INDEX|Nifty Fin Service"
}
index_choice = st.selectbox("Select Index", list(index_map.keys()))
selected_key = index_map[index_choice]

# Fetch Market Data
spot_price, vwap_price, d_high, d_low = get_market_data(selected_key)
expiry_list = get_expiry_list(selected_key)

# --- INITIALIZE DEFAULTS ---
trend_status = "INITIALIZING"
trend_class  = "sideways-bg"
trend_color  = "#94a3b8"
total_ce_oi, total_pe_oi = 0, 0
pcr_near, pcr_far = 0.0, 0.0
best_trade   = None
support_strike, resistance_strike = None, None
iv_info = {}

# --- CORE LOGIC ---
if expiry_list and spot_price > 0:
    try:
        # ── Nearest expiry chain (for OI surge & momentum pick) ──
        near_expiry = expiry_list[0]
        near_chain  = fetch_option_chain(selected_key, near_expiry)

        # ── Far expiry chain (monthly, for multi-expiry PCR) ──
        # Pick the expiry that is ~4 weeks out if available, else last available
        far_expiry  = expiry_list[min(3, len(expiry_list) - 1)]
        far_chain   = fetch_option_chain(selected_key, far_expiry) if far_expiry != near_expiry else []

        # ── 1. Aggregate OI ──
        far_ce_oi, far_pe_oi = 0, 0
        for item in near_chain:
            if item.call_options: total_ce_oi += item.call_options.market_data.oi
            if item.put_options:  total_pe_oi += item.put_options.market_data.oi
        for item in far_chain:
            if item.call_options: far_ce_oi += item.call_options.market_data.oi
            if item.put_options:  far_pe_oi += item.put_options.market_data.oi

        pcr_near = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0
        pcr_far  = far_pe_oi   / far_ce_oi   if far_ce_oi   > 0 else 0

        # ── 2. Trend Determination with PCR band (0.8–1.2 = sideways zone) ──
        is_bullish = (spot_price > vwap_price) and (pcr_near > 1.2)
        is_bearish = (spot_price < vwap_price) and (pcr_near < 0.8)

        trend_status = "UPTREND" if is_bullish else "DOWNTREND" if is_bearish else "SIDEWAYS"
        trend_class  = "uptrend-bg"   if is_bullish else "downtrend-bg" if is_bearish else "sideways-bg"
        trend_color  = "#22c55e"      if is_bullish else "#ef4444"      if is_bearish else "#94a3b8"

        # ── Toast alert on trend change ──
        if st.session_state.prev_trend and st.session_state.prev_trend != trend_status:
            st.toast(f"⚡ Trend flipped: {st.session_state.prev_trend} → {trend_status}", icon="🔔")
        st.session_state.prev_trend = trend_status

        # ── 3. Support & Resistance from Max OI strikes ──
        valid_ce = [i for i in near_chain if i.call_options and i.call_options.market_data.oi > 0]
        valid_pe = [i for i in near_chain if i.put_options  and i.put_options.market_data.oi  > 0]
        if valid_ce:
            resistance_strike = max(valid_ce, key=lambda x: x.call_options.market_data.oi).strike_price
        if valid_pe:
            support_strike    = max(valid_pe, key=lambda x: x.put_options.market_data.oi).strike_price

        # ── 4. Momentum Trade Pick with OI surge + IV filter ──
        trade_side = "CALL" if is_bullish or (not is_bearish and spot_price > vwap_price) else "PUT"
        atm_strikes = sorted(near_chain, key=lambda x: abs(x.strike_price - spot_price))[:5]
        options_pool = []

        for item in atm_strikes:
            opt_data = item.call_options if trade_side == "CALL" else item.put_options
            if not opt_data:
                continue

            ikey     = opt_data.instrument_key
            curr_oi  = opt_data.market_data.oi
            curr_iv  = getattr(opt_data.market_data, 'iv', None) or getattr(opt_data, 'greeks', None)

            # Try to extract IV from greeks if available
            iv_val = None
            if hasattr(opt_data, 'greeks') and opt_data.greeks:
                iv_val = getattr(opt_data.greeks, 'iv', None)
            if iv_val is None and hasattr(opt_data.market_data, 'iv'):
                iv_val = opt_data.market_data.iv

            # ── Baseline OI: stored once per session start, never overwritten ──
            if ikey not in st.session_state.oi_snapshots:
                st.session_state.oi_snapshots[ikey] = {
                    "baseline_oi": curr_oi,
                    "prev_oi":     curr_oi,
                    "time":        datetime.now()
                }

            snap         = st.session_state.oi_snapshots[ikey]
            baseline_oi  = snap["baseline_oi"]

            # Surge vs session baseline (never resets until app restart)
            surge_session = ((curr_oi - baseline_oi) / baseline_oi * 100) if baseline_oi > 0 else 0
            # Surge vs last 60s snapshot
            surge_tick    = ((curr_oi - snap["prev_oi"]) / snap["prev_oi"] * 100) if snap["prev_oi"] > 0 else 0

            # Update prev_oi for next tick
            st.session_state.oi_snapshots[ikey]["prev_oi"] = curr_oi

            options_pool.append({
                "strike":         f"{item.strike_price} {'CE' if trade_side == 'CALL' else 'PE'}",
                "strike_price":   item.strike_price,
                "ltp":            opt_data.market_data.ltp,
                "surge_session":  surge_session,
                "surge_tick":     surge_tick,
                "iv":             round(iv_val, 1) if iv_val else None,
                "time":           round((datetime.now() - snap["time"]).total_seconds() / 60, 1)
            })

        if options_pool:
            # Filter out high-IV outliers (>1.5x median IV) if IV data available
            iv_vals = [o["iv"] for o in options_pool if o["iv"] is not None]
            if len(iv_vals) >= 2:
                median_iv = sorted(iv_vals)[len(iv_vals) // 2]
                options_pool = [o for o in options_pool if o["iv"] is None or o["iv"] <= median_iv * 1.5]

            # Rank by session-level OI surge
            best_trade = max(options_pool, key=lambda x: x['surge_session'])

            # ── 5. Rolling surge history (keep last 20 entries) ──
            st.session_state.surge_history.append({
                "time":   datetime.now().strftime("%H:%M"),
                "strike": best_trade["strike"],
                "surge":  round(best_trade["surge_session"], 2)
            })
            if len(st.session_state.surge_history) > 20:
                st.session_state.surge_history = st.session_state.surge_history[-20:]

    except Exception as e:
        st.error(f"Logic Error: {e}")


# ═══════════════════════════════════════════════════════
#  UI
# ═══════════════════════════════════════════════════════

# ── Overall Trend ──
st.markdown(f"""
    <div class="{trend_class}" style="padding:22px; border-radius:14px; text-align:center; margin-bottom:22px;">
        <div style="color:white; font-size:0.72rem; letter-spacing:4px; font-weight:600; opacity:0.6; font-family:'IBM Plex Mono',monospace;">MARKET STRUCTURE</div>
        <div style="color:{trend_color}; font-size:2.8rem; font-weight:900; margin:10px 0; font-family:'IBM Plex Mono',monospace;">{trend_status}</div>
        <div style="color:#94a3b8; font-size:0.78rem; font-family:'IBM Plex Mono',monospace;">
            Price vs VWAP: {'▲ ABOVE' if spot_price > vwap_price else '▼ BELOW'} &nbsp;|&nbsp;
            PCR (Near): {pcr_near:.2f} &nbsp;|&nbsp;
            PCR (Far): {pcr_far:.2f}
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Metrics Row ──
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("LIVE SPOT",   f"₹{spot_price:,.2f}", f"{spot_price - vwap_price:+.2f} vs VWAP")
with col2:
    st.metric("PCR (NEAR)",  f"{pcr_near:.2f}", "Bullish" if pcr_near > 1.2 else "Bearish" if pcr_near < 0.8 else "Neutral")
with col3:
    st.metric("PCR (FAR)",   f"{pcr_far:.2f}",  "Bullish" if pcr_far  > 1.2 else "Bearish" if pcr_far  < 0.8 else "Neutral")
with col4:
    st.metric("DAY RANGE",   f"₹{d_high:,.0f}", f"Low: ₹{d_low:,.0f}", delta_color="off")

# ── Support & Resistance ──
if support_strike or resistance_strike:
    st.markdown("##### Key S/R Levels (Max OI)")
    sr_html = ""
    if support_strike:
        dist_s = spot_price - support_strike
        sr_html += f'<span class="sr-badge tag-support">🟢 Support: {support_strike:,.0f} ({dist_s:+.0f})</span>'
    if resistance_strike:
        dist_r = resistance_strike - spot_price
        sr_html += f'<span class="sr-badge tag-resistance">🔴 Resistance: {resistance_strike:,.0f} ({dist_r:+.0f})</span>'
    st.markdown(sr_html, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

# ── Trade Pick Card ──
if best_trade:
    s = best_trade
    iv_display = f"{s['iv']}%" if s['iv'] else "N/A"
    st.markdown(f"""
    <div class="card" style="border-left-color:{trend_color};">
        <div style="display:flex; justify-content:space-between; align-items:start;">
            <div>
                <div class="metric-label">MOMENTUM PICK</div>
                <h1 style="color:{trend_color}; margin:0; font-family:'IBM Plex Mono',monospace;">{s['strike']}</h1>
            </div>
            <div style="text-align:right;">
                <div class="metric-label">LTP</div>
                <div style="font-size:1.5rem; color:white; font-weight:bold; font-family:'IBM Plex Mono',monospace;">₹{s['ltp']}</div>
            </div>
        </div>
        <div style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:12px; margin-top:18px;">
            <div style="background:#070d1a; padding:14px; border-radius:10px; text-align:center;">
                <div class="metric-label">SESSION SURGE</div>
                <div style="color:#eab308; font-weight:700; font-size:1.2rem; font-family:'IBM Plex Mono',monospace;">{s['surge_session']:+.2f}%</div>
            </div>
            <div style="background:#070d1a; padding:14px; border-radius:10px; text-align:center;">
                <div class="metric-label">60s SURGE</div>
                <div style="color:#f97316; font-weight:700; font-size:1.2rem; font-family:'IBM Plex Mono',monospace;">{s['surge_tick']:+.2f}%</div>
            </div>
            <div style="background:#070d1a; padding:14px; border-radius:10px; text-align:center;">
                <div class="metric-label">IV</div>
                <div style="color:#a78bfa; font-weight:700; font-size:1.2rem; font-family:'IBM Plex Mono',monospace;">{iv_display}</div>
            </div>
            <div style="background:#070d1a; padding:14px; border-radius:10px; text-align:center;">
                <div class="metric-label">SNAP AGE</div>
                <div style="color:white; font-weight:700; font-size:1.2rem; font-family:'IBM Plex Mono',monospace;">{s['time']}m</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.info("Gathering live data... Wait for the next 60s cycle to calculate OI surge.")

# ── OI Surge History Chart ──
if st.session_state.surge_history:
    st.markdown("##### 📈 OI Surge History (Session)")
    df_hist = pd.DataFrame(st.session_state.surge_history)
    st.line_chart(df_hist.set_index("time")["surge"], use_container_width=True, height=160)

# ── Footer ──
st.caption(
    f"Last Sync: {datetime.now().strftime('%H:%M:%S')} | "
    f"VWAP: ₹{vwap_price:,.2f} | "
    f"Logic: PCR Band (0.8/1.2) + Weighted VWAP + Max-OI S/R + IV Filter"
)
