import streamlit as st
import pandas as pd
import upstox_client
import pytz
from datetime import datetime, time as dtime
from streamlit_autorefresh import st_autorefresh

# --- 1. UI SETUP ---
st.set_page_config(page_title="Price Action & OI Radar", layout="centered")

# --- 2. AUTO-REFRESH (Every 60 Seconds) ---
st_autorefresh(interval=60 * 1000, key="radar_refresh")

# --- 3. SESSION STATE INITIALIZATION ---
if "oi_snapshots"  not in st.session_state: st.session_state.oi_snapshots  = {}
if "surge_history" not in st.session_state: st.session_state.surge_history = []
if "prev_trend"    not in st.session_state: st.session_state.prev_trend    = None
# ── Last-known-good cache: persists across after-hours refreshes ──
if "last_cache"    not in st.session_state: st.session_state.last_cache    = {}


# ─────────────────────────────────────────────
#  MARKET HOURS  (NSE: 09:15 – 15:30 IST)
# ─────────────────────────────────────────────
IST          = pytz.timezone("Asia/Kolkata")
MARKET_OPEN  = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)

def is_market_open() -> bool:
    return MARKET_OPEN <= datetime.now(IST).time() <= MARKET_CLOSE

def market_status_label() -> str:
    t = datetime.now(IST).time()
    if t < MARKET_OPEN:  return "PRE-MARKET  (opens 09:15 IST)"
    if t > MARKET_CLOSE: return "MARKET CLOSED  (closed 15:30 IST)"
    return "MARKET OPEN  🟢"


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


def _safe_float(obj, *attrs):
    """Safely drill into nested attributes, return float or None."""
    for attr in attrs:
        if obj is None: return None
        obj = getattr(obj, attr, None)
    try: return float(obj) if obj is not None else None
    except: return None


def get_market_data(index_key):
    """
    Market hours        → live fetch, update cache.
    After hours + cache → return last cached values, skip API entirely.
    After hours, NO cache (first open) → fetch once to populate cache.
    On API error        → fall back to cache.
    """
    cache = st.session_state.last_cache.get(index_key)

    # Only skip API if cache is fully populated (has real OHLC, not just spot)
    if not is_market_open() and cache and cache.get("high") != cache.get("spot"):
        return cache["spot"], cache["vwap"], cache["high"], cache["low"]

    try:
        api       = upstox_client.MarketQuoteV3Api(get_api_client())
        ltp_resp  = api.get_ltp(instrument_key=index_key)
        ohlc_resp = api.get_market_quote_ohlc(instrument_key=index_key, interval="1d")

        spot_obj  = safe_get_instrument(ltp_resp.data, index_key)
        spot      = _safe_float(spot_obj, 'last_price') or 0.0

        ohlc_obj  = safe_get_instrument(ohlc_resp.data, index_key)
        vwap_val, day_high, day_low = spot, spot, spot

        # Upstox OHLC structure: ohlc_obj.ohlc.open / .high / .low / .close
        # Also handle alternate attribute names gracefully
        prices = getattr(ohlc_obj, 'ohlc', None) if ohlc_obj else None
        if prices:
            h = _safe_float(prices, 'high')
            l = _safe_float(prices, 'low')
            c = _safe_float(prices, 'close')
            if h and l and c:
                vwap_val = (h + l + c * 2) / 4
                day_high = h
                day_low  = l

        # Always overwrite cache with freshest live values
        st.session_state.last_cache[index_key] = {
            "spot": spot, "vwap": vwap_val, "high": day_high, "low": day_low,
            "as_of": datetime.now(IST).strftime("%d %b %H:%M IST")
        }
        return spot, vwap_val, day_high, day_low

    except Exception as e:
        st.error(f"Market Data Error: {e}")
        if cache:
            return cache["spot"], cache["vwap"], cache["high"], cache["low"]
        return 0.0, 0.0, 0.0, 0.0


def get_expiry_list(index_key):
    """
    Fetch expiry list. Caches in session_state so it:
      - Never caches a failed/empty result (unlike @st.cache_data)
      - Refreshes once per session when market opens
    """
    cache_key = f"expiry_{index_key}"
    cached = st.session_state.last_cache.get(cache_key)

    # Return cached list if it has entries
    if cached:
        return cached

    try:
        api       = upstox_client.OptionsApi(get_api_client())
        contracts = api.get_option_contracts(index_key)
        today     = datetime.now().strftime('%Y-%m-%d')
        result    = sorted(list(set(c.expiry for c in contracts.data if c.expiry >= today)))
        if result:  # Only cache non-empty results
            st.session_state.last_cache[cache_key] = result
        return result
    except Exception as e:
        st.error(f"Expiry List Error: {e}")
        return cached or []


def fetch_option_chain(index_key, expiry):
    """
    Market hours         → live fetch, update cache.
    After hours + cache  → return frozen close-of-day chain.
    After hours, no cache→ fetch once to populate.
    On error             → fall back to cache.
    """
    chain_key    = f"chain_{index_key}_{expiry}"
    cached_chain = st.session_state.last_cache.get(chain_key)

    # Only skip fetch if we already have a populated chain
    if not is_market_open() and cached_chain:
        return cached_chain

    try:
        api  = upstox_client.OptionsApi(get_api_client())
        resp = api.get_put_call_option_chain(instrument_key=index_key, expiry_date=expiry)
        data = resp.data if resp and resp.data else []
        if data:
            st.session_state.last_cache[chain_key] = data
        return data
    except Exception as e:
        st.error(f"Option Chain Error ({expiry}): {e}")
        return cached_chain or []


# --- STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

    html, body, .main { background-color: #080c14 !important; font-family: 'IBM Plex Sans', sans-serif; }

    /* ── Sentiment background themes ── */
    .uptrend-bg {
        background: linear-gradient(135deg, #021a0e 0%, #031f11 40%, #080c14 100%);
        border: 1px solid #16a34a;
        box-shadow: 0 0 40px rgba(34,197,94,0.12), inset 0 0 60px rgba(34,197,94,0.04);
    }
    .downtrend-bg {
        background: linear-gradient(135deg, #1a0202 0%, #1f0303 40%, #080c14 100%);
        border: 1px solid #dc2626;
        box-shadow: 0 0 40px rgba(239,68,68,0.12), inset 0 0 60px rgba(239,68,68,0.04);
    }
    .sideways-bg {
        background: linear-gradient(135deg, #0a0f1e 0%, #0f172a 100%);
        border: 1px solid #334155;
        box-shadow: 0 0 20px rgba(148,163,184,0.06);
    }

    /* ── Sentiment-tinted metric tiles ── */
    .tile-bull { background: linear-gradient(135deg, #052e16 0%, #071a0e 100%); border:1px solid #16a34a33; border-radius:10px; padding:14px; text-align:center; }
    .tile-bear { background: linear-gradient(135deg, #3f0d0d 0%, #1f0404 100%); border:1px solid #dc262633; border-radius:10px; padding:14px; text-align:center; }
    .tile-neut { background: linear-gradient(135deg, #0f172a 0%, #070d1a 100%); border:1px solid #33415540;  border-radius:10px; padding:14px; text-align:center; }

    /* ── Trade card ── */
    .card {
        padding: 20px;
        border-radius: 14px;
        border-left: 5px solid #3b82f6;
        margin-bottom: 18px;
        backdrop-filter: blur(6px);
    }
    .card-bull { background: linear-gradient(135deg, #031a0c 0%, #080c14 70%); border-left-color: #22c55e !important; box-shadow: 0 0 24px rgba(34,197,94,0.15); }
    .card-bear { background: linear-gradient(135deg, #1a0303 0%, #080c14 70%); border-left-color: #ef4444 !important; box-shadow: 0 0 24px rgba(239,68,68,0.15); }
    .card-neut { background: linear-gradient(135deg, #0a0f1e 0%, #080c14 70%); border-left-color: #94a3b8 !important; }

    /* ── S/R badges ── */
    .sr-badge { display:inline-block; padding:5px 12px; border-radius:6px; font-size:0.75rem; font-family:'IBM Plex Mono',monospace; font-weight:600; margin:3px 5px; }
    .tag-support    { background:#021a0e; color:#4ade80; border:1px solid #16a34a; }
    .tag-resistance { background:#1a0202; color:#f87171; border:1px solid #dc2626; }

    /* ── PCR sentiment pill ── */
    .pcr-pill { display:inline-block; padding:3px 10px; border-radius:20px; font-size:0.7rem; font-weight:700; font-family:'IBM Plex Mono',monospace; margin-left:6px; vertical-align:middle; }
    .pcr-bull { background:#052e16; color:#4ade80; border:1px solid #16a34a; }
    .pcr-bear { background:#3f0d0d; color:#f87171; border:1px solid #dc2626; }
    .pcr-neut { background:#1e293b; color:#94a3b8; border:1px solid #334155; }

    /* ── Surge value colors ── */
    .surge-pos { color: #4ade80; }
    .surge-neg { color: #f87171; }
    .surge-zero{ color: #94a3b8; }

    .metric-label { color: #64748b; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 4px; font-family: 'IBM Plex Mono', monospace; }
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

# ── Market status banner ──
_mkt_open = is_market_open()
_cache    = st.session_state.last_cache.get(selected_key, {})
_as_of    = _cache.get("as_of", "—")

col_status, col_btn = st.columns([4, 1])
with col_status:
    if not _mkt_open:
        st.warning(
            f"⏰ {market_status_label()} — showing last closing values as of **{_as_of}**",
            icon="🔔"
        )
with col_btn:
    if st.button("🔄 Refresh Cache", help="Force re-fetch all data from Upstox"):
        # Clear only data caches, keep OI snapshots and surge history
        keys_to_clear = [k for k in st.session_state.last_cache if k != "oi_snapshots"]
        for k in keys_to_clear:
            del st.session_state.last_cache[k]
        st.rerun()

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

        # ── 1. Aggregate OI  (safe access — market_data or oi may be None) ──
        def _oi(opt):
            try: return float(opt.market_data.oi or 0)
            except: return 0.0

        far_ce_oi, far_pe_oi = 0, 0
        for item in near_chain:
            if item.call_options: total_ce_oi += _oi(item.call_options)
            if item.put_options:  total_pe_oi += _oi(item.put_options)
        for item in far_chain:
            if item.call_options: far_ce_oi += _oi(item.call_options)
            if item.put_options:  far_pe_oi += _oi(item.put_options)

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
        valid_ce = [i for i in near_chain if i.call_options and _oi(i.call_options) > 0]
        valid_pe = [i for i in near_chain if i.put_options  and _oi(i.put_options)  > 0]
        if valid_ce:
            resistance_strike = max(valid_ce, key=lambda x: _oi(x.call_options)).strike_price
        if valid_pe:
            support_strike    = max(valid_pe, key=lambda x: _oi(x.put_options)).strike_price

        # ── 4. Momentum Trade Pick with OI surge + IV filter ──
        trade_side = "CALL" if is_bullish or (not is_bearish and spot_price > vwap_price) else "PUT"
        atm_strikes = sorted(near_chain, key=lambda x: abs(x.strike_price - spot_price))[:5]
        options_pool = []

        for item in atm_strikes:
            opt_data = item.call_options if trade_side == "CALL" else item.put_options
            if not opt_data or not opt_data.market_data:
                continue

            ikey    = opt_data.instrument_key
            curr_oi = _safe_float(opt_data.market_data, 'oi') or 0.0
            curr_ltp= _safe_float(opt_data.market_data, 'ltp') or 0.0

            # Skip strikes with zero OI — no meaningful data
            if curr_oi == 0:
                continue

            # IV: try greeks first, then market_data
            iv_val = None
            try:
                if opt_data.greeks:
                    iv_val = _safe_float(opt_data.greeks, 'iv')
            except: pass
            if iv_val is None:
                iv_val = _safe_float(opt_data.market_data, 'iv')

            # ── Baseline OI: stored once per session start, never overwritten ──
            if ikey not in st.session_state.oi_snapshots:
                st.session_state.oi_snapshots[ikey] = {
                    "baseline_oi": curr_oi,
                    "prev_oi":     curr_oi,
                    "time":        datetime.now()
                }

            snap        = st.session_state.oi_snapshots[ikey]
            baseline_oi = snap["baseline_oi"]

            surge_session = ((curr_oi - baseline_oi) / baseline_oi * 100) if baseline_oi > 0 else 0.0
            surge_tick    = ((curr_oi - snap["prev_oi"]) / snap["prev_oi"] * 100) if snap["prev_oi"] > 0 else 0.0

            st.session_state.oi_snapshots[ikey]["prev_oi"] = curr_oi

            options_pool.append({
                "strike":        f"{item.strike_price} {'CE' if trade_side == 'CALL' else 'PE'}",
                "strike_price":  item.strike_price,
                "ltp":           curr_ltp,
                "oi":            curr_oi,
                "surge_session": surge_session,
                "surge_tick":    surge_tick,
                "iv":            round(iv_val, 1) if iv_val else None,
                "time":          round((datetime.now() - snap["time"]).total_seconds() / 60, 1)
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
#  SENTIMENT COLOR HELPERS
# ═══════════════════════════════════════════════════════

def pcr_pill(pcr_val):
    if pcr_val > 1.2:
        return f'<span class="pcr-pill pcr-bull">▲ {pcr_val:.2f} BULLISH</span>'
    elif pcr_val < 0.8:
        return f'<span class="pcr-pill pcr-bear">▼ {pcr_val:.2f} BEARISH</span>'
    else:
        return f'<span class="pcr-pill pcr-neut">◆ {pcr_val:.2f} NEUTRAL</span>'

def tile_class(is_bull, is_bear):
    return "tile-bull" if is_bull else "tile-bear" if is_bear else "tile-neut"

def surge_color(val):
    return "#4ade80" if val > 0 else "#f87171" if val < 0 else "#94a3b8"

def vwap_color(spot, vwap):
    return "#4ade80" if spot > vwap else "#f87171"

# Derive per-PCR sentiment booleans
near_bull = pcr_near > 1.2
near_bear = pcr_near < 0.8
far_bull  = pcr_far  > 1.2
far_bear  = pcr_far  < 0.8
is_bull   = trend_status == "UPTREND"
is_bear   = trend_status == "DOWNTREND"

card_class = "card-bull" if is_bull else "card-bear" if is_bear else "card-neut"
vwap_txt_color = vwap_color(spot_price, vwap_price)
spot_delta_color = vwap_color(spot_price, vwap_price)

# ═══════════════════════════════════════════════════════
#  UI
# ═══════════════════════════════════════════════════════

# ── Overall Trend Banner ──
vwap_label_color = "#4ade80" if spot_price > vwap_price else "#f87171"
vwap_arrow       = "▲ ABOVE" if spot_price > vwap_price else "▼ BELOW"

st.markdown(f"""
    <div class="{trend_class}" style="padding:26px; border-radius:16px; text-align:center; margin-bottom:22px;">
        <div style="color:{trend_color}; font-size:0.72rem; letter-spacing:5px; font-weight:700; opacity:0.7; font-family:'IBM Plex Mono',monospace; margin-bottom:6px;">MARKET STRUCTURE</div>
        <div style="color:{trend_color}; font-size:3rem; font-weight:900; margin:6px 0 10px; font-family:'IBM Plex Mono',monospace;
                    text-shadow: 0 0 30px {trend_color}55;">
            {'🟢' if is_bull else '🔴' if is_bear else '🟡'} {trend_status}
        </div>
        <div style="font-size:0.82rem; font-family:'IBM Plex Mono',monospace; margin-top:4px;">
            <span style="color:{vwap_label_color}; font-weight:600;">{vwap_arrow} VWAP</span>
            <span style="color:#475569;"> &nbsp;|&nbsp; </span>
            <span style="color:#64748b;">PCR Near</span> {pcr_pill(pcr_near)}
            <span style="color:#475569;"> &nbsp;|&nbsp; </span>
            <span style="color:#64748b;">PCR Far</span> {pcr_pill(pcr_far)}
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Metrics Row (sentiment-tinted tiles) ──
spot_delta     = spot_price - vwap_price
spot_val_color = "#4ade80" if spot_delta >= 0 else "#f87171"

st.markdown(f"""
<div style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:12px; margin-bottom:20px;">

  <div class="{tile_class(is_bull, is_bear)}">
    <div class="metric-label">Live Spot</div>
    <div style="color:white; font-size:1.3rem; font-weight:700; font-family:'IBM Plex Mono',monospace;">₹{spot_price:,.2f}</div>
    <div style="color:{spot_val_color}; font-size:0.75rem; font-family:'IBM Plex Mono',monospace; margin-top:4px;">{spot_delta:+.2f} vs VWAP</div>
  </div>

  <div class="{tile_class(near_bull, near_bear)}">
    <div class="metric-label">PCR (Near)</div>
    <div style="color:{'#4ade80' if near_bull else '#f87171' if near_bear else '#94a3b8'}; font-size:1.3rem; font-weight:700; font-family:'IBM Plex Mono',monospace;">{pcr_near:.2f}</div>
    <div style="color:{'#4ade80' if near_bull else '#f87171' if near_bear else '#94a3b8'}; font-size:0.72rem; margin-top:4px;">{'▲ Bullish' if near_bull else '▼ Bearish' if near_bear else '◆ Neutral'}</div>
  </div>

  <div class="{tile_class(far_bull, far_bear)}">
    <div class="metric-label">PCR (Far)</div>
    <div style="color:{'#4ade80' if far_bull else '#f87171' if far_bear else '#94a3b8'}; font-size:1.3rem; font-weight:700; font-family:'IBM Plex Mono',monospace;">{pcr_far:.2f}</div>
    <div style="color:{'#4ade80' if far_bull else '#f87171' if far_bear else '#94a3b8'}; font-size:0.72rem; margin-top:4px;">{'▲ Bullish' if far_bull else '▼ Bearish' if far_bear else '◆ Neutral'}</div>
  </div>

  <div class="tile-neut">
    <div class="metric-label">Day Range</div>
    <div style="color:#4ade80; font-size:1.1rem; font-weight:700; font-family:'IBM Plex Mono',monospace;">H ₹{d_high:,.0f}</div>
    <div style="color:#f87171; font-size:1.1rem; font-weight:700; font-family:'IBM Plex Mono',monospace;">L ₹{d_low:,.0f}</div>
  </div>

</div>
""", unsafe_allow_html=True)

# ── Support & Resistance ──
if support_strike or resistance_strike:
    st.markdown("##### Key S/R Levels (Max OI)")
    sr_html = ""
    if support_strike:
        dist_s = spot_price - support_strike
        sr_html += f'<span class="sr-badge tag-support">🟢 Support: {support_strike:,.0f} &nbsp;({dist_s:+.0f} pts)</span>'
    if resistance_strike:
        dist_r = resistance_strike - spot_price
        sr_html += f'<span class="sr-badge tag-resistance">🔴 Resistance: {resistance_strike:,.0f} &nbsp;({dist_r:+.0f} pts)</span>'
    st.markdown(sr_html, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

# ── Trade Pick Card ──
if best_trade:
    s = best_trade
    iv_display     = f"{s['iv']}%" if s['iv'] else "N/A"
    sess_color     = surge_color(s['surge_session'])
    tick_color     = surge_color(s['surge_tick'])
    ltp_color      = trend_color  # LTP label tinted by overall sentiment

    st.markdown(f"""
    <div class="card {card_class}">
        <div style="display:flex; justify-content:space-between; align-items:start;">
            <div>
                <div class="metric-label">MOMENTUM PICK</div>
                <h1 style="color:{trend_color}; margin:0; font-family:'IBM Plex Mono',monospace;
                           text-shadow:0 0 18px {trend_color}66;">{s['strike']}</h1>
            </div>
            <div style="text-align:right;">
                <div class="metric-label">LTP</div>
                <div style="font-size:1.6rem; color:{ltp_color}; font-weight:bold; font-family:'IBM Plex Mono',monospace;">₹{s['ltp']}</div>
            </div>
        </div>
        <div style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:12px; margin-top:18px;">
            <div style="background:{'#031a0c' if is_bull else '#1a0303' if is_bear else '#070d1a'}; padding:14px; border-radius:10px; text-align:center; border:1px solid {trend_color}22;">
                <div class="metric-label">Session Surge</div>
                <div style="color:{sess_color}; font-weight:700; font-size:1.2rem; font-family:'IBM Plex Mono',monospace;">{s['surge_session']:+.2f}%</div>
            </div>
            <div style="background:{'#031a0c' if is_bull else '#1a0303' if is_bear else '#070d1a'}; padding:14px; border-radius:10px; text-align:center; border:1px solid {trend_color}22;">
                <div class="metric-label">60s Surge</div>
                <div style="color:{tick_color}; font-weight:700; font-size:1.2rem; font-family:'IBM Plex Mono',monospace;">{s['surge_tick']:+.2f}%</div>
            </div>
            <div style="background:{'#031a0c' if is_bull else '#1a0303' if is_bear else '#070d1a'}; padding:14px; border-radius:10px; text-align:center; border:1px solid {trend_color}22;">
                <div class="metric-label">IV</div>
                <div style="color:#a78bfa; font-weight:700; font-size:1.2rem; font-family:'IBM Plex Mono',monospace;">{iv_display}</div>
            </div>
            <div style="background:{'#031a0c' if is_bull else '#1a0303' if is_bear else '#070d1a'}; padding:14px; border-radius:10px; text-align:center; border:1px solid {trend_color}22;">
                <div class="metric-label">Snap Age</div>
                <div style="color:#94a3b8; font-weight:700; font-size:1.2rem; font-family:'IBM Plex Mono',monospace;">{s['time']}m</div>
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

# ── Debug Expander (hidden by default) ──
with st.expander("🔍 Debug Info", expanded=False):
    st.write(f"**Market Open:** {_mkt_open}")
    st.write(f"**Spot:** {spot_price} | **VWAP:** {vwap_price:.2f} | **High:** {d_high} | **Low:** {d_low}")
    st.write(f"**Near PCR:** {pcr_near:.4f}  (CE OI: {total_ce_oi:,.0f} | PE OI: {total_pe_oi:,.0f})")
    st.write(f"**Far PCR:** {pcr_far:.4f}")
    st.write(f"**Expiry list:** {expiry_list[:4] if expiry_list else 'EMPTY'}")
    st.write(f"**Near chain rows:** {len(near_chain) if 'near_chain' in dir() else 'N/A'}")
    if 'options_pool' in dir() and options_pool:
        st.dataframe(pd.DataFrame(options_pool))
    elif 'near_chain' in dir() and near_chain:
        sample = near_chain[0]
        st.write("**Sample chain item (first row):**")
        st.write(f"  Strike: {sample.strike_price}")
        st.write(f"  CE market_data: {sample.call_options.market_data if sample.call_options else 'None'}")
        st.write(f"  PE market_data: {sample.put_options.market_data if sample.put_options else 'None'}")

# ── Footer ──
_sync_label = (
    f"Live Sync: {datetime.now(IST).strftime('%H:%M:%S IST')}"
    if _mkt_open else
    f"After Hours — Last Close Data: {_as_of}"
)
st.caption(
    f"{_sync_label} | "
    f"VWAP: ₹{vwap_price:,.2f} | "
    f"Logic: PCR Band (0.8/1.2) + Weighted VWAP + Max-OI S/R + IV Filter"
)
