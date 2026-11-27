#!/usr/bin/env python3
"""Backtest of @astridwilde's stated stock positions.

Reads ledger.json and prices/*.json (IBKR weekly closes) in this directory and writes backtest.json.
Deterministic: no clock, no network, sorted output. Run twice and diff to confirm.

Conventions
- A "week close" is the last IBKR weekly bar whose week (Monday) contains the date.
- Returns are price returns in the listing currency; dividends are excluded.
- Shorts take the negated return. Options are measured on the underlying (option_proxy=True).
- SPY over the same entry/exit weeks is the benchmark; excess = trade return - SPY return.
"""
import json, os, statistics, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
TODAY = "2026-11-27"
WINDOW_START = "2023-07-14"
LATEST_LABEL = "latest bar (week of 2026-11-23, IBKR label 2026-11-27 where present)"

# ----------------------------------------------------------------------------------------------
# prices
# ----------------------------------------------------------------------------------------------
def monday(d):
    d = dt.date.fromisoformat(d[:10])
    return (d - dt.timedelta(days=d.weekday())).isoformat()

PRICES = {}
for fn in sorted(os.listdir(os.path.join(HERE, "prices"))):
    if fn.endswith(".json"):
        p = json.load(open(os.path.join(HERE, "prices", fn)))
        PRICES[fn[:-5]] = p

def series(t):
    return PRICES.get(t)

FALLBACKS = []

def week_close(t, date):
    """(bar_label, close) of the last bar in the week containing date.
    If the listing has no bar that week (holiday / missing bar), the first bar of the following week is used
    (recorded in FALLBACKS). None if neither exists."""
    s = series(t)
    if not s:
        return None
    w = monday(date)
    hit = None
    for lab, c in zip(s["time"], s["close"]):
        if monday(lab) == w:
            hit = (lab, c)
    if hit is None:
        nxt = (dt.date.fromisoformat(w) + dt.timedelta(days=7)).isoformat()
        for lab, c in zip(s["time"], s["close"]):
            if monday(lab) == nxt:
                hit = (lab, c)
                if (t, date) not in FALLBACKS:
                    FALLBACKS.append((t, date))
                break
    return hit

def latest_close(t):
    s = series(t)
    return (s["time"][-1], s["close"][-1]) if s else None

def closes_between(t, d0, d1):
    s = series(t)
    w0, w1 = monday(d0), monday(d1)
    return [(lab, c) for lab, c in zip(s["time"], s["close"]) if w0 <= monday(lab) <= w1]

def first_date(t):
    s = series(t)
    return s["time"][0] if s else None

def rnd(x, n=4):
    return None if x is None else round(x, n)

def ann(r, days):
    if r is None or days is None or days <= 0 or r <= -1:
        return None
    return (1 + r) ** (365.0 / days) - 1

def days_between(a, b):
    return (dt.date.fromisoformat(b[:10]) - dt.date.fromisoformat(a[:10])).days

def mid_date(a, b):
    da, db = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    return (da + (db - da) / 2).isoformat()

# ----------------------------------------------------------------------------------------------
# ledger
# ----------------------------------------------------------------------------------------------
L = json.load(open(os.path.join(HERE, "ledger.json")))
POS = L["positions"]

# Ledger ticker -> price file(s). Lists are equal-weight baskets.
PRICE_MAP = {
    "SKHY": "SKHY_KRX",          # KRX 000660 primary listing (US ADR only exists from 2026-07)
    "GOOGL": "GOOG",             # class C used for class A rows
    "AI SOFTWARE basket (SNOW, DDOG)": ["SNOW", "DDOG"],
}

# Stated entry prices and whether they are fills.
STATED_PRICE_KIND = {
    ("APP", "2024-08-27"): "upper_bound ('under $12/share', said 2026-10-25)",
    ("APP", "2025-02-26"): "upper_bound ('under $300')",
    ("ARBKL", "2025-07-01"): "limit_bid suggestion ($2.60), not a confirmed fill",
    ("DIS", "2023-08-24"): "conditional bid ($70), fill never stated",
    ("BTCW.V", "2023-02-03"): "hash-commitment reference price, not a stated fill",
    ("NTDOY", "2026-05-08"): "stated purchase price ('$10.50/share')",
}

# Rows excluded from the headline for structural reasons (beyond weak confidence / private).
STRUCTURAL_EXCLUDE = {
    "MEMORY basket": "basket overlaps the single-ticker MU, SKHY and SNDK rows (ledger: do not double count)",
    "DATACENTER CAPEX basket": "basket overlaps the 2025 NVDA call row; holdings not named; entry and exit on the same disclosure date",
    "NEOCLOUD basket (CRWV inferred)": "entry and exit on the same disclosure date (no measurable holding); names inferred",
    "CANNABIS basket": "tickers not named",
    "SCIENTIFIC PUBLISHERS basket": "which publishers were shorted is not stated",
    "PORTFOLIO MARKET BETA": "portfolio-level exposure change, not a priceable position (used in the book-weighted estimate)",
    "WAL": "the 2023 banking-crisis trade has no entry or exit date in the ledger; 2024-10-20 is only a retrospective mention",
}


def price_keys(ticker):
    m = PRICE_MAP.get(ticker, ticker)
    return m if isinstance(m, list) else [m]

def priced(ticker):
    return all(series(k) for k in price_keys(ticker))

def basket_close(ticker, date):
    """Equal-weight basket handled by the caller via per-name returns; single name returns (label, close)."""
    ks = price_keys(ticker)
    if len(ks) == 1:
        return week_close(ks[0], date)
    return None

def ret_between(ticker, d0, d1, latest=False):
    """Price return of ticker from week(d0) close to week(d1) close (or latest bar). Basket = equal-weight mean."""
    ks = price_keys(ticker)
    rs, legs = [], []
    for k in ks:
        a = week_close(k, d0)
        b = latest_close(k) if latest else week_close(k, d1)
        if not a or not b:
            return None, None
        rs.append(b[1] / a[1] - 1)
        legs.append({"price_file": k, "entry_bar": a[0], "entry_close": a[1], "exit_bar": b[0], "exit_close": b[1]})
    return sum(rs) / len(rs), legs

def spy_ret(d0, d1, latest=False):
    a = week_close("SPY", d0)
    b = latest_close("SPY") if latest else week_close("SPY", d1)
    if not a or not b:
        return None
    return b[1] / a[1] - 1

def evidence_ids(p):
    ids = [p.get("entry_post"), p.get("exit_post")]
    for k in ("entry", "exit"):
        for e in p.get("evidence", {}).get(k, []):
            ids.append(e["post"])
    w = p.get("exit_window") or {}
    ids += [w.get("last_seen_post"), w.get("first_absent_post")]
    for s in (p.get("size") if isinstance(p.get("size"), list) else [p.get("size")]):
        if isinstance(s, dict):
            ids.append(s.get("post"))
    out = []
    for i in ids:
        if i and i not in out:
            out.append(i)
    return out

def last_evidence_date(p):
    ds = [p.get("entry_date"), p.get("exit_date")]
    for k in ("entry", "exit"):
        for e in p.get("evidence", {}).get(k, []):
            ds.append(e.get("date"))
    w = p.get("exit_window") or {}
    ds.append(w.get("last_seen_held"))
    for s in (p.get("size") if isinstance(p.get("size"), list) else [p.get("size")]):
        if isinstance(s, dict):
            ds.append(s.get("date"))
    return max(d for d in ds if d)

# ----------------------------------------------------------------------------------------------
# per-trade rows
# ----------------------------------------------------------------------------------------------
def classify(p):
    """-> (bucket, reason). bucket in headline | weak | private | excluded"""
    t, inst, conf = p["ticker"], p["instrument"], p["confidence"]
    if inst == "private":
        return "private", "private / non-tradable holding"
    if t in STRUCTURAL_EXCLUDE:
        return "excluded", STRUCTURAL_EXCLUDE[t]
    if conf == "weak":
        return "weak", "weak confidence (excluded from headline per method)"
    if p.get("exit_date") and p.get("exit_date") == p.get("backtest_entry_date") \
            and p.get("entry_basis") in ("first_disclosed_at_exit", "stated_intent"):
        return "excluded", "first disclosed at its exit: entry date unknown, no measurable holding period"
    if monday(p.get("backtest_entry_date") or p["entry_date"]) >= monday("2026-11-23"):
        return "excluded", "entry falls in the latest price week: no measurable holding period"
    if inst not in ("stock", "ETF", "etf", "warrant", "crypto", "call", "put", "short"):
        return "excluded", "instrument %s not in universe" % inst
    return "headline", None

def exposure(p):
    """+1 long underlying, -1 short underlying; option proxy flag."""
    inst, d = p["instrument"], p["direction"]
    if inst == "call":
        return 1, True, "long call measured as long underlying"
    if inst == "put":
        if d == "short":
            return 1, True, "short put (bullish) measured as long underlying"
        return -1, True, "long put measured as short underlying"
    if inst == "short" or d == "short":
        return -1, False, "short: negated return"
    return 1, False, None

def build_trade(i, p, bucket, why):
    t = p["ticker"]
    row = {
        "row": i, "ticker": t, "leg": p.get("leg"), "instrument": p["instrument"], "direction": p["direction"],
        "confidence": p["confidence"], "bucket": bucket, "status": p["status"],
        "post_ids": evidence_ids(p), "notes": [],
    }
    if why:
        row["notes"].append(why)
    sign, opt, expl = exposure(p)
    row["option_proxy"] = opt
    if expl:
        row["notes"].append(expl)
    if not priced(t):
        row["priced"] = False
        row["unpriced_reason"] = ("weak confidence (outside the headline): not fetched from IBKR in this run" if bucket == "weak"
                                  else "no IBKR price series")
        return row
    entry = p.get("backtest_entry_date") or p["entry_date"]
    keys = price_keys(t)
    fd = max(first_date(k) for k in keys)
    if monday(entry) < monday(fd):
        row["priced"] = False
        row["unpriced_reason"] = "entry %s precedes the available IBKR history (starts %s)" % (entry, fd)
        return row
    row["priced"] = True
    row["price_files"] = keys
    row["currency"] = PRICES[keys[0]].get("currency")
    row["entry_date"] = entry
    row["entry_basis"] = p.get("backtest_entry_basis") or "entry_date"
    # exit
    w = p.get("exit_window")
    if p.get("exit_date") and p["exit_date"] >= entry:
        exit_d, mode = p["exit_date"], "exit_date"
        row["exit_basis"] = "exit_date (%s)" % p.get("exit_basis")
    elif w:
        exit_d, mode = mid_date(w["last_seen_held"], w["first_absent"]), "window_mid"
        row["exit_basis"] = "exit_window midpoint of %s..%s (last listed -> first absent)" % (w["last_seen_held"], w["first_absent"])
        row["exit_window"] = [w["last_seen_held"], w["first_absent"]]
    else:
        exit_d, mode = TODAY, "open"
        row["exit_basis"] = "open_or_unknown: marked to " + LATEST_LABEL
        led = last_evidence_date(p)
        row["last_evidence_date"] = led
        row["stale_mark"] = days_between(led, TODAY) > 180
    latest = mode == "open"
    r, legs = ret_between(t, entry, exit_d, latest=latest)
    if r is None:
        row["priced"] = False
        row["unpriced_reason"] = "no weekly bar for entry or exit week"
        return row
    if len(keys) == 1:
        row["entry_bar"], row["entry_price"] = legs[0]["entry_bar"], legs[0]["entry_close"]
        row["exit_bar"], row["exit_price"] = legs[0]["exit_bar"], legs[0]["exit_close"]
        # stated entry price
        sp = p.get("entry_price_stated")
        kind = STATED_PRICE_KIND.get((t, p.get("backtest_entry_date") or p["entry_date"]))
        if sp is not None:
            row["entry_price_stated"] = sp
            row["entry_price_stated_kind"] = kind
            close = row["entry_price"]
            within = abs(sp / close - 1) <= 0.15
            if kind and kind.startswith("stated") and within:
                row["entry_price"] = sp
                r = row["exit_price"] / sp - 1
                row["notes"].append("stated fill %.4g used (within 15%% of week close %.4g)" % (sp, close))
            else:
                row["notes"].append("stated %.4g not used: %s; %s 15%% of week close %.4g" % (
                    sp, kind or "unclassified", "within" if within else "outside", close))
    else:
        row["basket_legs"] = legs
    row["exit_date"] = row.get("exit_bar") if latest else exit_d
    r_trade = sign * r
    sr = spy_ret(entry, exit_d, latest=latest)
    end = legs[0]["exit_bar"] if latest else exit_d
    hd = days_between(entry, end if not latest else TODAY)
    row.update({
        "holding_days": hd,
        "underlying_return": rnd(r), "return": rnd(r_trade), "annualized": rnd(ann(r_trade, hd)),
        "spy_return": rnd(sr), "excess_vs_spy": rnd(r_trade - sr if sr is not None else None),
    })
    if hd < 30:
        row["notes"].append("holding under 30 days: annualized figure not meaningful")
    if mode == "window_mid":
        lo = hi = None
        rs = []
        for k in keys:
            a = week_close(k, entry)
            seg = closes_between(k, w["last_seen_held"], w["first_absent"])
            rs.append([sign * (c / a[1] - 1) for _, c in seg])
        if all(rs):
            n = min(len(x) for x in rs)
            path = [sum(x[j] for x in rs) / len(rs) for j in range(n)]
            lo, hi = min(path), max(path)
        row["window_return_low"], row["window_return_high"] = rnd(lo), rnd(hi)
        s0 = week_close("SPY", entry)[1]
        sseg = [c / s0 - 1 for _, c in closes_between("SPY", w["last_seen_held"], w["first_absent"])]
        row["window_spy_low"], row["window_spy_high"] = rnd(min(sseg)), rnd(max(sseg))
    if row["currency"] and row["currency"] != "USD":
        row["notes"].append("return in %s (local currency)" % row["currency"])
    for k in keys:
        if PRICES[k].get("note"):
            row["notes"].append("%s: %s" % (k, PRICES[k]["note"]))
    return row

TRADES = []
for i, p in enumerate(POS):
    b, why = classify(p)
    if b in ("private",):
        TRADES.append({"row": i, "ticker": p["ticker"], "bucket": b, "priced": False,
                       "unpriced_reason": why, "post_ids": evidence_ids(p), "confidence": p["confidence"]})
        continue
    if b == "excluded":
        TRADES.append({"row": i, "ticker": p["ticker"], "bucket": b, "priced": False,
                       "excluded_reason": why, "post_ids": evidence_ids(p), "confidence": p["confidence"],
                       "instrument": p["instrument"]})
        continue
    TRADES.append(build_trade(i, p, b, why if b == "weak" else None))

HEAD = [t for t in TRADES if t["bucket"] == "headline" and t.get("priced")]

def agg(rows):
    rs = [t["return"] for t in rows]
    ex = [t["excess_vs_spy"] for t in rows]
    if not rs:
        return {"n": 0}
    return {
        "n": len(rs),
        "mean_return": rnd(statistics.mean(rs)), "median_return": rnd(statistics.median(rs)),
        "hit_rate": rnd(sum(1 for r in rs if r > 0) / len(rs)),
        "hit_rate_vs_spy": rnd(sum(1 for e in ex if e > 0) / len(ex)),
        "sum_excess_vs_spy": rnd(sum(ex)),
        "mean_excess_vs_spy": rnd(statistics.mean(ex)), "median_excess_vs_spy": rnd(statistics.median(ex)),
        "mean_spy_return": rnd(statistics.mean(t["spy_return"] for t in rows)),
    }

AGG_A = {
    "headline_all": agg(HEAD),
    "headline_ex_option_proxies": agg([t for t in HEAD if not t["option_proxy"]]),
    "option_proxies_only": agg([t for t in HEAD if t["option_proxy"]]),
    "headline_closed_or_windowed_only": agg([t for t in HEAD if not t["exit_basis"].startswith("open")]),
    "headline_ex_stale_marks": agg([t for t in HEAD if not t.get("stale_mark")]),
    "weak_confidence_priced": agg([t for t in TRADES if t["bucket"] == "weak" and t.get("priced")]),
    "assumptions": [
        "Equal weight per trade; each re-entry leg is a separate trade.",
        "Entry = week close of backtest_entry_date; exit = week close of exit_date, or exit-window midpoint, or the latest bar for open_or_unknown rows.",
        "open_or_unknown rows with no exit evidence are marked to the latest bar; 'stale_mark' = last evidence older than 180 days (sensitivity row excludes them).",
        "Options (calls, puts) measured on the underlying; leverage unknown. Shorts negated.",
        "Price return only, dividends excluded; local currency (SK Hynix in KRW).",
        "Excess = trade return minus SPY price return over the same entry/exit weeks.",
    ],
}

def tl(t):
    return {k: t.get(k) for k in ("ticker", "leg", "row", "entry_date", "exit_date", "entry_price", "exit_price",
                                   "return", "spy_return", "excess_vs_spy", "holding_days", "exit_basis",
                                   "option_proxy", "currency", "post_ids")}

TOP = {
    "top5_by_return": [tl(t) for t in sorted(HEAD, key=lambda t: (-t["return"], t["row"]))[:5]],
    "top5_by_excess": [tl(t) for t in sorted(HEAD, key=lambda t: (-t["excess_vs_spy"], t["row"]))[:5]],
    "worst5_by_return": [tl(t) for t in sorted(HEAD, key=lambda t: (t["return"], t["row"]))[:5]],
    "worst5_by_excess": [tl(t) for t in sorted(HEAD, key=lambda t: (t["excess_vs_spy"], t["row"]))[:5]],
}

# ----------------------------------------------------------------------------------------------
# (b) book-weighted estimate
# ----------------------------------------------------------------------------------------------
CASH, PROXY = "CASH", "SPY_PROXY"
BOOK_PRICE = {"VAL": "VAL", "SKHY": "SKHY_KRX"}   # VAL row is 2026 40c calls: underlying used

def bp(t):
    return BOOK_PRICE.get(t, t)

# Each event: (date, post_ids, kind, spec, basis)
#  set_full: dict of weights (fractions). Anything not priced is moved to SPY_PROXY. Residual to fill 100% goes to `residual`.
#  set_names: set named weights, funded from `fund` order (list of buckets) then pro rata from remaining non-cash.
#  cash_to: set cash fraction; non-cash scaled pro rata.
#  move: move all weight of names to target bucket.
EVENTS = [
    ("2023-07-14", ["1679931444750323712"], "set_full", {"w": {CASH: 0.50}, "residual": PROXY},
     "assumed: '>50% in cash' taken as 50%; the undisclosed rest earns SPY"),
    ("2024-01-05", ["1743229653106803197"], "set_names", {"w": {"TCEHY": 0.2/3, "BIDU": 0.2/3, "BABA": 0.2/3}, "fund": [PROXY]},
     "partial: China largecaps 20% (equal split assumed), funded from the undisclosed slice"),
    ("2024-01-25", ["1750334625006989798"], "set_names", {"w": {"ENTG": 0.05, "TSM": 0.05}, "fund": [PROXY]},
     "partial: ENTG+TSM '>10% of net worth' taken as 10% (equal split assumed)"),
    ("2024-09-30", ["1840887410739003716", "1848753001634128192"], "set_full",
     {"w": {"CPNG": .12, "APP": .11, "GRUSF": .10, "TSM": .09, "ACFN": .03, "NTDOY": .03, "DAC": .02, "COVCF": .015,
            "CPH.TO": .01, "RRGB": .01, "MOB.ST": .01, "CRL": .005, "GSL": .005, CASH: .12, PROXY: .41 + .025 - .12},
      "residual": PROXY},
     "full book: listed weights sum to 99%; the 12% cash is assumed to sit inside the 41% 'undisclosed' line; undisclosed rest and 1% residual earn SPY"),
    ("2024-10-22", ["1848753001634128192"], "set_full",
     {"w": {"APP": .091, "CPNG": .083, "TSM": .074, "GRUSF": .061, "ACFN": .027, "NTDOY": .02, "RRGB": .01, "COVCF": .009,
            "CPH.TO": .007, "CRL": .004, "GSL": .004, PROXY: .554 + .036}, "residual": CASH},
     "full book: undisclosed 59% earns SPY; the 0.9% residual is treated as cash; DAC reported sold"),
    ("2024-11-12", ["1856391266017095824"], "cash_to", {"cash": 0.50}, "cash-only update: 'went to 50% cash'; holdings scaled pro rata"),
    ("2024-12-09", ["1866149181506597201"], "move", {"names": ["APP"], "to": CASH}, "APP leg-1 exit (inferred) to cash"),
    ("2025-01-08", ["1877043951464505499"], "cash_to", {"cash": 0.40}, "cash-only update: 'up to 40% cash'"),
    ("2025-02-26", ["1894763674654376113"], "cash_to", {"cash": 0.50},
     "cash-only update: '50% cash'; the APP buy-back weight is not stated and is not modelled"),
    ("2025-03-10", ["1899150866281795614"], "cash_to", {"cash": 0.40}, "cash-only update: '40%'; GOOG/AMZN buys appear in the 04-02 book"),
    ("2025-04-02", ["1907225874266726690"], "set_full",
     {"w": {CASH: .35, "CPH.TO": .106, "CPNG": .065, "NTDOY": .051, "APP": .051, "TSM": .051, "CIB": .05, "AMZN": .035,
            "REGN": .03, "ACFN": .025, "RELY": .025, "DAC": .024, PROXY: .017, "VAL": .014, "TDW": .013, "FOA": .012,
            "HII": .012, "AMTM": .01, "COVCF": .01, "GOOG": .01}, "residual": PROXY},
     "full book of >1% lines (96.1%); the 3.9% residual (<1% lines) earns SPY; VAL 40c calls measured on VAL"),
    ("2025-07-01", ["1940069022961385595"], "keep_only",
     {"keep": ["CPH.TO", "CPNG", "NTDOY", "GOOG", "ACFN", "AMTM", "REGN", "COVCF"], "to": PROXY},
     "ordered list without weights: surviving names keep drifted weights; dropped names' weight earns SPY; new unweighted names (DMGI.V, TGTX, HROW, ARBKL) sit in that SPY slice"),
    ("2025-08-07", ["1953600042843222423"], "set_names", {"w": {"CPH.TO": 0.15}, "fund": [PROXY]}, "partial: CPH.TO ~15% of LNW"),
    ("2026-01-21", ["2014044628828184608"], "set_names", {"w": {"ADBE": 0.05}, "fund": [PROXY]}, "partial: ADBE 2% -> 5%"),
    ("2026-02-03", ["2018760073569599774"], "set_names", {"w": {"ADBE": 0.08}, "fund": [PROXY]}, "partial: ADBE 8%"),
    ("2026-02-06", ["2019893114207629314"], "set_full",
     {"w": {"APP": .31, "NNI": .18, "RELY": .10, "TWST": .095, "NVDA": .07, "HROW": .03, "TGTX": .025, "AMTM": .025,
            "ACFN": .02, "RGEN": .02, "ASML": .015}, "residual": PROXY},
     "full book: listed 89%; no cash line, the 11% residual is treated as undisclosed and earns SPY; ADBE cut"),
    ("2026-03-26", ["2037216555843674518"], "set_names", {"w": {"NVDA": .10, "META": .10, "SKHY": .10}, "fund": []},
     "partial: NVDA+META+SK Hynix 30% (equal split assumed), funded pro rata from the rest"),
    ("2026-05-06", ["2052078363637158196"], "move", {"names": ["SKHY"], "to": CASH}, "'realized all gains in ... memory': SK Hynix to cash"),
    ("2026-05-08", ["2052817098939015459", "2082110993606611098"], "set_names", {"w": {"NTDOY": None}, "fund": [CASH], "from_freed": "SKHY"},
     "NTDOY bought back, funded by the memory sale (07-28 post): weight = SK Hynix weight freed on 05-06 (assumed)"),
    ("2026-06-27", ["2070928172456214776"], "move", {"names": ["META"], "to": CASH}, "META exit (inferred from 'I'm out') to cash"),
    ("2026-09-04", ["2095870240035082499"], "set_full",
     {"w": {CASH: .36, "RELY": .064, "NVDA": .064, "QXO": .064, "SKHY": .064, PROXY: .064 * 2, "HROW": .064, "NTDOY": .064,
            "ACFN": .064, "AMZN": .064}, "residual": PROXY},
     "ordered >1% list with cash 36% only: the 10 lines share 64% equally (assumed); the 2 undisclosed lines earn SPY"),
    ("2026-11-04", ["2118070900860076241"], "set_names", {"w": {"APP": .175, "RELY": .175}, "fund": [CASH]},
     "partial: APP+RELY 35% (equal split assumed), funded from cash"),
]
SCENARIOS = {
    "A_base": [("2026-11-06", ["2118526296431137146"], "keep_only", {"keep": ["APP", "RELY"], "to": CASH},
                "'sold beta': everything except APP+RELY (still reported 11-04/11-05, no sale stated) to cash")],
    "B_all_cash_from_2026-11-06": [("2026-11-06", ["2118526296431137146", "2123644589282369940", "2125440798909251770"],
                                    "keep_only", {"keep": [], "to": CASH},
                                    "'sit out the market in cash' (11-20, 11-25) applied from the 11-06 beta sale: 100% cash")],
}

def norm(w):
    return {k: v for k, v in w.items() if abs(v) > 1e-12}

def apply_event(w, ev, freed):
    date, ids, kind, spec, basis = ev
    notes = []
    w = dict(w)
    if kind == "set_full":
        nw = dict(spec["w"])
        tot = sum(nw.values())
        nw[spec["residual"]] = nw.get(spec["residual"], 0) + (1 - tot)
        w = nw
    elif kind == "cash_to":
        c = spec["cash"]
        rest = {k: v for k, v in w.items() if k != CASH}
        s = sum(rest.values())
        w = {k: v * (1 - c) / s for k, v in rest.items()}
        w[CASH] = c
    elif kind == "move":
        for n in spec["names"]:
            v = w.pop(n, 0)
            freed[n] = v
            w[spec["to"]] = w.get(spec["to"], 0) + v
    elif kind == "keep_only":
        for k in list(w):
            if k in (CASH, PROXY) or k in spec["keep"]:
                continue
            w[spec["to"]] = w.get(spec["to"], 0) + w.pop(k)
        if spec["to"] == CASH and not spec["keep"]:
            w = {CASH: 1.0}
        elif spec["to"] == CASH:
            w[CASH] = w.get(CASH, 0) + w.pop(PROXY, 0)
    elif kind == "set_names":
        targets = dict(spec["w"])
        if spec.get("from_freed"):
            for n in targets:
                targets[n] = freed.get(spec["from_freed"], 0)
        need = sum(targets[n] - w.get(n, 0) for n in targets)
        for n in targets:
            w[n] = targets[n]
        for b in spec["fund"]:
            take = min(need, w.get(b, 0)) if need > 0 else need
            w[b] = w.get(b, 0) - take
            need -= take
            if abs(need) < 1e-12:
                break
        if abs(need) > 1e-12:
            others = {k: v for k, v in w.items() if k not in targets and k != CASH and v > 0}
            s = sum(others.values())
            if s > 0:
                for k in others:
                    w[k] -= need * others[k] / s
                notes.append("funded %.4f pro rata from other holdings" % need)
            else:
                w[CASH] = w.get(CASH, 0) - need
    # unpriced names to SPY proxy
    for k in list(w):
        if k not in (CASH, PROXY) and not series(bp(k)):
            w[PROXY] = w.get(PROXY, 0) + w.pop(k)
            notes.append("%s unpriced -> SPY" % k)
    return norm(w), notes

def run_book(extra_events):
    cal = [lab for lab in PRICES["SPY"]["time"] if monday(lab) >= monday(WINDOW_START)]
    evs = sorted(EVENTS + extra_events, key=lambda e: e[0])
    w, freed, seg_log, ev_log = {}, {}, [], []
    idx = {k: {lab: c for lab, c in zip(PRICES[k]["time"], PRICES[k]["close"])} for k in PRICES}
    def r_of(k, prev, cur):
        if k == CASH:
            return 0.0
        key = "SPY" if k == PROXY else bp(k)
        d = idx.get(key, {})
        a, b = d.get(prev), d.get(cur)
        if a is None or b is None:
            # carry the last known close forward (missing week or series ended)
            pa = [lab for lab in d if lab <= prev]
            pb = [lab for lab in d if lab <= cur]
            if not pa or not pb:
                return 0.0
            a, b = d[max(pa)], d[max(pb)]
        return b / a - 1
    nav, spy_nav = 1.0, 1.0
    path = {}
    ei = 0
    seg = None
    for j, lab in enumerate(cal):
        if j > 0:
            prev = cal[j - 1]
            R = sum(v * r_of(k, prev, lab) for k, v in w.items())
            S = r_of(PROXY, prev, lab)
            nav *= 1 + R
            spy_nav *= 1 + S
            # drift
            tot = sum(v * (1 + r_of(k, prev, lab)) for k, v in w.items())
            w = {k: v * (1 + r_of(k, prev, lab)) / tot for k, v in w.items()}
        path[lab] = (nav, spy_nav)
        # events in this week apply at this week's close
        while ei < len(evs) and monday(evs[ei][0]) <= monday(lab) and (j == len(cal) - 1 or monday(cal[j + 1]) > monday(evs[ei][0])):
            if seg:
                seg.update({"end_bar": lab, "end_nav": nav, "end_spy": spy_nav})
                seg_log.append(seg)
            ev = evs[ei]
            w, notes = apply_event(w, ev, freed)
            ev_log.append({"date": ev[0], "post_ids": ev[1], "kind": ev[2], "basis": ev[4], "notes": notes,
                           "weights_after": {k: rnd(v) for k, v in sorted(w.items())}})
            seg = {"start_event": ev[0], "start_bar": lab, "start_nav": nav, "start_spy": spy_nav, "basis": ev[4],
                   "cash": rnd(w.get(CASH, 0)), "spy_proxy_share": rnd(w.get(PROXY, 0)),
                   "named_priced_share": rnd(sum(v for k, v in w.items() if k not in (CASH, PROXY)))}
            ei += 1
    if seg:
        seg.update({"end_bar": cal[-1], "end_nav": nav, "end_spy": spy_nav})
        seg_log.append(seg)
    segs = []
    for s in seg_log:
        segs.append({"from": s["start_event"], "start_bar": s["start_bar"], "end_bar": s["end_bar"],
                     "portfolio_return": rnd(s["end_nav"] / s["start_nav"] - 1),
                     "spy_return": rnd(s["end_spy"] / s["start_spy"] - 1),
                     "cash_at_start": s["cash"], "spy_proxy_share_at_start": s["spy_proxy_share"],
                     "named_priced_share_at_start": s["named_priced_share"], "weights_basis": s["basis"]})
    return {"start_bar": cal[0], "end_bar": cal[-1], "cumulative_return": rnd(nav - 1),
            "spy_cumulative_return": rnd(spy_nav - 1), "excess_vs_spy": rnd(nav - spy_nav),
            "segments": segs, "events": ev_log}, path

BOOK, PATHS = {}, {}
for name, extra in SCENARIOS.items():
    BOOK[name], PATHS[name] = run_book(extra)

def book_ctx(d0, d1, scn="A_base"):
    """Book-weighted and SPY return between the week closes of d0 and d1."""
    p = PATHS[scn]
    labs = sorted(p)
    a = [l for l in labs if monday(l) <= monday(d0)]
    b = [l for l in labs if monday(l) <= monday(d1)]
    a = a[-1] if a else labs[0]
    b = b[-1]
    return {"from_bar": a, "to_bar": b, "book_weighted_pct": pct(p[b][0] / p[a][0] - 1), "spy_pct": pct(p[b][1] / p[a][1] - 1)}

def nav_between(scn, d0, d1):
    """Book-weighted return between two dates for context (scenario A)."""
    res, cal = run_book(SCENARIOS[scn])
    return res

AGG_B = {
    "window": [WINDOW_START, PRICES["SPY"]["time"][-1]],
    "scenarios": BOOK,
    "assumptions": [
        "Weights chain between successive weighted books; between events, weights drift with prices (buy-and-hold).",
        "Cash earns 0%. Undisclosed lines, residuals to 100%, and unpriced names (COVCF, MOB.ST, etc.) earn SPY and are flagged in event notes.",
        "Only books/updates that state a weight or cash share change the weights; dated exits stated in the ledger move the weight to cash.",
        "Partial updates that name several tickers with one combined weight split it equally (assumed).",
        "2023-07-14 to 2024-09-30 has no full book: 50% cash / 50% SPY plus the China (20%) and ENTG+TSM (10%) partial weights.",
        "2025-07-01 and 2026-09-04 lists have no per-name weights (see event basis).",
        "Scenario A keeps APP+RELY (35%) after the 2026-11-06 beta sale; scenario B is 100% cash from 2026-11-06.",
        "SK Hynix uses KRX 000660 in KRW; FX not modelled. VAL calls are measured on VAL.",
    ],
}
# which periods have weights
AGG_B["weight_coverage"] = [
    {"period": "2023-07-14..2024-09-29", "weights": "assumed (cash share + partial China / ENTG+TSM weights)"},
    {"period": "2024-09-30..2024-11-11", "weights": "full books 2024-09-30 and 2024-10-22 (41-59% undisclosed -> SPY)"},
    {"period": "2024-11-12..2025-04-01", "weights": "drifted 2024-10-22 book rescaled to stated cash shares (50/40/50/40%); APP leg-1 exit to cash"},
    {"period": "2025-04-02..2025-06-30", "weights": "full book 2025-04-02"},
    {"period": "2025-07-01..2026-02-05", "weights": "drifted 2025-04-02 survivors (no weights in 07-01 list), CPH.TO 15% (08-07), ADBE 5-8% (01-21, 02-03)"},
    {"period": "2026-02-06..2026-09-03", "weights": "full book 2026-02-06, NVDA/META/SKHY 30% (03-26), memory sale -> NTDOY (05-06/08), META exit (06-27)"},
    {"period": "2026-09-04..2026-11-26", "weights": "cash 36% + equal split of ordered list (assumed); APP+RELY 35% (11-04); 11-06 beta sale per scenario"},
]

# ----------------------------------------------------------------------------------------------
# claims check
# ----------------------------------------------------------------------------------------------
def pct(x):
    return None if x is None else round(100 * x, 2)

def tol_verdict(claimed, actual):
    """claimed/actual as fractions."""
    tol = max(0.10, 0.20 * abs(claimed))
    if abs(actual - claimed) <= tol:
        return "consistent"
    return "overstated" if claimed > actual else "understated"

def r_simple(t, d0, d1=None):
    a = week_close(t, d0)
    b = latest_close(t) if d1 is None else week_close(t, d1)
    if not a or not b:
        return None, a, b
    return b[1] / a[1] - 1, a, b

def claim_specs():
    out = {}
    # 2023-07-28 +100% (filed as META); APP shown too
    r1, a1, b1 = r_simple("META", "2023-01-17", "2023-07-28")
    r2, a2, b2 = r_simple("APP", "2022-12-09", "2023-07-28")
    out["1684972690615242752"] = {
        "computed": {"META_2023-01-17_to_2023-07-28": pct(r1), "META_bars": [a1, b1],
                     "APP_2022-12-09_to_2023-07-28": pct(r2), "APP_bars": [a2, b2]},
        "verdict": tol_verdict(1.0, r1),
        "basis": "claimed +100% realized; META (ledger filing) from its 2023-01-17 self-quoted entry; APP from the 2022-12-09 'both bets' post for comparison"}
    # JXN +48% since added in March 2023
    rows = [(lab, c) for lab, c in closes_between("JXN", "2023-03-01", "2023-03-31")]
    e = week_close("JXN", "2023-12-15")
    rs = [e[1] / c - 1 for _, c in rows]
    out["1735697118193651745"] = {
        "computed": {"JXN_from_each_March_2023_week_to_2023-12-15_pct": [pct(x) for x in rs], "exit_bar": e},
        "verdict": "consistent" if min(rs) - 0.10 <= 0.48 <= max(rs) + 0.10 else tol_verdict(0.48, statistics.median(rs)),
        "basis": "claimed +48% since added in March 2023 (exact add date unknown: every March week tested)"}
    # RRGB double
    q3 = closes_between("RRGB", "2024-07-01", "2024-09-30")
    e = week_close("RRGB", "2024-10-20")
    lo = min(c for _, c in q3)
    r_lo, r_930 = e[1] / lo - 1, e[1] / week_close("RRGB", "2024-09-30")[1] - 1
    out["1847838812971430239"] = {
        "computed": {"RRGB_from_Q3_2024_low_close": pct(r_lo), "RRGB_from_2024-09-30_week": pct(r_930), "exit_bar": e},
        "verdict": tol_verdict(1.0, r_lo),
        "basis": "claimed a double; entry unknown within Q3 2024 (initiated that quarter): best case from the lowest Q3 weekly close"}
    # APP exit within 2% of ATH (weekly closes)
    s = closes_between("APP", "2021-04-12", "2024-12-09")
    ath = max(c for _, c in s)
    ex = week_close("APP", "2024-12-09")
    atl = min(c for _, c in s)
    ath_bar = max(s, key=lambda x: x[1])
    out["1866149181506597201"] = {
        "computed": {"APP_2024-12-09_week_close": ex, "max_weekly_close_to_then": ath_bar, "gap_of_12-09_week_to_ath_pct": pct(ex[1] / ath - 1),
                     "min_weekly_close_to_then": atl, "upper_bound_entry_vs_atl_pct": pct(12 / atl - 1)},
        "verdict": "consistent" if monday(ath_bar[0]) >= monday("2024-11-25") else "overstated",
        "basis": "claimed exit within 2% of the ATH (posted after the fact on 12-09). The highest weekly close (401.50) is the week of 2024-12-02, the week before the post, so a sale near the top is plausible; within-2% is intraday and not checkable. The ledger's 12-09 exit week closed 19% below that high, so APP leg 1 as backtested understates the stated exit."}
    # GRUSF 10x
    r_e, a, b = r_simple("GRUSF", "2023-09-06", "2025-02-18")
    lo = min(c for _, c in closes_between("GRUSF", "2021-11-29", "2025-02-18"))
    out["1891681975938748627"] = {
        "computed": {"GRUSF_2023-09-06_to_2025-02-18_pct": pct(r_e), "bars": [a, b], "from_series_low_pct": pct(b[1] / lo - 1)},
        "verdict": tol_verdict(9.0, r_e),
        "basis": "claimed '10x' (+900%); from the first in-window holding statement 2023-09-06 (OTC USD line); a 10x only holds from the 2022 lows"}
    # MU -35% then +50% since 2025-02-18
    base = week_close("MU", "2025-02-18")
    seg = closes_between("MU", "2025-02-18", "2025-09-10")
    mn = min(c for _, c in seg)
    now = week_close("MU", "2025-09-10")
    out["1965802140703850705"] = {
        "computed": {"base_bar": base, "max_drawdown_pct": pct(mn / base[1] - 1), "to_2025-09-10_pct": pct(now[1] / base[1] - 1)},
        "verdict": "consistent" if (abs((mn / base[1] - 1) + 0.35) <= 0.10 and abs((now[1] / base[1] - 1) - 0.50) <= 0.15) else tol_verdict(0.50, now[1] / base[1] - 1),
        "basis": "claimed -35% then +50% from the 2025-02-18 'buy Micron' post"}
    # SPY +10.3% over 5 months from 2023-03-03 (picks tracker)
    r_s, a, b = r_simple("SPY", "2023-03-03", "2023-08-10")
    out["1689518685545975813"] = {
        "computed": {"SPY_2023-03-03_to_2023-08-10_pct": pct(r_s), "bars": [a, b]},
        "verdict": "consistent" if abs(r_s - 0.103) <= 0.02 else tol_verdict(0.103, r_s),
        "basis": "only the SPY leg (+10.3%) is checkable; QQQ, ZIG, CSU/MKL/LVMH and TDW/TS/OEC legs were not priced (TDW history starts 2024-11)"}
    # S&P +50% since 2022-12-20 (simple theses scorecard)
    r_s, a, b = r_simple("SPY", "2022-12-20", "2024-09-23")
    gsl, ga, gb = r_simple("GSL", "2022-12-20", "2024-09-23")
    out["1838065316796276929"] = {
        "computed": {"SPY_2022-12-20_to_2024-09-23_pct": pct(r_s), "GSL_same_pct": pct(gsl)},
        "verdict": "consistent" if abs(r_s - 0.50) <= 0.05 else tol_verdict(0.50, r_s),
        "basis": "the S&P +50% leg is checkable (SPY price only); the +28.8% equal-weighted picks figure needs VNO, RIG, LXU, AFM.V (not priced); GSL shown"}
    # MRVI first L (sign)
    r_m, a, b = r_simple("MRVI", "2025-02-08", "2025-02-25")
    out["1894399223581258134"] = {"computed": {"MRVI_2025-02-08_to_2025-02-25_pct": pct(r_m)},
                                 "verdict": "consistent" if r_m < 0 else "overstated",
                                 "basis": "claimed a loss; sign check over the ledger's inferred holding (entry may be earlier)"}
    # NTLA second L (sign) from the 2025-10-08 endorsement
    r_n, a, b = r_simple("NTLA", "2025-10-08", "2025-10-27")
    out["1982858252061950431"] = {"computed": {"NTLA_2025-10-08_to_2025-10-27_pct": pct(r_n)},
                                 "verdict": "consistent" if r_n < 0 else "overstated",
                                 "basis": "claimed a loss; sign check from the 2025-10-08 endorsement (entry not stated)"}
    # 2025-11-07 Ls this year: MRVI, NTLA, QURE, RELY (sign checks, 2025 YTD for RELY)
    r_r, a, b = r_simple("RELY", "2024-12-31", "2025-11-07")
    r_q, qa, qb = r_simple("QURE", "2025-10-27", "2025-11-07")
    out["1986848723151036911"] = {"computed": {"RELY_2025YTD_to_2025-11-07_pct": pct(r_r), "QURE_wk_2025-10-27_to_2025-11-07_pct": pct(r_q),
                                              "MRVI_pct": pct(r_m), "NTLA_pct": pct(r_n)},
                                 "verdict": "consistent" if all(x < 0 for x in (r_r, r_q, r_m, r_n)) else "overstated",
                                 "basis": "sign check: each named loser down over its implied 2025 period (RELY from 2024 year-end)"}
    # 2026-07-28 dodged -30% in memory; +10% in Nintendo
    dd = {}
    for k in ("MU", "SKHY_KRX", "SNDK"):
        a = week_close(k, "2026-05-06")
        seg = closes_between(k, "2026-05-06", "2026-07-28")
        dd[k] = {"to_2026-07-28_pct": pct(seg[-1][1] / a[1] - 1), "max_drawdown_from_peak_pct": pct(min(c for _, c in seg) / max(c for _, c in seg) - 1)}
    n0 = 10.5
    n1 = week_close("NTDOY", "2026-07-28")
    out["2082110993606611098"] = {"computed": {"memory_after_2026-05-06_sale": dd, "NTDOY_from_$10.50_to_2026-07-28_pct": pct(n1[1] / n0 - 1)},
                                 "verdict": "consistent" if (n1[1] / n0 - 1) > 0.05 and min(dd[k]["max_drawdown_from_peak_pct"] for k in dd) <= -25 else "overstated",
                                 "basis": "claimed memory fell ~30% after the 05-06 sale while NTDOY (bought at $10.50) rose ~10%"}
    # CIB big winner by 2024-01-05 (sign, from 2023-09-12 holding statement)
    r_c, a, b = r_simple("CIB", "2023-09-12", "2024-01-05")
    out["1743301646292341197"] = {"computed": {"CIB_2023-09-12_to_2024-01-05_pct": pct(r_c)},
                                 "verdict": "consistent" if r_c > 0.15 else "overstated",
                                 "basis": "qualitative 'big winner': checked from the 2023-09-12 in-window holding statement (cost basis predates the window and is unknown)"}
    # AMRK great trade
    r_a, a, b = r_simple("AMRK", "2022-11-09", "2024-11-07")
    out["1854534281814520172"] = {"computed": {"AMRK_2022-11-09_to_2024-11-07_pct": pct(r_a), "SPY_same_pct": pct(spy_ret("2022-11-09", "2024-11-07"))},
                                 "verdict": "consistent" if r_a > 0 else "overstated",
                                 "basis": "qualitative 'great trade': sign check over the ledger's inferred holding"}
    # GEO significant alpha 2024 (calls; underlying)
    r_g, a, b = r_simple("GEO", "2024-07-05", "2024-10-24")
    sp = spy_ret("2024-07-05", "2024-10-24")
    out["1849569538276458827"] = {"computed": {"GEO_2024-07-05_to_2024-10-24_pct": pct(r_g), "SPY_same_pct": pct(sp),
                                              "GEO_max_weekly_close_2024-07-05_to_2024-10-24": max(c for _, c in closes_between("GEO", "2024-07-05", "2024-10-24"))},
                                 "verdict": "uncheckable",
                                 "basis": "qualitative claim on GEO calls: strike, expiry and exit unknown; underlying shown for context (it rose from 14.83 to a 16.34 weekly-close high, then fell back)"}
    # QURE 2026-09-29 made money owning the stock (sign from 2025-11-03 inferred holding)
    r_q2, a, b = r_simple("QURE", "2025-11-03", "2026-09-29")
    out["2104911896780644593"] = {"computed": {"QURE_2025-11-03_to_2026-09-29_pct": pct(r_q2)},
                                 "verdict": "uncheckable",
                                 "basis": "entry not stated (held before 2025-11-03 per ledger note); from 2025-11-03 the stock is shown for context only"}
    # APP 2026-08-05 -6% of LNW (implied weight)
    a = week_close("APP", "2026-07-27"); b = week_close("APP", "2026-08-03")
    mv = b[1] / a[1] - 1
    out["2085106834030158102"] = {"computed": {"APP_week_of_2026-08-03_move_pct": pct(mv), "implied_weight_for_-6pct_LNW": pct(0.06 / abs(mv)) if mv else None},
                                 "verdict": "uncheckable",
                                 "basis": "one-day move and weight not observable with weekly data; implied weight shown"}
    # 2026-11-05 +10% day APP+CCLD
    a = week_close("APP", "2026-10-26"); b = week_close("APP", "2026-11-02")
    c0 = week_close("CCLD", "2026-10-26"); c1 = week_close("CCLD", "2026-11-02")
    out["2118360364153012240"] = {"computed": {"APP_week_of_2026-11-02_pct": pct(b[1] / a[1] - 1), "CCLD_week_of_2026-11-02_pct": pct(c1[1] / c0[1] - 1)},
                                 "verdict": "uncheckable", "basis": "single-day portfolio figure; weekly data and unknown weights"}
    # 2025-06-04 ~200% portfolio since 2023-06-12 -> book-weighted context
    out["1930257653827285515"] = {"verdict": "uncheckable",
                                 "basis": "portfolio-level; the book-weighted estimate (mostly assumed weights before 2024-09-30) is shown for context"}
    # QURE FDA rug pull (sign)
    out["1985331353983045636"] = {"computed": {"QURE_week_2025-10-27_to_2025-11-03_pct": pct(r_q)},
                                 "verdict": "consistent" if r_q < 0 else "overstated",
                                 "basis": "claimed a loss on the FDA news; adjacent weekly closes around 2025-11-03"}
    # beta sale timing: SPY after the 11-06 sale week
    r_sp, a, b = r_simple("SPY", "2026-11-06")
    out["2118526296431137146"] = {"computed": {"SPY_week_2026-11-02_to_latest_pct": pct(r_sp), "bars": [a, b]},
                                 "verdict": "consistent" if r_sp < 0 else "overstated",
                                 "basis": "qualitative 'crazy timing to sell beta': SPY from the sale week close to the latest bar"}
    # NBIS / CRWV / TPR / SATS / ARBKL handled if priced
    if series("NBIS"):
        for pid, d1, fig in (("1890461842759155996", "2025-02-14", 0.50), ("1891864035320049687", "2025-02-18", 0.90),
                             ("1973756630002172386", "2025-10-02", 3.40)):
            r_b, a, b = r_simple("NBIS", "2025-01-27", d1)
            out[pid] = {"computed": {"NBIS_2025-01-27_to_%s_pct" % d1: pct(r_b), "bars": [a, b]},
                        "verdict": tol_verdict(fig, r_b), "basis": "weekly closes from the week of the 2025-01-27 call; the call was made on the 01-27 DeepSeek selloff, so an intraday fill below the 32.66 week close would lift the figure"}
        r_b, a, b = r_simple("NBIS", "2025-10-14", "2025-10-22")
        out["1981018647050301799"] = {"computed": {"NBIS_2025-10-14_to_2025-10-22_pct": pct(r_b)},
                                     "verdict": "uncheckable", "basis": "intra-week figures (-22% etc.) not resolvable with weekly closes; IREN, GEV, VRT, BE not priced; NBIS weekly move shown"}
    if series("CRWV"):
        r_w, a, b = r_simple("CRWV", "2026-05-06", "2026-05-12")
        out["2054209619992662299"] = {"computed": {"CRWV_week_2026-05-06_to_2026-05-12_pct": pct(r_w), "bars": [a, b]},
                                     "verdict": tol_verdict(0.30, -r_w), "basis": "claimed a -30% drop in the six days after the 05-06 sale; adjacent weekly closes show a much smaller drop (intra-week low not checkable)"}
    if series("TPR"):
        r_t, a, b = r_simple("TPR", "2024-11-07", "2024-11-26")
        out["1861481017279648096"] = {"computed": {"TPR_2024-11-07_to_2024-11-26_pct": pct(r_t)}, "verdict": tol_verdict(0.20, r_t),
                                     "basis": "claimed +20% since the 2024-11-07 call"}
        r_t, a, b = r_simple("TPR", "2024-11-07", "2025-01-31")
        out["1885334311777313079"] = {"computed": {"TPR_2024-11-07_to_2025-01-31_pct": pct(r_t)}, "verdict": tol_verdict(0.50, r_t),
                                     "basis": "claimed +50% in 3 months from the 2024-11-07 call"}
    return out

SPEC = claim_specs()

def default_reason(c):
    k = c.get("kind", "")
    fig = c.get("claimed_figure", "")
    if k.startswith("portfolio") or k in ("risk_stats", "public_contest"):
        return "portfolio-level figure: no account data; book weights too partial to verify"
    if "image" in fig:
        return "figures only in an image (not captured)"
    if "unquantified" in fig or "called it" in fig or fig.startswith("n/a"):
        return "no checkable figure or period"
    if c.get("ticker") and not all(priced(t.strip()) for t in c["ticker"].replace("/", ",").split(",") if t.strip()):
        return "ticker(s) not priced or not tradable"
    return "horizon or instrument not resolvable with weekly closes"

CLAIMS = []
for c in L["claimed_returns"]:
    pid = c["post_id"]
    row = {"date": c["date"], "post_id": pid, "ticker": c.get("ticker"), "quote": c["quote"],
           "claimed_figure": c["claimed_figure"], "kind": c["kind"]}
    if pid in SPEC:
        row.update(SPEC[pid])
    else:
        row["verdict"] = "uncheckable"
        row["basis"] = default_reason(c)
    CLAIMS.append(row)

# book-weighted context for portfolio-level claims (verdict stays uncheckable)
CTX = {
    "1930257653827285515": ("2023-07-14", "2025-06-04", "claimed ~+200% since 2023-06-12 (window starts 2023-07-14)"),
    "1986848310318277063": ("2024-11-07", "2025-11-07", "claimed +74% LTM"),
    "1840884002154057911": ("2024-01-01", "2024-09-30", "claimed +45% YTD 2024"),
    "1961474654964441395": ("2024-12-31", "2025-08-29", "claimed +33% YTD 2025"),
    "1966134399537430556": ("2024-09-11", "2025-09-11", "claimed 'absurd LTM'"),
    "2084699182959673832": ("2026-07-27", "2026-08-04", "claimed +13.5% in two days (weekly: week of 07-27 to week of 08-03)"),
    "1874749539992961501": ("2024-01-01", "2024-12-31", "claimed 2024 second-best year (figures in image)"),
}
for row in CLAIMS:
    if row["post_id"] in CTX:
        d0, d1, what = CTX[row["post_id"]]
        row["book_weighted_context"] = dict(book_ctx(d0, d1), claim=what,
                                            caveat="book-weighted estimate with assumed weights; not the account's reported performance")

# ----------------------------------------------------------------------------------------------
# current portfolio (as of 2026-11-27)
# ----------------------------------------------------------------------------------------------
CURRENT = {
    "as_of": TODAY,
    "start_book": {"date": "2026-09-04", "post_id": "2095870240035082499", "cash_pct": "36%",
                   "holdings_in_weight_order": ["RELY", "NVDA", "QXO", "SKHY", "undisclosed 1", "HROW", "NTDOY", "undisclosed 2", "ACFN", "AMZN"]},
    "later_changes": [
        {"date": "2026-11-01", "post_id": "2116736100937224192", "change": "'i'm bearish market beta'"},
        {"date": "2026-11-02", "post_id": "2117370896268898605", "change": "wants APP under $180 'so i can put on a 30% weight'"},
        {"date": "2026-11-03", "post_id": "2117635166785138733", "change": "bought TAN (election hedge)"},
        {"date": "2026-11-04", "post_id": "2118070900860076241", "change": "APP+RELY grown to 35% weight"},
        {"date": "2026-11-04", "post_id": "2117801715680543132", "change": "will sell all Texas datacenter exposure (intent)"},
        {"date": "2026-11-05", "post_id": "2118360364153012240", "change": "+10% day from APP and CCLD (CCLD holding implied)"},
        {"date": "2026-11-06", "post_id": "2118526296431137146", "change": "'crazy timing ... to sell beta'"},
        {"date": "2026-11-20", "post_id": "2123644589282369940", "change": "'sitting out the market for the last month'"},
        {"date": "2026-11-23", "post_id": "2124916147145588802", "change": "NVDA calls implied ('did not buy far enough OTM')"},
        {"date": "2026-11-25", "post_id": "2125440798909251770", "change": "'continue to sit out the market in cash'; slowly accumulating QURE (suggested)"},
    ],
    "holdings": [
        {"ticker": "APP", "status": "possibly sold", "weight_last_stated": "35% with RELY (2026-11-04)", "post_ids": ["2118070900860076241", "2118360364153012240", "2125440798909251770"],
         "contradiction": "reported at 35% with RELY on 11-04 and a +10% day on 11-05, no sale stated, yet 11-20/11-25 say 'sitting out the market in cash'"},
        {"ticker": "RELY", "status": "possibly sold", "weight_last_stated": "35% with APP (2026-11-04)", "post_ids": ["2118070900860076241", "2118091716100276619", "2125440798909251770"],
         "contradiction": "same as APP; 11-04 'please keep selling $RELY' signals intent to buy more"},
        {"ticker": "CCLD", "status": "possibly sold", "weight_last_stated": "unknown", "post_ids": ["2118360364153012240", "2118359597228675448"],
         "contradiction": "bought ~11-05 (implied); conflicts with 'in cash' 11-20/11-25"},
        {"ticker": "TAN", "status": "possibly sold", "weight_last_stated": "unknown", "post_ids": ["2117635166785138733", "2117998945876213903"],
         "contradiction": "election-hedge bought 11-03, 'it worked out' 11-04; no exit stated; 'in cash' 11-25"},
        {"ticker": "NVDA (stock)", "status": "possibly sold", "weight_last_stated": "listed 2nd on 2026-09-04", "post_ids": ["2095870240035082499", "2118526296431137146"],
         "contradiction": "11-06 beta sale may include it; 11-23 implies NVDA calls (separate row)"},
        {"ticker": "NVDA (calls)", "status": "possibly sold", "weight_last_stated": "unknown", "post_ids": ["2124916147145588802"],
         "contradiction": "implied 0DTE-style calls around 2026-11-20..23 while 'in cash'; likely expired or closed"},
        {"ticker": "SKHY", "status": "possibly sold", "weight_last_stated": "listed 4th on 2026-09-04", "post_ids": ["2095870240035082499", "2122873151306825875", "2118526296431137146"],
         "contradiction": "11-18 ambiguous remark on memory bulls; beta sale 11-06"},
        {"ticker": "SNDK", "status": "possibly sold", "weight_last_stated": "<1% or absent on 2026-09-04", "post_ids": ["2084699182959673832", "2095870240035082499"],
         "contradiction": "part of the 07-28 memory re-entry; not in the 09-04 >1% list"},
        {"ticker": "QXO", "status": "possibly sold", "weight_last_stated": "listed 3rd on 2026-09-04", "post_ids": ["2095870240035082499", "2118526296431137146"]},
        {"ticker": "HROW", "status": "possibly sold", "weight_last_stated": "listed 6th on 2026-09-04", "post_ids": ["2095870240035082499", "2119955290154291353", "2118526296431137146"],
         "contradiction": "11-10 'probably a 3x over the next 4 years' (bullish) vs 'in cash' 11-25"},
        {"ticker": "NTDOY", "status": "possibly sold", "weight_last_stated": "listed 7th on 2026-09-04", "post_ids": ["2095870240035082499", "2118526296431137146"]},
        {"ticker": "ACFN", "status": "possibly sold", "weight_last_stated": "listed 9th on 2026-09-04", "post_ids": ["2095870240035082499", "2118526296431137146"]},
        {"ticker": "AMZN", "status": "possibly sold", "weight_last_stated": "listed 10th on 2026-09-04", "post_ids": ["2095870240035082499", "2118526296431137146"]},
        {"ticker": "QURE", "status": "possibly held (accumulating)", "weight_last_stated": "unknown", "post_ids": ["2125440798909251770"],
         "contradiction": "'slowly accumulating $QURE' (suggested) in the same 11-25 post that says 'sit out the market in cash'"},
        {"ticker": "Texas datacenter exposure (private)", "status": "sold (intent stated, completion not reported)", "post_ids": ["2117801715680543132"]},
        {"ticker": "Precigenetics (private)", "status": "likely held", "post_ids": ["2116067563151270020"]},
        {"ticker": "Cash", "status": "likely majority", "weight_last_stated": "36% (2026-09-04); 'in cash' 2026-11-25 (no %)", "post_ids": ["2095870240035082499", "2123644589282369940", "2125440798909251770"]},
    ],
    "reading": "Two readings fit the posts: (A) beta sold on ~11-06 but the 35% APP+RELY core (and small CCLD/TAN) kept, so 'sit out the market' means no index/beta exposure; (B) everything sold, 100% cash. No post resolves it; the book-weighted estimate reports both.",
}
# fill latest prices + moves since 2026-11-06 week for context
for h in CURRENT["holdings"]:
    t = h["ticker"].split(" ")[0]
    k = PRICE_MAP.get(t, t)
    if isinstance(k, str) and series(k):
        a = week_close(k, "2026-11-06")
        b = latest_close(k)
        h["latest_close"] = b
        h["move_since_2026-11-06_week_pct"] = pct(b[1] / a[1] - 1) if a else None
# fix Precigenetics post id from ledger
for p in POS:
    if p["ticker"].startswith("PRECIGENETICS"):
        for h in CURRENT["holdings"]:
            if h["ticker"].startswith("Precigenetics"):
                h["post_ids"] = evidence_ids(p)

# ----------------------------------------------------------------------------------------------
# endorsed picks
# ----------------------------------------------------------------------------------------------
ENDORSE_MAP = {
    "GLNG": (["GLNG"], 1), "FOA": (["FOA"], 1), "VAL,BORR,TDW (offshore)": (["VAL", "BORR", "TDW"], 1),
    "TSM,NVDA,MRVL": (["TSM", "NVDA", "MRVL"], 1), "HROW": (["HROW"], 1), "TWST": (["TWST"], 1), "NTLA": (["NTLA"], 1),
    "TWST,NTRA": (["TWST", "NTRA"], 1), "GOOGL": (["GOOG"], 1), "ADBE long / publishers short": (["ADBE"], 1),
    "SK Hynix (000660.KS)": (["SKHY_KRX"], 1), "semicap (TSMC guidance)": (["TSM"], 1), "APP": (["APP"], 1),
    "MU": (["MU"], 1), "NVDA, MU, SNDK": (["NVDA", "MU", "SNDK"], 1), "SNOW": (["SNOW"], 1), "QURE": (["QURE"], 1),
    "ASML,TSM,AMAT,LRCX,KLAC": (["ASML", "TSM", "AMAT", "LRCX", "KLAC"], 1), "CCLD": (["CCLD"], 1), "NVDA": (["NVDA"], 1),
    "CPH.TO": (["CPH.TO"], 1), "NNI": (["NNI"], 1), "NU": (["NU"], 1), "PRGS (bearish)": (["PRGS"], -1),
    "ALPP (short)": (["ALPP"], -1), "VSAT (bearish event)": (["VSAT"], -1), "BB": (["BB"], 1),
    "AMR,METC,HCC,CEIX (coal)": (["AMR", "METC", "HCC", "CEIX"], 1), "ASPI": (["ASPI"], 1), "CLPT / CLS.b": (["CLPT"], 1),
    "ROOT": (["ROOT"], 1), "NXSN.TA": (["NXSN.TA"], 1), "REKR (vs SOUN)": (["REKR"], 1), "FPH": (["FPH"], 1), "CLF": (["CLF"], 1),
    "DM (NNDM merger arb)": (["DM"], 1), "ODD": (["ODD"], 1), "SEZL,HIMS": (["SEZL", "HIMS"], 1), "GTLB": (["GTLB"], 1),
    "CVNA": (["CVNA"], 1), "LLY/ABVX": (["ABVX"], 1), "BW (and BE)": (["BW", "BE"], 1), "PL": (["PL"], 1), "REPL": (["REPL"], 1),
    "SEZL": (["SEZL"], 1), "INTC": (["INTC"], 1), "KRE": (["KRE"], 1), "HOOD (and SIVB call)": (["HOOD"], 1),
}
ENDORSED = []
for e in L["endorsed_picks"]:
    t = e["ticker"]
    row = {"date": e["date"], "post_id": e["post_id"], "ticker": t, "quoted_author": e.get("quoted_author"),
           "quoted_id": e.get("quoted_id"), "account_holds_per_ledger": e.get("account_holds_per_ledger")}
    m = ENDORSE_MAP.get(t)
    if not m:
        row["priced"] = False
        row["reason"] = "private company or not mapped to a listed ticker"
        ENDORSED.append(row)
        continue
    names, sign = m
    got = [k for k in names if series(k) and week_close(k, e["date"])]
    miss = [k for k in names if k not in got]
    if not got:
        row["priced"] = False
        row["reason"] = "not fetched from IBKR in this run: " + ", ".join(miss)
        ENDORSED.append(row)
        continue
    rs, legs = [], []
    for k in got:
        a = week_close(k, e["date"]); b = latest_close(k)
        rs.append(b[1] / a[1] - 1)
        legs.append({"price_file": k, "entry_bar": a[0], "entry_close": a[1], "exit_bar": b[0], "exit_close": b[1], "return": rnd(b[1] / a[1] - 1)})
    r = sign * sum(rs) / len(rs)
    sr = spy_ret(e["date"], TODAY, latest=True)
    row.update({"priced": True, "direction": "short/bearish" if sign < 0 else "long", "legs": legs,
                "return": rnd(r), "spy_return": rnd(sr), "excess_vs_spy": rnd(r - sr),
                "holding_days": days_between(e["date"], TODAY)})
    if miss:
        row["unpriced_legs"] = miss
    ENDORSED.append(row)
pe = [x for x in ENDORSED if x.get("priced")]
ENDORSED_SUMMARY = {"n_priced": len(pe), "n_total": len(ENDORSED),
                    "mean_return": rnd(statistics.mean(x["return"] for x in pe)) if pe else None,
                    "median_return": rnd(statistics.median(x["return"] for x in pe)) if pe else None,
                    "hit_rate": rnd(sum(1 for x in pe if x["return"] > 0) / len(pe)) if pe else None,
                    "hit_rate_vs_spy": rnd(sum(1 for x in pe if x["excess_vs_spy"] > 0) / len(pe)) if pe else None,
                    "basis": "endorsement-week close to the latest bar; baskets equal-weight over priced names; bearish picks negated"}

# ----------------------------------------------------------------------------------------------
# unpriced list
# ----------------------------------------------------------------------------------------------
UNP_FETCH = json.load(open(os.path.join(HERE, "prices_unpriced.json"))) if os.path.exists(os.path.join(HERE, "prices_unpriced.json")) else {}
UNPRICED = []
seen = set()
for t in TRADES:
    if t.get("priced"):
        continue
    key = (t["ticker"], t["row"])
    reason = t.get("unpriced_reason") or t.get("excluded_reason")
    tk = t["ticker"]
    if tk in UNP_FETCH:
        reason = UNP_FETCH[tk]
    UNPRICED.append({"ticker": tk, "row": t["row"], "bucket": t["bucket"], "confidence": t.get("confidence"),
                     "reason": reason, "post_ids": t["post_ids"]})
for e in ENDORSED:
    if not e.get("priced") or e.get("unpriced_legs"):
        UNPRICED.append({"ticker": e["ticker"], "endorsed_pick": True, "post_id": e["post_id"],
                         "reason": e.get("reason") or ("legs not fetched from IBKR in this run: " + ", ".join(e["unpriced_legs"]))})

OUT = {
    "meta": {
        "account": "astridwilde", "as_of": TODAY, "source_ledger": "ledger.json", "prices": "prices/*.json (IBKR weekly closes, outside_rth=false)",
        "benchmark": "SPY (ARCA, conid 756733) weekly close, price only",
        "method": AGG_A["assumptions"],
        "price_fetch_notes": [
            "Periods ONE_YEAR/TWO_YEARS/FIVE_YEARS chosen as the shortest covering each holding (step_count was ignored by the API).",
            "IBKR's latest bar is labelled 2026-11-27 (partial week after 2026-11-23) for most listings; OTC/KRX series end at the 2026-11-23 bar.",
            "Some PINK series contain a duplicate 2023-04-24/2023-04-25 bar pair; the 04-25 bar is kept as that week's close.",
            "Non-permissioned venues (TSX, TSX Venture, Stockholm): CPH.TO and DMGI.V priced on their US OTC lines (USD); others unpriced.",
        ],
    },
    "trades": TRADES,
    "aggregates_equal_weight": AGG_A,
    "aggregates_book_weighted": AGG_B,
    "top_and_worst": TOP,
    "claims_check": CLAIMS,
    "current_portfolio": CURRENT,
    "endorsed_picks": {"summary": ENDORSED_SUMMARY, "rows": ENDORSED},
    "unpriced": UNPRICED,
    "week_fallbacks_used": [{"price_file": a, "date": b, "rule": "no bar in that week; first bar of the following week used"} for a, b in FALLBACKS],
}
json.dump(OUT, open(os.path.join(HERE, "backtest.json"), "w"), indent=1, sort_keys=False, ensure_ascii=False)
print("trades", len(TRADES), "headline", len(HEAD), "claims", len(CLAIMS), "endorsed priced", ENDORSED_SUMMARY["n_priced"])
