#!/usr/bin/env python3
"""Build accounts/astridwilde/backtest/ledger.json from posts.jsonl.

Every evidence quote is checked as a verbatim substring of the cited post's own
text (or, when marked, of a quoted post inside it). Every date is taken from the
cited post's created_at (or the quoted post's created_at for claimed_* fields).
The script fails loudly on any mismatch.
"""
import json, re, sys, collections, os

ROOT = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
POSTS = {}
for line in open(f"{ROOT}/posts.jsonl"):
    p = json.loads(line)
    POSTS[p["id"]] = p

ERR = []

def d(pid):
    if pid not in POSTS:
        ERR.append(f"missing post id {pid}")
        return None
    return POSTS[pid]["created_at"][:10]

def chain(p):
    q = p.get("quoted")
    while q:
        yield q
        q = q.get("quoted")

def ev(pid, s, role=None, quoted=False):
    """Evidence: verbatim substring of post text, or of a quoted post (quoted=True)."""
    if pid not in POSTS:
        ERR.append(f"missing post id {pid}")
        return {"post": pid}
    p = POSTS[pid]
    out = {"post": pid, "date": p["created_at"][:10]}
    if role:
        out["role"] = role
    if not quoted:
        if s not in p["text"]:
            ERR.append(f"quote not in {pid}: {s!r}")
        out["quote"] = s
    else:
        for q in chain(p):
            if s in (q.get("text") or ""):
                out.update({"quote": s, "quote_source": "quoted_post",
                            "quoted_id": q.get("id"), "quoted_handle": q.get("handle"),
                            "quoted_date": (q.get("created_at") or "")[:10] or None})
                break
        else:
            ERR.append(f"quoted quote not in {pid}: {s!r}")
    return out

def qdate(pid, handle="astridwilde"):
    """created_at date of the first quoted post by handle inside pid."""
    for q in chain(POSTS[pid]):
        if q.get("handle") == handle:
            return (q.get("created_at") or "")[:10] or None, q.get("id")
    ERR.append(f"no quoted {handle} post in {pid}")
    return None, None

def pos(ticker, instrument, direction, entry_post, entry_basis, confidence,
        evidence_entry, evidence_exit=(), exit_post=None, exit_basis=None,
        entry_price=None, exit_price=None, size=None, ticker_note=None,
        note=None, claimed_entry=None, exit_window=None, legs=None, leg=None,
        confidence_exit=None, status=None):
    e = {
        "ticker": ticker,
        "ticker_note": ticker_note,
        "instrument": instrument,
        "direction": direction,
        "leg": leg,
        "entry_date": d(entry_post) if entry_post else None,
        "entry_post": entry_post,
        "entry_basis": entry_basis,
        "entry_price_stated": entry_price,
        "exit_date": d(exit_post) if exit_post else None,
        "exit_post": exit_post,
        "exit_basis": exit_basis,
        "exit_price_stated": exit_price,
        "status": status or ("closed" if exit_post else "open_or_unknown"),
        "size": size,
        "evidence": {"entry": list(evidence_entry), "exit": list(evidence_exit)},
        "confidence": confidence,
        "confidence_exit": confidence_exit,
        "note": note,
    }
    if claimed_entry:
        e["claimed_entry"] = claimed_entry
    be = e["entry_date"]
    if claimed_entry and claimed_entry.get("date") and (be is None or claimed_entry["date"] < be):
        be = claimed_entry["date"]
    e["backtest_entry_date"] = be
    e["backtest_entry_basis"] = "claimed_entry.date (earlier quoted self-post or stated earlier buy)" if be != e["entry_date"] else "entry_date"
    if exit_window:
        e["exit_window"] = exit_window
    if legs:
        e["legs"] = legs
    return {k: v for k, v in e.items() if v is not None}

def window(after_post, before_post, why):
    return {"last_seen_held": d(after_post), "last_seen_post": after_post,
            "first_absent": d(before_post), "first_absent_post": before_post,
            "basis": why}

def sz(value, post):
    if post == B_2024_09_30 and "2024-09-30" in value:
        return {"value": value, "post": post, "date": "2024-09-30", "quoted_id": "1840887410739003716",
                "date_basis": "created_at of the quoted 2024-09-30 book inside post"}
    return {"value": value, "post": post, "date": d(post)}

def claimed(pid, handle="astridwilde", why=None):
    dt, qid = qdate(pid, handle)
    out = {"date": dt, "quoted_id": qid, "via_post": pid,
           "basis": why or "earlier self-post quoted inside via_post; quoted id is not a row in posts.jsonl"}
    if qid in POSTS:
        out["basis"] = (why or "earlier self-post quoted inside via_post") + "; quoted id is also a row in posts.jsonl"
    return out

# Books used repeatedly
B_2024_09_30 = "1848753001634128192"   # its quoted post 1840887410739003716 is the 2024-09-30 book
B_2024_10_22 = "1848753001634128192"
B_2025_04_02 = "1907225874266726690"
B_2025_05_19 = "1924290564335587399"
B_2025_07_01 = "1940069022961385595"
B_2026_02_06 = "2019893114207629314"
B_2026_09_04 = "2095870240035082499"
B_2026_11_04 = "2118070900860076241"

ABS = "absent from the next posted holdings list"

P = []

# ---------------------------------------------------------------- 2023
P.append(pos("CBIT.V", "stock", "long", "1679851224513015808", "first_disclosed_at_exit", "inferred",
    [ev("1741685939028873455", "long: $CBIT.V"), ev("1740060712448458916", "buying BTC miners last Christmas was easy")],
    [ev("1679851224513015808", "closed out my BTC miner L/S this morning"), ev("1697622477470589069", "in hindsight i literally top ticked it")],
    exit_post="1679851224513015808", exit_basis="stated", ticker_note="TSX Venture (non-US). Long leg of the BTC miner L/S pair.",
    note="Pair named only as the 2023 contest picks (1741685939028873455: 'my Bitcoin miner L/S picks went from being +350% in February to ending the year negative'); that the closed 2023-07-14 L/S is this same pair is inferred. Entry predates the capture window (2023-07-14); 1740060712448458916 says miners were bought 'last Christmas' (Dec 2022)."))
P.append(pos("WULF", "short", "short", "1679851224513015808", "first_disclosed_at_exit", "inferred",
    [ev("1741685939028873455", "short: $WULF")],
    [ev("1679851224513015808", "closed out my BTC miner L/S this morning")],
    exit_post="1679851224513015808", exit_basis="stated", ticker_note="Short leg of the BTC miner L/S pair.",
    note="See CBIT.V. Same pairing inference."))
P.append(pos("SIMO", "stock", "long", "1681670272187785220", "stated", "explicit",
    [ev("1681670272187785220", "my stink bid on $SIMO was filled today")],
    [ev("1684236603181666304", "after that $SIMO win"), ev("1684590562807279616", "vol on $SIMO is mispriced")],
    note="No sale stated. 'after that $SIMO win' (2023-07-26) may mean a realized gain; 2026-01-08 retrospective on the vol call: 'short term vol printed / long term vol printed' [2009120203146424506]. Options use is implied by the vol language but not stated."))
P.append(pos("AAMC", "stock", "long", "1682063349377548294", "stated", "explicit",
    [ev("1682063349377548294", "add some more $AAMC to the piggy bank"),
     ev("1683868473678757888", "add more $AAMC to the piggy bank"),
     ev("1691174221941215233", "i am taking a beating on $AAMC and i am also doubling down on the bet"),
     ev("1686942315468955648", "$AAMC")],
    [ev("1691215743634022400", "happy to report my first L of the year"), ev("1970502652774760914", "$AAMC was my biggest L of all time")],
    legs=[{"date": d("1682063349377548294"), "post": "1682063349377548294", "action": "add"},
          {"date": d("1683868473678757888"), "post": "1683868473678757888", "action": "add"},
          {"date": d("1691174221941215233"), "post": "1691174221941215233", "action": "add ('doubling down')"}],
    note="First in-window post is already an add, so the original entry predates 2023-07-20. Exit never stated; 2025-09-23 calls it 'my biggest L of all time' (loss, realization date unknown)."))
P.append(pos("MSFT", "short", "short", "1682488994347773952", "stated", "weak",
    [ev("1682488994347773952", "an AU degenerate version of myself opened a $MSFT short today")],
    note="'AU' (alternate universe) framing reads as a joke; do not treat as a real short without other evidence."))
P.append(pos("BIRD", "stock", "long", "1682068545562378240", "stated", "inferred",
    [ev("1682068545562378240", "mildly peeved that i didn't have a larger $BIRD position")],
    note="Implies a small existing position; size and exit never stated."))
P.append(pos("PYPL", "stock", "long", "1688563957848743936", "stated", "explicit",
    [ev("1688563957848743936", "i own $PYPL now")], note="Exit never stated."))
P.append(pos("TME", "stock", "long", "1692224658505130232", "stated", "explicit",
    [ev("1692224658505130232", "while i'm still rebuilding my position")],
    [ev("1902049154085658864", "i am just as proud of my Tencent Music call")],
    note="Re-entry ('rebuilding'). Exit never stated; 2025-03-18 retrospective claims the call. Also in the 2023-12-12 China outperformance forecast [1734593893323415964]."))
P.append(pos("SCHW", "stock", "long", "1694008143435702665", "stated_intent", "weak",
    [ev("1694008143435702665", "considering rebuilding a position")], note="Consideration only; no fill stated."))
P.append(pos("DIS", "stock", "long", "1694729808054571094", "conditional_bid", "weak",
    [ev("1694729808054571094", "i'm a buyer of $DIS at $70/share")], entry_price=70,
    note="Conditional bid at $70; fill never stated."))
P.append(pos("GRVY", "stock", "long", "1696541443303825865", "stated", "explicit",
    [ev("1696541443303825865", "i added on the news.")],
    [ev("1840887409115873640", "$GRVY (exited)")], exit_post="1840887409115873640", exit_basis="stated",
    note="'added' implies an earlier position. Exit reported in the Q3 2024 review (posted 2024-09-30); the exact sale date in Q3 2024 is not given."))
P.append(pos("AMRK", "stock", "long", "1697628599535509990", "first_disclosed", "inferred",
    [ev("1697628599535509990", "still the best risk/reward opportunity on my radar"),
     ev("1854534281814520172", "adding to my position", quoted=True)],
    [ev("1854534281814520172", "turned out to be a great trade when silver spreads blew out")],
    exit_post="1854534281814520172", exit_basis="disclosed_after_inferred", confidence_exit="inferred",
    claimed_entry=claimed("1854534281814520172", why="2022-11-09 self-post 'adding to my position'"),
    note="Held before the window. Past-tense 'turned out to be a great trade' (2024-11-07) implies closed; sale date unknown."))
P.append(pos("GRUSF", "stock", "long", "1699227645102465102", "stated", "explicit",
    [ev("1699227645102465102", "finally pulled the trigger here and am now a $GRUSF shareholder")],
    [ev("1891681975938748627", "meanwhile $GRUSF is a 10x")],
    size=[sz("10% (2024-09-30 book)", B_2024_09_30), sz("6.1%", B_2024_10_22)],
    exit_window=window(B_2024_10_22, B_2025_04_02, ABS + " (2025-04-02 lists all >1% positions)"),
    note="OTC ticker for a Canadian-listed cannabis company (Grown Rogue). No sale stated; the 2025-02-18 '10x' remark may refer to the stock rather than the holding."))
P.append(pos("CIB", "stock", "long", "1701447340543078475", "stated", "explicit",
    [ev("1701447340543078475", "top 5 position for me"), ev("1743301646292341197", "$CIB still a top position, now a big winner")],
    size=[sz("top 5 position", "1701447340543078475"), sz("5%", B_2025_04_02)],
    exit_window=window(B_2025_04_02, B_2025_07_01, ABS),
    note="ADR (Grupo Cibest / Bancolombia, Colombia). Held before the window: 'my biggest losing position in portfolio percentage terms this year'."))
P.append(pos("MGM", "short", "short", "1702742531723911195", "stated", "inferred",
    [ev("1702742531723911195", "short $MGM")], note="Two-word call with 'nfa'; instrument and exit never stated."))
P.append(pos("GLNG", "stock", "long", "1703496981015130367", "stated", "inferred",
    [ev("1703496981015130367", "when @mintzmyer joins you on a trade")],
    note="Implies the account was already in $GLNG before mintzmyer's 2023-09-12 post. No size or exit."))
P.append(pos("JXN", "stock", "long", "1735697118193651745", "first_disclosed", "inferred",
    [ev("1735697118193651745", "$JXN +48% since i added it to my bets in March")],
    [ev("1830490306707587525", "gratz to everyone who held on to $JXN longer than me")],
    exit_post="1830490306707587525", exit_basis="disclosed_after", confidence_exit="inferred",
    note="'my bets' is the public My-Bets tracker (github.com/starfaerie/My-Bets); entry March 2023 (before the window). Exit happened some time after the December 2023 regulatory change; the 2024-09-02 post only discloses it."))
P.append(pos("GSL", "stock", "long", "1738064329856192559", "stated", "inferred",
    [ev("1738064329856192559", "got $GSL?")],
    size=[sz("0.5% (2024-09-30 book)", B_2024_09_30), sz("0.4%", B_2024_10_22)],
    exit_window=window(B_2024_10_22, B_2025_04_02, ABS),
    note="Also one of the 2022-12-20 'simple theses' scored on 2024-09-23 [1838065316796276929]."))
for t in ("TCEHY", "BIDU", "BABA"):
    P.append(pos(t, "stock", "long", "1743229653106803197", "stated", "explicit",
        [ev("1743229653106803197", "i'm buying $TCEHY, $BIDU, and $BABA. Chinese largecaps are now a 20% position for me and i'm still adding"),
         ev("1738068916763848853", "almost time to add Tencent to my China collection")],
        size=sz("20% combined (TCEHY+BIDU+BABA)", "1743229653106803197"), ticker_note="US OTC/ADR of a Chinese large cap.",
        note="The 2023-12-22 'China collection' remark implies China holdings already existed. No exit stated; none of the three appears in the 2024-09-30 or later books (2024-09-30 had 41% undisclosed)."))
P.append(pos("FXI", "stock", "long", "1737486130658820420", "recommendation", "weak",
    [ev("1737486130658820420", "keep calm and buy $FXI")], note="Imperative only; ETF."))
P.append(pos("BTCW.V", "stock", "long", "1748224903395025324", "hash_commitment_revealed", "inferred",
    [ev("1748224903395025324", "generational buying opportunity in BTCW.V today."),
     ev("1748224905710297256", "this was the best way i found to bet on the Bitcoin ETF approval")],
    [ev("1748224903395025324", "this alpha has now fully played out")],
    exit_post="1748224903395025324", exit_basis="inferred", confidence_exit="weak",
    entry_price=0.0343, claimed_entry=claimed("1748224903395025324", why="2023-02-03 SHA-256 commitment, revealed 2024-01-19"),
    ticker_note="TSX Venture (non-US), price stated in USD ('ask: $0.0343 USD').",
    note="Call encoded as a hash on 2023-02-03 and revealed on 2024-01-19. A position is implied ('the best way i found to bet'), not stated. 'fully played out' read as closed is an inference."))
P.append(pos("ENTG", "stock", "long", "1750334625006989798", "stated", "explicit",
    [ev("1750334625006989798", ">10% of my net worth is in $ENTG and $TSM"), ev("1750334626114175194", "not selling")],
    size=sz(">10% of net worth combined with TSM", "1750334625006989798"), note="Exit never stated; ENTG appears in no posted book."))
P.append(pos("TSM", "stock", "long", "1750334625006989798", "stated", "explicit",
    [ev("1750334625006989798", ">10% of my net worth is in $ENTG and $TSM"),
     ev("1847399974046487025", "i was smart enough to buy shares at the time")],
    size=[sz(">10% of net worth combined with ENTG", "1750334625006989798"), sz("9% (2024-09-30 book)", B_2024_09_30),
          sz("7.4%", B_2024_10_22), sz("5.1%", B_2025_04_02)],
    exit_window=window(B_2025_04_02, B_2025_07_01, ABS),
    claimed_entry={"date": qdate("1847399974046487025", "orrdavid")[0], "quoted_id": "1682112583212453890", "via_post": "1847399974046487025",
                   "basis": "2024-10-18 says it bought shares 'at the time' of orrdavid's quoted 2023-07-20 post; quoted_date taken from that quoted post's created_at"},
    note="On 2025-06-18 it still wrote 'you simply have to be long $TSMC' [1935407044087202205], yet TSM is missing from the 2025-07-01 list."))
# ---------------------------------------------------------------- 2024
P.append(pos("GEO", "call", "long", "1812704253263426009", "stated", "explicit",
    [ev("1812704253263426009", "what's about to be my best trade of the year"),
     ev("1812704253263426009", "you could make the same bet through $GEO calls", quoted=True)],
    [ev("1849569538276458827", "this has been a significant source of alpha for me this year")],
    claimed_entry={"date": qdate("1812704253263426009")[0], "quoted_id": "1809023609555624170", "via_post": "1812704253263426009",
                   "basis": "quoted self-post dated 2024-07-05: 'i put on the trade in the equity market because you could make the same bet through $GEO calls'"},
    note="Election-odds proxy trade. The quoted wording says the trade was put on in the equity market via $GEO calls. Strike, expiry and exit never stated."))
P.append(pos("U", "short", "short", "1834251198536581287", "stated", "inferred",
    [ev("1834251198536581287", "short $U, long $APP will continue to outperform")],
    note="Pair framing (short $U / long $APP). Whether a $U short was actually on is not stated."))
P.append(pos("MOB.ST", "stock", "long", "1840884002154057911", "first_disclosed", "explicit",
    [ev("1840884002154057911", "had some wild volatility in both directions this quarter thanks to $MOB.ST")],
    [ev("1840887409115873640", "$MOB.ST from ~14% weight at peak to 1%")],
    size=[sz("~14% at peak, trimmed to 1%", "1840887409115873640")],
    exit_window={"last_seen_held": "2024-09-30", "last_seen_post": "1840887409115873640", "first_absent": d(B_2024_10_22),
                 "first_absent_post": B_2024_10_22, "basis": ABS + " (2024-10-22 'current weights' list)"},
    ticker_note="Nasdaq Stockholm (non-US).",
    legs=[{"date": d("1840887409115873640"), "post": "1840887409115873640", "action": "trim ~14% -> 1% during Q3 2024"}]))
for t, w in (("CPH.TO", "1%"), ("COVCF", "1.5%"), ("RRGB", "1%")):
    base = dict(size=[sz(f"{w} at initiation (Q3 2024)", "1840887409115873640")])
    if t == "CPH.TO":
        base["size"] += [sz("0.7%", B_2024_10_22), sz("10.6%", B_2025_04_02), sz("largest position", B_2025_07_01),
                         sz("roughly 15% of LNW", "1953600042843222423")]
        P.append(pos(t, "stock", "long", "1840887409115873640", "stated", "explicit",
            [ev("1840887409115873640", "$CPH.TO 1%"), ev("1924290564335587399", "my only material positions are Cipher, Nintendo, and Coupang"),
             ev("1953600042843222423", "roughly 15% of my LNW")],
            exit_window=window("1953600042843222423", B_2026_02_06, ABS + "; 2026-02-06 book"),
            ticker_note="Toronto (non-US), Cipher Pharmaceuticals.", note="No sale stated.", **base))
    elif t == "COVCF":
        base["size"] += [sz("0.9%", B_2024_10_22), sz("1%", B_2025_04_02)]
        P.append(pos(t, "stock", "long", "1840887409115873640", "stated", "explicit",
            [ev("1840887409115873640", "$COVCF 1.5%"), ev(B_2025_07_01, "$COVCF")],
            exit_window=window(B_2025_07_01, B_2026_02_06, ABS), ticker_note="US OTC line of a non-US issuer.", **base))
    else:
        base["size"] += [sz("1%", B_2024_10_22)]
        P.append(pos(t, "stock", "long", "1840887409115873640", "stated", "explicit",
            [ev("1840887409115873640", "$RRGB 1%"),
             ev("1847838812971430239", "gratz to everyone with a lower cost basis on $RRGB than insiders")],
            exit_window=window(B_2024_10_22, B_2025_04_02, ABS),
            note="2024-10-20 calls it 'the fastest double i've ever had other than $WAL'.", **base))
P.append(pos("DAC", "stock", "long", B_2024_10_22, "first_disclosed", "explicit",
    [ev(B_2024_10_22, "$DAC 2%", quoted=True)], [ev(B_2024_10_22, "sold: $DAC")],
    exit_post=B_2024_10_22, exit_basis="stated", leg="1 of 2", size=sz("2% (2024-09-30 book)", B_2024_09_30),
    claimed_entry=claimed(B_2024_10_22, why="2024-09-30 book quoted inside the 2024-10-22 book"),
    note="Seen first in the 2024-09-30 book (quoted id 1840887410739003716, not a row in posts.jsonl); the 2024-10-22 book reports it sold."))
P.append(pos("DAC", "stock", "long", B_2025_04_02, "first_disclosed", "explicit",
    [ev(B_2025_04_02, "$DAC 2.4%")], leg="2 of 2", size=sz("2.4%", B_2025_04_02),
    exit_window=window(B_2025_04_02, B_2025_07_01, ABS), note="Re-entry some time between 2024-10-22 and 2025-04-02."))
P.append(pos("NTDOY", "stock", "long", B_2024_10_22, "first_disclosed", "explicit",
    [ev(B_2024_10_22, "$NTDOY 3%", quoted=True), ev(B_2024_10_22, "$NTDOY 2%"),
     ev("1880077559117029725", "i don't own enough $NTDOY"),
     ev(B_2025_05_19, "my only material positions are Cipher, Nintendo, and Coupang")],
    [ev("2052817098939015459", "finally bought back into $NTDOY")], leg="1 of 2",
    size=[sz("3% (2024-09-30 book)", B_2024_09_30), sz("2%", B_2024_10_22), sz("5.1%", B_2025_04_02), sz("3rd by weight", B_2025_07_01)],
    claimed_entry=claimed(B_2024_10_22, why="2024-09-30 book quoted inside the 2024-10-22 book"),
    exit_window=window(B_2025_07_01, B_2026_02_06, ABS + "; the 2026-05-08 'bought back into' confirms an exit"),
    ticker_note="US OTC ADR of Nintendo (7974.T).",
    note="Listed as a 'current best idea' on 2024-01-05 [1743229653106803197] without a holding statement."))
P.append(pos("NTDOY", "stock", "long", "2052817098939015459", "stated", "explicit",
    [ev("2052817098939015459", "finally bought back into $NTDOY. $10.50/share simply seemed egregious."),
     ev("2082110993606611098", "being up +10% in Nintendo instead"), ev(B_2026_09_04, "$NTDOY")],
    entry_price=10.50, leg="2 of 2", note="The 2026-07-28 post describes this buy as funded by selling memory. Still listed 2026-09-04; no exit."))
P.append(pos("CPNG", "stock", "long", B_2024_10_22, "first_disclosed", "explicit",
    [ev(B_2024_10_22, "$CPNG 12%", quoted=True), ev(B_2024_10_22, "$CPNG 8.3%"),
     ev(B_2025_05_19, "my only material positions are Cipher, Nintendo, and Coupang")],
    size=[sz("12% (2024-09-30 book)", B_2024_09_30), sz("8.3%", B_2024_10_22), sz("6.5%", B_2025_04_02), sz("2nd by weight", B_2025_07_01)],
    claimed_entry=claimed(B_2024_10_22, why="2024-09-30 book quoted inside the 2024-10-22 book"),
    exit_window=window(B_2025_07_01, B_2026_02_06, ABS),
    note="Listed as a 'current best idea' on 2024-01-05 [1743229653106803197]."))
P.append(pos("ACFN", "stock", "long", B_2024_10_22, "first_disclosed", "explicit",
    [ev(B_2024_10_22, "$ACFN 3%", quoted=True), ev(B_2026_09_04, "$ACFN")],
    size=[sz("3% (2024-09-30 book)", B_2024_09_30), sz("2.7%", B_2024_10_22), sz("2.5%", B_2025_04_02), sz("2%", B_2026_02_06), sz(">1%", B_2026_09_04)],
    claimed_entry=claimed(B_2024_10_22, why="2024-09-30 book quoted inside the 2024-10-22 book"),
    note="In every book from 2024-09-30 to 2026-09-04. Open."))
P.append(pos("CRL", "stock", "long", B_2024_10_22, "first_disclosed", "explicit",
    [ev(B_2024_10_22, "$CRL 0.5%", quoted=True), ev(B_2024_10_22, "$CRL 0.4%")],
    size=[sz("0.5% (2024-09-30 book)", B_2024_09_30), sz("0.4%", B_2024_10_22)],
    claimed_entry=claimed(B_2024_10_22, why="2024-09-30 book quoted inside the 2024-10-22 book"),
    exit_window=window(B_2024_10_22, B_2025_04_02, ABS), note="One of the 2023-06-12 'oligopolies' best ideas [1930257651524649434]."))
# APP legs
P.append(pos("APP", "stock", "long", "1828253583361630555", "first_disclosed", "explicit",
    [ev("1828253583361630555", "it's been my biggest absolute $ and % winner the past couple years"),
     ev("2114383076239503412", "which I put on at a 2.5% weight under $12/share"),
     ev("1854370232724234734", "i'm not selling a share")],
    [ev("1866149181506597201", "within 2% and 90 minutes from the all time high"),
     ev("1866148516441075761", "i will never time the market this perfectly again in my life"),
     ev("1894763674654376113", "i literally bought back my entire position")],
    exit_post="1866149181506597201", exit_basis="inferred", confidence_exit="inferred", entry_price=12, leg="1 of 5",
    size=[sz("2.5% initial weight", "2114383076239503412"), sz("11% (2024-09-30 book)", B_2024_09_30), sz("9.1%", B_2024_10_22),
          sz("second largest position", "1854370232724234734")],
    note="entry_price_stated 12 is the stated upper bound ('under $12/share', said 2026-10-25); 'Holding equity instead of otm options on $APP when it was $11/share' [2047475887646621990]. The buy predates the window (APP last traded near $11-12 around Dec 2022-Jan 2023, consistent with the quoted 2022-12-09 '$META and $APP are both bets'). Exit 2024-12-09 is inferred from 'within 17% and 3 weeks of the all time low / within 2% and 90 minutes from the all time high / the $APP trade was unreal', and the 2025-02-26 'bought back my entire position' means a full exit happened before then. 2023-07-28 'sold out on a sentiment swing for +100% gain' [1684972690615242752] may cover an earlier APP and/or META round trip; unresolved."))
P.append(pos("APP", "stock", "long", "1894763674654376113", "stated", "explicit",
    [ev("1894763674654376113", "$APP under $300??? lol i literally bought back my entire position")],
    [ev("1899150866281795614", "with the exception of briefly playing the dead cat boing on $APP")],
    exit_post="1899150866281795614", exit_basis="inferred", confidence_exit="inferred", entry_price=300, leg="2 of 5",
    note="entry_price_stated 300 is an upper bound ('under $300'). 'briefly playing the dead cat boing' (2025-03-10) implies it was sold again by then."))
P.append(pos("APP", "stock", "long", B_2025_04_02, "first_disclosed", "explicit",
    [ev(B_2025_04_02, "$APP 5.1%")], leg="3 of 5", size=sz("5.1%", B_2025_04_02),
    exit_window=window(B_2025_04_02, B_2025_05_19, "not among 'my only material positions' on 2025-05-19 and absent from the 2025-07-01 list"),
    note="On 2025-03-27 it wished for APP 'below $180' so it could 'park my money in AppLovin' [1905347772074873322]."))
P.append(pos("APP", "stock", "long", B_2026_02_06, "first_disclosed", "explicit",
    [ev(B_2026_02_06, "$APP 31%"), ev("2019121210156830730", "whatever you have to do to own more $APP"),
     ev("2085106834030158102", "held anyway in case i was wrong")],
    [ev("2085106835464593835", "obviously correct thing to do was to completely sell out of $APP for memory and i didn't do it")],
    leg="4 of 5", size=[sz("31%", B_2026_02_06)],
    exit_window=window("2085106834030158102", B_2026_09_04, ABS + " (could also sit in an 'undisclosed' line)"),
    note="Re-entered some time between 2025-07-01 and 2026-02-06. Held through the 2026-08-05 miss ('-6% to my LNW on this release')."))
P.append(pos("APP", "stock", "long", B_2026_11_04, "first_disclosed", "explicit",
    [ev(B_2026_11_04, "grown to 35% weight between the two of them"),
     ev("2117370896268898605", "give me $APP under $180 again so i can put on a 30% weight"),
     ev("2118360364153012240", "+10% today thanks to the lovely people at $APP and $CCLD")],
    leg="5 of 5", size=sz("35% combined with RELY", B_2026_11_04),
    note="Re-entered some time between 2026-09-04 and 2026-11-04 ('under $180 again' hints at a recent buy below $180). On 2026-11-25 it says 'continue to sit out the market in cash' [2125440798909251770], which conflicts with a 35% APP+RELY weight three weeks earlier; whether APP was sold in between is not stated."))
P.append(pos("META", "stock", "long", "1684972690615242752", "first_disclosed_at_exit", "inferred",
    [ev("1684972690615242752", "huh. i expected to be underwater on $APP and $META much longer than this", quoted=True)],
    [ev("1684972690615242752", "sold out on a sentiment swing for +100% gain")],
    exit_post="1684972690615242752", exit_basis="disclosed_after_inferred", confidence_exit="inferred", leg="1 of 2",
    claimed_entry=claimed("1684972690615242752", why="2023-01-17 self-post quoted inside 2023-07-28; 2022-12-09 'my $META and $APP are both bets' quoted in 1848365500075479457"),
    note="The 2023-07-28 post does not name which ad-platform holding it sold for +100% (META, APP or both); listed under META because APP was held continuously (see APP leg 1). The sale predates the window."))
P.append(pos("META", "stock", "long", "2037216555843674518", "stated", "explicit",
    [ev("2037216555843674518", "go all in on $NVDA, $META, and SK Hynix"), ev("2037216555843674518", "(i'm already up to 30% weight)"),
     ev("2032639447469318355", "You just have to own it")],
    [ev("2070928172456214776", "for that reason I'm out")], exit_post="2070928172456214776", exit_basis="inferred", confidence_exit="weak",
    leg="2 of 2", size=sz("30% combined with NVDA and SK Hynix", "2037216555843674518"),
    note="The 'I'm out' on 2026-06-27 is a reply under a post about the $MAGS/hyperscaler capex trade; reading it as an exit from META is an inference. META is absent from the 2026-09-04 book."))
P.append(pos("TLN", "stock", "long", "1841863943708455080", "first_disclosed_at_exit", "inferred",
    [ev("2088613083057209413", "buying $TLN out of Bk"), ev("1841863943708455080", "buying in was still one of my best % calls ever")],
    [ev("1841863943708455080", "i still think i made the right call exiting the position")],
    exit_post="1841863943708455080", exit_basis="disclosed_after", leg="1 of 2",
    note="This 2024-10-03 reply about 'the datacenter IPP trade' ($VST, $CEG, $TLN) says it exited 'my position'. Treating that position as TLN rests on the 2026-08-15 'buying $TLN out of Bk'. Entry is before the window (Talen emerged from bankruptcy in 2023). Exit date unknown, on or before 2024-10-03."))
P.append(pos("TLN", "stock", "long", "1857061347999047837", "stated", "weak",
    [ev("1857061347999047837", "can't believe there's still alpha in buying $TLN")],
    [ev("1893052520177476063", "this is why i sold out of everything i own that's datacenter capex related a couple weeks ago")],
    exit_post="1893052520177476063", exit_basis="inferred", confidence_exit="weak", leg="2 of 2",
    note="It is unclear whether this 2024-11-14 remark records a re-entry. If one happened, the 2025-02-21 'sold out of everything ... datacenter capex related' would cover it."))
P.append(pos("PSIX", "stock", "long", "1849098954580848766", "inferred", "weak",
    [ev("1849098954580848766", "$PSIX -20% today for non-fundamental reasons. worth looking at."),
     ev("1849583316229554597", "what can i say except")], leg="1 of 2",
    note="Only the 'once again a buyer' of 2024-12-13 implies an October 2024 buy. No exit stated for this leg."))
P.append(pos("PSIX", "stock", "long", "1867593633697808604", "stated", "explicit",
    [ev("1867593633697808604", "I am once again a buyer")],
    [ev("1877043951464505499", "sold out of my entire $PSIX position")], exit_post="1877043951464505499", exit_basis="stated", leg="2 of 2",
    note="2025-07-01: 'largest contributors YTD were $TSSI and $PSIX which i no longer own'."))
P.append(pos("VSCO", "stock", "long", "1978690320272388267", "first_disclosed", "inferred",
    [ev("1978690320272388267", "two years in a row now where buying $VSCO before the show was an incredible trade"),
     ev("1863626338633978340", "$VSCO +46% since this tweet")],
    note="Two trades, each bought before the October fashion show (2024 and 2025); dates, sizes and exits not stated. The 2024-12-02 '+46% since this tweet' measures from visakanv's 2024-10-17 post."))
P.append(pos("TPR", "stock", "long", "1861481017279648096", "first_disclosed", "weak",
    [ev("1861481017279648096", "+20% already"), ev("1885334311777313079", "this is up an uncorrelated 50% in 3 months")],
    claimed_entry=claimed("1861481017279648096", why="2024-11-07 Tapestry thesis post quoted inside 2024-11-26"),
    note="Thesis and running returns are posted, but a holding is never stated."))
P.append(pos("SWI", "stock", "long", "1887881160052867122", "recommendation", "weak",
    [ev("1887881160052867122", "no one i pitched this to cared")],
    claimed_entry=claimed("1887881160052867122", why="2024-12-06 $SWI pitch quoted inside 2025-02-07"),
    note="A pitch; holding never stated."))
P.append(pos("CANNABIS basket", "stock", "long", "1856025524654743584", "stated", "inferred",
    [ev("1856025524654743584", "(i'm a buyer)"), ev("1856348569873027261", "$CRON is +17%")],
    ticker_note="Unspecified tickers; $CRON is discussed alongside.",
    note="Sector-level 'i'm a buyer' (2024-11-11). The 2024-12-18 '+100% today while the market is -4% and $MSOS is -2%' [1869518699276931499] does not say which name rose."))
# ---------------------------------------------------------------- 2025
P.append(pos("DATACENTER CAPEX basket", "stock", "long", "1893052520177476063", "first_disclosed_at_exit", "explicit",
    [ev("1893052520177476063", "everything i own that's datacenter capex related")],
    [ev("1893052520177476063", "i sold out of everything i own that's datacenter capex related a couple weeks ago"),
     ev("1899113582891249899", "i was smart enough to see the sentiment turn coming and sell everything")],
    exit_post="1893052520177476063", exit_basis="disclosed_after", ticker_note="Unspecified names; the NVDA OTM calls of 2025-01-27 are probably among them.",
    note="Sale took place 'a couple weeks' before 2025-02-21, so about 2025-02-07. Holdings are not named."))
P.append(pos("NVDA", "call", "long", "1973755921382932881", "stated", "explicit",
    [ev("1973755921382932881", "i bought OTM $NVDA options for the first time ever today", quoted=True)],
    [ev("1884799481369035103", "the long NVDA trade is dead money after this comment"),
     ev("1893052520177476063", "i sold out of everything i own that's datacenter capex related a couple weeks ago")],
    exit_post="1893052520177476063", exit_basis="inferred", confidence_exit="inferred", leg="options 2025",
    claimed_entry={"date": qdate("1973755921382932881")[0], "quoted_id": "1883902034723930464", "via_post": "1973755921382932881",
                   "basis": "quoted self-post dated 2025-01-27 (the DeepSeek selloff day); not a row in posts.jsonl"},
    note="'options' are read as calls because of 'OTM' and the bullish context; strike and expiry not stated."))
P.append(pos("NVDA", "stock", "long", B_2026_02_06, "first_disclosed", "explicit",
    [ev(B_2026_02_06, "$NVDA 7%"), ev("2037216555843674518", "(i'm already up to 30% weight)"),
     ev("2091649861586456784", "buy more Nvidia and memory"), ev(B_2026_09_04, "$NVDA")],
    leg="stock 2026", size=[sz("7%", B_2026_02_06), sz("30% combined with META and SK Hynix", "2037216555843674518")],
    note="No exit stated. 2026-11-06 'crazy timing in hindsight for me to sell beta' [2118526296431137146] may include NVDA; not stated."))
P.append(pos("NVDA", "call", "long", "2124916147145588802", "inferred", "inferred",
    [ev("2124916147145588802", "i did not buy far enough OTM to make a million dollars")], leg="options 2026-11",
    note="Reply to a report of 0DTE $NVDA calls bought on Friday 2026-11-20 that paid out on 2026-11-23 (Jensen Huang's return). It implies the account bought NVDA calls, not far enough OTM. Strike, expiry and P&L not stated."))
P.append(pos("MRVI", "stock", "long", "1888232444148494705", "inferred", "inferred",
    [ev("1888232444148494705", "$MRVI will be one of the greatest wealth compounding vehicles of all time")],
    [ev("1894399223581258134", "$MRVI my first L of the year"),
     ev("1902948344256946452", "realize a small loss early without getting emotionally attached to a position")],
    exit_post="1894399223581258134", exit_basis="stated", confidence_exit="explicit",
    note="Holding is implied by the realized 'L'. The entry date is unknown and may be well before 2025-02-08. 2025-07-01: 'only L of the year so far $MRVI'."))
P.append(pos("DAVA", "stock", "long", "1892593869595775099", "stated", "inferred",
    [ev("1892593869595775099", "i think it's finally time to start buying $DAVA")], note="Absent from the 2025-04-02 >1% list. No exit."))
P.append(pos("AER", "stock", "long", "1896937660188598488", "stated", "explicit",
    [ev("1896937660188598488", "now a 1% position (crazy, i know)")], size=sz("1%", "1896937660188598488"),
    exit_window=window("1896937660188598488", B_2025_04_02, "absent from 2025-04-02 list of positions >1% (which includes 1.0% lines), so sold or below 1%"),
    note="Ireland-domiciled, NYSE-listed."))
P.append(pos("REGN", "stock", "long", "1896605521752555865", "stated", "inferred",
    [ev("1896605521752555865", "keep calm and buy Regeneron"), ev("1928469044744577233", "adding again"), ev(B_2025_07_01, "$REGN")],
    size=[sz("3%", B_2025_04_02), sz("2% after adding", "1928469044744577233")],
    exit_window=window(B_2025_07_01, B_2026_02_06, ABS),
    legs=[{"date": d("1928469044744577233"), "post": "1928469044744577233", "action": "add ('adding again ... up to a 2% position now')"}],
    note="3% on 2025-04-02 but 'up to a 2% position now' after adding on 2025-05-30, so the price fell or it was trimmed in between. 2025-05-30 reaction: '-19%!'."))
P.append(pos("RUSSIAN BANK (unnamed)", "stock", "long", "1896248420064792727", "stated_intent", "weak",
    [ev("1896248420064792727", "i think it's time to buy a certain Russian bank")], ticker_note="Unnamed; not identifiable from the post.",
    note="Intent only."))
P.append(pos("GOOG", "stock", "long", "1899150866281795614", "stated", "explicit",
    [ev("1899150866281795614", "bought $GOOG and $AMZN for the first time ever"), ev("1948117088670826771", "(i own it)"),
     ev("2006224544823152804", "why do i own anything other than $GOOGL")],
    [ev("2085049377702481996", "i told him when Jeff Dean left and Demis was no longer leading DeepMind")],
    size=[sz("1%", B_2025_04_02), sz("4th by weight", B_2025_07_01)],
    exit_window=window("2006224544823152804", B_2026_02_06, ABS),
    note="2026-08-05 recalls the stated sell trigger (Jeff Dean leaving) firing, but GOOG had already dropped out of the 2026-02-06 book. Whether it was re-bought before August 2026 is unknown."))
P.append(pos("GOOGL", "call", "long", "1963005357212729577", "inferred", "weak",
    [ev("1963005357212729577", "singing the praises of past me for actually buying call options for the first time i think since 2022")],
    ticker_note="Underlying inferred from the quoted post (benchmarking against $GOOGL).",
    note="Conflicts with the 2025-01-27 'bought OTM $NVDA options for the first time ever'. Underlying, strike and dates are uncertain."))
P.append(pos("AMZN", "stock", "long", "1899150866281795614", "stated", "explicit",
    [ev("1899150866281795614", "bought $GOOG and $AMZN for the first time ever")], leg="1 of 2", size=sz("3.5%", B_2025_04_02),
    exit_window=window(B_2025_04_02, B_2025_07_01, ABS)))
P.append(pos("AMZN", "stock", "long", "2085049377702481996", "inferred", "inferred",
    [ev("2085049377702481996", "i guess buy Amazon?"), ev(B_2026_09_04, "$AMZN")], leg="2 of 2",
    note="The 2026-09-04 book confirms a holding; the buy date is uncertain (on or after 2026-08-05)."))
for t, w in (("VAL", "1.4%"), ("TDW", "1.3%"), ("FOA", "1.2%"), ("HII", "1.2%")):
    txt = {"VAL": "$VAL 2026 40c 1.4%", "TDW": "$TDW 1.3%", "FOA": "$FOA 1.2%", "HII": "$HII 1.2%"}[t]
    P.append(pos(t, "call" if t == "VAL" else "stock", "long", B_2025_04_02, "first_disclosed", "explicit",
        [ev(B_2025_04_02, txt)], size=sz(w, B_2025_04_02), exit_window=window(B_2025_04_02, B_2025_07_01, ABS),
        ticker_note=("2026 expiry $40 strike calls ('$VAL 2026 40c')" if t == "VAL" else None),
        note={"VAL": "Options. Offshore-drilling context: 2025-03-04 [1896945031992484147].",
              "TDW": "Also in the 2023-03-03 TDW/TS/OEC basket poll scored 2023-08-10 [1689518685545975813].",
              "FOA": "Same-day endorsement of Premski_SGP's $FOA note on 2025-02-25 [1894263776892928309].",
              "HII": None}[t]))
P.append(pos("AMTM", "stock", "long", B_2025_04_02, "first_disclosed", "explicit",
    [ev(B_2025_04_02, "$AMTM 1%"), ev(B_2026_02_06, "$AMTM 2.5%")], size=[sz("1%", B_2025_04_02), sz("2.5%", B_2026_02_06)],
    exit_window=window(B_2026_02_06, B_2026_09_04, ABS)))
P.append(pos("OWN STARTUP (private)", "private", "long", "1907225872282915216", "stated_intent", "inferred",
    [ev("1907225872282915216", "most to all of my liquid net worth will be going into my startup")],
    ticker_note="The account's own robotics/data company (named KikiTora in 2025 posts; inheritance.ai is linked in 2026). Not tradable.",
    note="A capital allocation, not a market position. Kept so liquid-book weights after 2025-04 can be read in context."))
P.append(pos("DMGI.V", "stock", "long", B_2025_07_01, "first_disclosed", "explicit", [ev(B_2025_07_01, "$DMGI.V")],
    exit_window=window(B_2025_07_01, B_2026_02_06, ABS), ticker_note="TSX Venture (non-US), DMG Blockchain."))
P.append(pos("TGTX", "stock", "long", B_2025_07_01, "first_disclosed", "explicit", [ev(B_2025_07_01, "$TGTX"), ev(B_2026_02_06, "$TGTX 2.5%")],
    size=sz("2.5%", B_2026_02_06), exit_window=window(B_2026_02_06, B_2026_09_04, ABS)))
P.append(pos("HROW", "stock", "long", B_2025_07_01, "first_disclosed", "explicit",
    [ev(B_2025_07_01, "$HROW"), ev("1970502652774760914", "i joined the $HROW party two years late"), ev(B_2026_09_04, "$HROW")],
    size=[sz("3%", B_2026_02_06), sz(">1%", B_2026_09_04)],
    note="Open. 2026-11-10: 'stock is probably a 3x over the next 4 years from here' [2119955290154291353]."))
P.append(pos("ARBKL", "stock", "long", B_2025_07_01, "first_disclosed", "explicit",
    [ev(B_2025_07_01, "$ARBKL"), ev("1999727800392253520", "imho put in a limit bid at $2.60/share", quoted=True)],
    [ev("1999727800392253520", "$ARBKL traded -60% from my cost basis before finally exiting for a 108% return less than 6 months later")],
    exit_post="1999727800392253520", exit_basis="disclosed_after", entry_price=2.60,
    ticker_note="Argo Blockchain exchange-listed notes (debt instrument, US-listed baby bond; issuer is UK).",
    note="entry_price_stated 2.60 is the limit bid suggested on 2025-06-30 (quoted id 1939768680747081759, not in posts.jsonl), not a confirmed fill. The exit was disclosed 2025-12-13 and happened 'less than 6 months' after entry. A 2023-12-27 post already advocated buying $ARBKL debt [1740060714461757833]."))
P.append(pos("TSSI", "stock", "long", B_2025_07_01, "first_disclosed_at_exit", "explicit",
    [ev(B_2025_07_01, "largest contributors YTD were $TSSI and $PSIX which i no longer own")],
    [ev(B_2025_07_01, "which i no longer own")], exit_post=B_2025_07_01, exit_basis="disclosed_after", leg="stock",
    note="Bought and sold within 2025-01-01..2025-07-01; dates not stated."))
P.append(pos("TSSI", "put", "short", "1943760667271737786", "stated", "inferred",
    [ev("1943760667271737786", "what a beautiful day to sell puts on $TSSI")], leg="short puts",
    note="Short puts give bullish exposure. Strike and expiry not stated; the post carries 'nfa'."))
P.append(pos("RELY", "stock", "long", "1845179197171319075", "stated", "explicit",
    [ev("1845179197171319075", "i'm a buyer again"), ev("1938332883816743116", "i'm a buyer of $RELY again"),
     ev("1976309012296761706", "now my third largest position"), ev("2024773945195651301", "scale into a position 4-6 months too early"),
     ev(B_2026_11_04, "grown to 35% weight between the two of them")],
    size=[sz("2.5%", B_2025_04_02), sz("third largest", "1976309012296761706"), sz("10%", B_2026_02_06), sz("largest after cash", B_2026_09_04),
          sz("35% combined with APP", B_2026_11_04)],
    legs=[{"date": d("1845179197171319075"), "post": "1845179197171319075", "action": "buy ('buyer again')"},
          {"date": d("1938332883816743116"), "post": "1938332883816743116", "action": "buy ('buyer of $RELY again')"}],
    note="'again' (2024-10-12) means an earlier holding (a 2023-04-24 'best long term idea' is quoted). RELY is absent from the 2025-07-01 list even though a buy was posted on 2025-06-26; it may sit in that list's 'undisclosed' line. No exit; see the APP leg 5 note on the 2026-11-25 'sit out the market in cash'."))
P.append(pos("NNI", "stock", "long", "1953289685859455055", "stated", "inferred",
    [ev("1953289685859455055", "it feels really weird to own"), ev(B_2026_02_06, "$NNI 18%")],
    size=sz("18%", B_2026_02_06), exit_window=window(B_2026_02_06, B_2026_09_04, ABS)))
P.append(pos("SATS", "stock", "long", "1960855385696559586", "stated", "explicit",
    [ev("1960855385696559586", "buying literal hours after the press release still generated an 18% uncorrelated return within 24 hours"),
     ev("1965025724794130748", "an uncorrelated double in two weeks")],
    claimed_entry={"date": qdate("1960855385696559586", "1_adoy")[0], "quoted_id": "1960434314367082575", "via_post": "1960855385696559586",
                   "basis": "bought 'hours after the press release' discussed in the quoted 1_adoy post dated 2025-08-26"},
    note="Still bullish on 2025-09-08 ('still more near term upside'). No exit."))
P.append(pos("MU", "stock", "long", "1891843512330506559", "stated", "inferred",
    [ev("1891843512330506559", "this is your sign that it is finally time to buy Micron"),
     ev("1965802140703850705", "went -35% before up +50% from here"), ev("2045691279942828200", "I knew I was right")],
    [ev("2052078363637158196", "realized all gains in neocloud and memory today")],
    exit_post="2052078363637158196", exit_basis="stated", confidence_exit="inferred",
    note="Holding is inferred from the imperative plus later P&L-style tracking. The 2026-05-06 exit covers 'memory' as a whole; MU is not named."))
P.append(pos("MEMORY basket", "stock", "long", "1997013761065091429", "stated", "inferred",
    [ev("1997013761065091429", "First long memory now short publishers")],
    [ev("2052078363637158196", "realized all gains in neocloud and memory today"),
     ev("2082110993606611098", "it is so satisfying being mocked for selling memory to buy Nintendo")],
    exit_post="2052078363637158196", exit_basis="stated", leg="1 of 2",
    ticker_note="Names not itemised; SK Hynix, Micron, Samsung and Sandisk are the names it discusses (e.g. 2051915823066103817).",
    note="Parent row for the memory exposure. The SK Hynix and MU rows overlap with it; do not double count."))
P.append(pos("MEMORY basket", "stock", "long", "2082110993606611098", "stated", "explicit",
    [ev("2082110993606611098", "today buying memory again from degenerates getting liquidated"),
     ev("2084699182959673832", "gifts in $SNDK and $SKHY")], leg="2 of 2",
    note="Re-entry 2026-07-28. SKHY is listed on 2026-09-04. No exit stated; the 2026-11-06 'sell beta' may cover it."))
P.append(pos("SKHY", "stock", "long", "2037216555843674518", "stated", "explicit",
    [ev("2037216555843674518", "go all in on $NVDA, $META, and SK Hynix"), ev("2037216555843674518", "(i'm already up to 30% weight)")],
    [ev("2052078363637158196", "realized all gains in neocloud and memory today")], exit_post="2052078363637158196", exit_basis="stated",
    confidence_exit="inferred", leg="1 of 2", size=sz("30% combined with NVDA and META", "2037216555843674518"),
    ticker_note="SK Hynix (000660.KS, Korea); the account writes the cashtag as $SKHY.",
    note="Exit inferred from the 'memory' realization on 2026-05-06."))
P.append(pos("SKHY", "stock", "long", "2084699182959673832", "stated", "inferred",
    [ev("2084699182959673832", "gifts in $SNDK and $SKHY"), ev(B_2026_09_04, "$SKHY")], leg="2 of 2",
    ticker_note="SK Hynix (000660.KS); cashtag $SKHY as written.",
    note="The re-entry date is probably 2026-07-28 ('buying memory again')."))
P.append(pos("SNDK", "stock", "long", "2084699182959673832", "stated", "inferred",
    [ev("2084699182959673832", "gifts in $SNDK and $SKHY")], note="Part of the 2026-07-28 memory re-entry. Not listed 2026-09-04 (>1%)."))
P.append(pos("NEOCLOUD basket (CRWV inferred)", "stock", "long", "2052078363637158196", "first_disclosed_at_exit", "explicit",
    [ev("2052078363637158196", "realized all gains in neocloud")],
    [ev("2052078363637158196", "realized all gains in neocloud and memory today"), ev("2054209619992662299", "$CRWV -30% since. occasionally i make good decisions")],
    exit_post="2052078363637158196", exit_basis="stated",
    note="Names are not given; CRWV is inferred from the 2026-05-12 follow-up. On 2025-10-14 it had told readers to 'take your neo cloud exposure down to at least 0' [1978115478527586350], so this is probably a later re-entry."))
P.append(pos("SHORT DATACENTER FACTOR", "short", "short", "1990606919581802593", "stated", "weak",
    [ev("1990606919581802593", "it was time to short the datacenter factor")],
    note="Says it told its network to short and considered an SPV it did not form ('congrats to everyone who joined'). A personal short is not stated."))
P.append(pos("SCIENTIFIC PUBLISHERS basket", "short", "short", "1997013761065091429", "stated", "inferred",
    [ev("1997013761065091429", "now short publishers")],
    ticker_note="The quoted wolfejosh pitch names Wiley, Elsevier (RELX) and Springer Nature; which ones the account shorted is not stated.",
    note="No exit stated."))
P.append(pos("QURE", "stock", "long", "1985331353983045636", "stated", "inferred",
    [ev("1985331353983045636", "today i was rug pulled by the FDA"), ev("1986848310318277063", "$RELY + $QURE responsible for almost the entire drawdown"),
     ev("1970865558527840270", "$qure casually announcing that they nearly cured Huntington's")],
    [ev("2104911896780644593", "the only miracle was that I made way more money than I deserved to owning the stock")],
    leg="1 of 2",
    note="Holding is evident from 2025-11-03; the Sept 2025 celebration suggests it was held before then. The 2026-09-29 past tense suggests the position was gone or cut; no sale is stated. Not in the 2026-02-06 or 2026-09-04 >1% lists."))
P.append(pos("QURE", "stock", "long", "2125440798909251770", "stated_intent", "weak",
    [ev("2125440798909251770", "slowly accumulating $QURE doesn't seem dumb")], leg="2 of 2",
    note="Framed as an idea for others ('if you absolutely can't help yourself'); its own accumulation is not stated."))
P.append(pos("NTLA", "stock", "long", "1982858252061950431", "first_disclosed", "inferred",
    [ev("1982858252061950431", "my second L of the year"), ev("1986848723151036911", "$NTLA")],
    note="'my second L' quotes its own 2025-10-08 endorsement of JKeynesAlpha's $NTLA call [1975946313243197540], which implies a holding. Entry and exit not stated."))
P.append(pos("TWST", "stock", "long", B_2026_02_06, "first_disclosed", "explicit",
    [ev(B_2026_02_06, "$TWST 9.5%"), ev("1973792501967581328", "you simply have to own it"),
     ev("2090088625195356241", "between $TWST, $PSNL, $HROW, and $TEM what a Beautiful year it has been")],
    size=sz("9.5%", B_2026_02_06), exit_window=window("2090088625195356241", B_2026_09_04, ABS),
    note="Possibly held from about 2025-10-02 ('you simply have to own it'). Not listed 2026-09-04. On 2026-09-17 it quoted MartinShkreli's '$TWST is a short' with no comment [2100603910054432942]."))
P.append(pos("PSNL", "stock", "long", "2090088625195356241", "inferred", "inferred",
    [ev("2090088625195356241", "between $TWST, $PSNL, $HROW, and $TEM what a Beautiful year it has been"),
     ev("2079458386408812931", "$PSNL acquisition price is too cheap by at least 80%")],
    note="Being acquired as of 2026-07-21 ('just buy the acquirer'; the acquirer is not named)."))
P.append(pos("TEM", "stock", "long", "2090088625195356241", "inferred", "inferred",
    [ev("2090088625195356241", "between $TWST, $PSNL, $HROW, and $TEM what a Beautiful year it has been")], note="Holding is implied only."))
P.append(pos("ADBE", "stock", "long", "2014044628828184608", "stated", "explicit",
    [ev("2014044628828184608", "I bumped my $ADBE up from a 2% to a 5% position"), ev("2018760073569599774", "$ADBE now an 8% position")],
    [ev(B_2026_02_06, "cut the entire position")], exit_post=B_2026_02_06, exit_basis="stated",
    size=[sz("2% -> 5%", "2014044628828184608"), sz("8%", "2018760073569599774")],
    legs=[{"date": d("2014044628828184608"), "post": "2014044628828184608", "action": "add 2% -> 5% (the 2% existed before)"},
          {"date": d("2018760073569599774"), "post": "2018760073569599774", "action": "add to 8%"},
          {"date": d(B_2026_02_06), "post": B_2026_02_06, "action": "exit ('cut the entire position')"}],
    note="Exit reason: 'was betting on the factor bounce (which happened) / figured it would outperform its basket (which didn't happen)'. The original 2% entry date is unknown (2025-01-17 'whoa when did $ADBE get so cheap' [1880285279896105463])."))
P.append(pos("ASML", "stock", "long", B_2026_02_06, "first_disclosed", "explicit", [ev(B_2026_02_06, "$ASML 1.5%")],
    size=sz("1.5%", B_2026_02_06), exit_window=window(B_2026_02_06, B_2026_09_04, ABS), ticker_note="US listing of a Netherlands issuer."))
P.append(pos("RGEN", "stock", "long", B_2026_02_06, "first_disclosed", "explicit", [ev(B_2026_02_06, "$RGEN 2%")],
    size=sz("2%", B_2026_02_06), exit_window=window(B_2026_02_06, B_2026_09_04, ABS)))
P.append(pos("SPACEX (private secondaries)", "private", "long", "2017005331109597600", "first_disclosed_at_exit", "explicit",
    [ev("2017005331109597600", "since selling my SpaceX secondaries last year")],
    [ev("2017005331109597600", "first twinge of regret i've felt since selling my SpaceX secondaries last year")],
    exit_post="2017005331109597600", exit_basis="disclosed_after",
    note="Sold some time in 2025 ('last year', posted 2026-01-29). Entry not stated. After the IPO, on 2026-08-04: '$SPCX ... i don't own the stock' [2084789281206464704]."))
P.append(pos("GTLB", "short", "short", "2023127726283272258", "stated", "weak",
    [ev("2023127726283272258", "It's a short"), ev("2074715078872707409", "the terminal value of $GTLB is zero")],
    note="States a view ('It's a short'), not a position. On 2025-08-14 it said it never owned GTLB long: '(i don't own it and that's probably dumb of me)' [1955849648784204054]."))
P.append(pos("KOREA index", "stock", "long", "2018413940586537234", "inferred", "weak",
    [ev("2018413940586537234", "Everyone owns the Korean index in size, right?")], ticker_note="Unspecified vehicle (e.g. EWY).",
    note="Rhetorical; a holding is not stated."))
P.append(pos("PRECIGENETICS (private)", "private", "long", "2115829606293053917", "stated", "explicit",
    [ev("2115829606293053917", "you should give all your money to @Precigenetics (I have)"),
     ev("2053534148481130882", "you just have to be long @precigenetics and @parmita")],
    note="Private company. The amount is not stated."))
P.append(pos("AI SOFTWARE basket (SNOW, DDOG)", "stock", "long", "2070928172456214776", "stated", "inferred",
    [ev("2070928172456214776", "easier to own the AI beneficiary software basket from here. $SNOW and $DDOG two clear early winners"),
     ev("2072321614889554211", "AI software winners basket is +3% within 10 minutes")],
    note="'easier to own' (2026-06-27) and tracking the basket's moves (2026-07-01) suggest a holding; not stated. Neither name is in the 2026-09-04 book."))
P.append(pos("QXO", "stock", "long", "2084699182959673832", "first_disclosed", "inferred",
    [ev("2084699182959673832", "shoutout to @AdamB1438 for the timely flag on $QXO"), ev(B_2026_09_04, "$QXO")],
    note="Named among the gains in a 'my entire portfolio is up 13.5%' post. Listed 2026-09-04. Open."))
P.append(pos("HARVEY (private secondaries)", "private", "long", "2091650748341760019", "conditional_bid", "weak",
    [ev("2091650748341760019", "if anyone is selling Harvey secondaries i'm a buyer"), ev("2117878324659958167", "I'm still a buyer of Harvey secondaries btw!")],
    note="Standing bid; no fill stated."))
P.append(pos("TAN", "stock", "long", "2117635166785138733", "stated", "explicit",
    [ev("2117635166785138733", "suddenly feeling very uncreative for buying $TAN to make the same bet")],
    [ev("2117998945876213903", "it worked out")],
    note="A hedge against a Democratic election win, per the quoted WinstonV99 post. 'it worked out' (2026-11-04) reports a gain, not an exit. ETF."))
P.append(pos("TEXAS DATACENTER exposure", "private", "long", "2117801715680543132", "first_disclosed_at_exit", "inferred",
    [ev("2117801715680543132", "Will be selling all exposure to Texas datacenters")],
    [ev("2117801715680543132", "Will be selling all exposure to Texas datacenters in short order")],
    exit_post="2117801715680543132", exit_basis="stated_intent",
    ticker_note="Unspecified; probably compute or colocation contracts rather than securities.",
    note="This is an intention to sell; completion is not reported."))
P.append(pos("CCLD", "stock", "long", "2118360364153012240", "inferred", "inferred",
    [ev("2118360364153012240", "+10% today thanks to the lovely people at $APP and $CCLD")],
    note="Holding is implied by the attribution of a +10% day. On 2026-11-05 it quoted InvestorMexican's 'bought a bit in after hours at $1.82' (that author's price) [2118359597228675448]."))
P.append(pos("PORTFOLIO MARKET BETA", "stock", "long", "2118526296431137146", "first_disclosed_at_exit", "explicit",
    [ev("2116736100937224192", "i'm bearish market beta")],
    [ev("2118526296431137146", "crazy timing in hindsight for me to sell beta"),
     ev("2123644589282369940", "sitting out the market for the last month"),
     ev("2125440798909251770", "continue to sit out the market in cash")],
    exit_post="2118526296431137146", exit_basis="stated",
    ticker_note="Generic long-equity beta; the instruments sold are not named.",
    note="It sold 'beta' around 2026-11-01..06. Unclear which holdings that covered: the APP+RELY 35% was still reported on 2026-11-04 and 2026-11-05."))
P.append(pos("FTX CLAIMS", "private", "long", "2046809501987434610", "inferred", "weak",
    [ev("2046809501987434610", "tfw smart enough to buy FTX BK claims because their venture portfolio was mispriced")],
    note="Conflicts with 2025-07-26: 'i turned down dozens of people in my DMs who wanted to sell me their FTX claims' [1949201265696850323]. Unresolved."))
P.append(pos("5253.T", "stock", "long", "1899121761607995763", "inferred", "weak",
    [ev("1899121761607995763", "5253 is +10% today. why are you not long cute girls?")],
    ticker_note="Tokyo-listed (non-US) Cover Corp; written as '5253'.", note="Rhetorical; a holding is implied, not stated."))
P.append(pos("CORZW", "warrant", "long", "1894865816681881734", "stated", "weak",
    [ev("1894865816681881734", "$CORZW probably the only thing in this factor basket that's worth longing", quoted=True)],
    claimed_entry=claimed("1894865816681881734", why="2025-02-25 self-post quoted with a 🎯 on 2025-02-26"),
    ticker_note="Core Scientific warrants.", note="States it is 'worth longing', not that it is long."))
P.append(pos("SEMR", "stock", "long", "1687484226311229440", "first_disclosed", "inferred",
    [ev("1687484226311229440", "$SEMR turning the profitability corner"),
     ev("1952478373458169935", "$SEMR is almost back to trading at my entry price", quoted=True)],
    [ev("1952478373458169935", "i also don't own it anymore")], exit_post="1952478373458169935", exit_basis="disclosed_after",
    claimed_entry=claimed("1952478373458169935", why="2022-11-23 self-post 'almost back to trading at my entry price'"),
    note="Entry predates the window. The 2025-08-04 post discloses the exit after the fact; the sale date is unknown."))
P.append(pos("WAL", "stock", "long", "1847838812971430239", "first_disclosed", "inferred",
    [ev("1847838812971430239", "the fastest double i've ever had other than $WAL during the very brief banking crisis")],
    note="A 2023 banking-crisis trade (about March-May 2023), before the window; entry and exit dates not stated."))
P.append(pos("CCJ", "stock", "long", "1983222781849547183", "first_disclosed", "weak",
    [ev("1983222781849547183", "yet another day where past me is outperforming present me $CCJ")],
    note="Implies an earlier uranium/CCJ holding that was later sold (the quoted 2021 post says uranium was 'far and away the best opportunity'). Dates unknown."))
P.append(pos("TRTN/TGH", "stock", "long", "1740242713461854278", "inferred", "weak",
    [ev("1740242713461854278", "when you have an informational advantage you can be relentless $TGH $TRTN")],
    claimed_entry=claimed("1740242713461854278", why="2023-02-14 self-post calling $TRTN/$TGH 'an easy base hit'"),
    note="Container lessors, both since taken private. A holding is implied, not stated."))
for t, txt in (("NEXOY", "$NEXOY"), ("TRP", "$TRP"), ("KUT.V", "$KUT.V"), ("PLCE", "$PLCE"), ("OEC", "$OEC")):
    P.append(pos(t, "stock", "long", "1686942315468955648", "picks_tracker", "weak",
        [ev("1686942315468955648", "added my current best ideas to the Outperformers list today"), ev("1686942315468955648", txt)]
        + ([ev("1686787974779084800", "my best idea right now is $NEXOY")] if t == "NEXOY" else []),
        ticker_note=("TSX Venture (non-US)" if t == "KUT.V" else ("US OTC ADR of Nexon (3659.T)" if t == "NEXOY" else None)),
        note="Added to the public My-Bets 'Outperformers' list (github.com/starfaerie/My-Bets). A personal holding is not stated."))

# Remove helper duplicates
positions = P

# ------------------------------------------------------------------ books
def book(pid, holdings, cash=None, partial=False, note=None, quoted_book=False):
    p = POSTS[pid]
    b = {"date": d(pid), "post_id": pid, "holdings_as_stated": holdings, "cash_pct": cash, "partial": partial, "note": note}
    if quoted_book:
        for q in chain(p):
            if q.get("handle") == "astridwilde" and "current weights" in (q.get("text") or ""):
                b.update({"date": q["created_at"][:10], "post_id": None, "quoted_id": q["id"], "via_post": pid,
                          "verbatim": q["text"]})
                break
    else:
        b["verbatim"] = p["text"]
    return {k: v for k, v in b.items() if v is not None}

books = [
    book("1679931444750323712", [], ">50%", True, "Cash only: 'now >50% in cash again'."),
    book("1743229653106803197", ["$TCEHY, $BIDU, $BABA: 20% (Chinese largecaps)"], None, True, "Partial: China basket weight."),
    book("1750334625006989798", ["$ENTG + $TSM: >10% of net worth"], None, True, "Partial."),
    book(B_2024_09_30, ["UNDISCLOSED 41%", "$CPNG 12%", "$APP 11%", "$GRUSF 10%", "$TSM 9%", "$ACFN 3%", "$NTDOY 3%", "UNDISCLOSED 2.5%",
                        "$DAC 2%", "$COVCF 1.5%", "$CPH.TO 1%", "$RRGB 1%", "$MOB.ST 1%", "$CRL 0.5%", "$GSL 0.5%"], "12%", False,
         "The 2024-09-30 book is quoted inside the 2024-10-22 reply; its own id is not a row in posts.jsonl.", quoted_book=True),
    book("1840887409115873640", ["sells: $MOB.ST ~14% at peak -> 1%", "sells: $GRVY (exited)", "new: $CPH.TO 1%", "new: $COVCF 1.5%", "new: $RRGB 1%"],
         None, True, "Q3 2024 changes, posted with the 2024-09-30 book."),
    book(B_2024_10_22, ["UNDISCLOSED 55.4%", "$APP 9.1%", "$CPNG 8.3%", "$TSM 7.4%", "$GRUSF 6.1%", "UNDISCLOSED 3.6%", "$ACFN 2.7%", "$NTDOY 2%",
                        "$RRGB 1%", "$COVCF 0.9%", "$CPH.TO 0.7%", "$CRL 0.4%", "$GSL 0.4%", "sold: $DAC"], None, False,
         "No cash line. The weights sum to 99.1%, so cash, if any, sits in an undisclosed line or is under 1%."),
    book("1856391266017095824", [], "50%", True, "'immediately went to 50% cash'."),
    book("1877043951464505499", ["sold entire $PSIX"], "40%", True, "'up to 40% cash position now'."),
    book("1877427408275476766", [], "40%", True),
    book("1894763674654376113", ["bought back entire $APP position"], "50%", True, "'while i was sitting in 50% cash'."),
    book("1899150866281795614", ["bought $GOOG", "bought $AMZN"], "40%", True, "Cash was '>50% ... since January 19', now '40%'."),
    book(B_2025_04_02, ["Cash: 35%", "$CPH.TO 10.6%", "$CPNG 6.5%", "$NTDOY 5.1%", "$APP 5.1%", "$TSM 5.1%", "$CIB 5%", "$AMZN 3.5%", "$REGN 3%",
                        "$ACFN 2.5%", "$RELY 2.5%", "$DAC 2.4%", "UNDISCLOSED 1.7%", "$VAL 2026 40c 1.4%", "$TDW 1.3%", "$FOA 1.2%", "$HII 1.2%",
                        "$AMTM 1%", "$COVCF 1%", "$GOOG 1%"], "35%", False,
         "Positions >1% weight. Same-thread post 1907225872282915216: 'most to all of my liquid net worth will be going into my startup'."),
    book(B_2025_05_19, ["Cipher (CPH.TO)", "Nintendo (NTDOY)", "Coupang (CPNG)"], None, True,
         "'my only material positions are Cipher, Nintendo, and Coupang'; no weights."),
    book(B_2025_07_01, ["$CPH.TO", "$CPNG", "$NTDOY", "$GOOG", "undisclosed", "$DMGI.V", "$TGTX", "$HROW", "$ACFN", "$AMTM", "$REGN", "$COVCF", "$ARBKL"],
         None, False, "In order of weight, no weights or cash given; exited YTD: $TSSI, $PSIX; 'only L of the year so far $MRVI'."),
    book("1953600042843222423", ["$CPH.TO roughly 15% of LNW"], None, True, "LNW = liquid net worth."),
    book("1966135125290398179", [], ">30%", True, "'for almost this entire period i've had a >30% cash position' (LTM window)."),
    book("1976309012296761706", ["$RELY third largest position"], None, True),
    book("2014044628828184608", ["$ADBE 2% -> 5%"], None, True),
    book("2018760073569599774", ["$ADBE 8%"], None, True),
    book(B_2026_02_06, ["$APP 31%", "$NNI 18%", "$RELY 10%", "$TWST 9.5%", "$NVDA 7%", "$HROW 3%", "$TGTX 2.5%", "$AMTM 2.5%", "$ACFN 2%", "$RGEN 2%",
                        "$ASML 1.5%", "(ADBE: cut the entire position)"], None, False,
         "No cash line. The listed weights sum to 89%."),
    book("2037216555843674518", ["$NVDA + $META + SK Hynix: 30% weight"], None, True),
    book(B_2026_09_04, ["cash (36%)", "$RELY", "$NVDA", "$QXO", "$SKHY", "undisclosed 1", "$HROW", "$NTDOY", "undisclosed 2", "$ACFN", "$AMZN"], "36%", False,
         "'Current >1% holdings by weight', in order; weights given only for cash."),
    book(B_2026_11_04, ["$APP + $RELY: 35% weight"], None, True),
    book("2123644589282369940", [], "sitting out the market (no %)", True, "'sitting out the market for the last month'."),
    book("2125440798909251770", ["cash", "slowly accumulating $QURE (suggested)", "64-hex commitment string"], "sitting out the market in cash (no %)", True,
         "'1. continue to sit out the market in cash'. The hex string matches the 2023 hash-commitment pattern (see BTCW.V)."),
]

# ------------------------------------------------------------------ claimed returns
def cr(pid, quote, figure, ticker=None, kind="performance", note=None, quoted=False):
    e = ev(pid, quote, quoted=quoted)
    out = {"date": d(pid), "post_id": pid, "quote": quote, "ticker": ticker, "claimed_figure": figure, "kind": kind, "note": note}
    if quoted:
        out.update({k: e[k] for k in ("quoted_id", "quoted_handle", "quoted_date") if k in e})
    return {k: v for k, v in out.items() if v is not None}

claimed_returns = [
    cr("1679870129746903041", "i more than doubled its performance without using leverage", ">2x the Nasdaq's ~+50% 2023 YTD", None, "portfolio_ytd_relative"),
    cr("1684236603181666304", "after that $SIMO win", "win (unquantified)", "SIMO", "trade"),
    cr("1684972690615242752", "sold out on a sentiment swing for +100% gain", "+100% realized (could have been >200%)", "APP/META", "trade"),
    cr("1686942315468955648", "added my current best ideas to the Outperformers list today", "n/a (public picks tracker)", "TRP,NEXOY,KUT.V,PLCE,OEC,CIB,AAMC", "picks_tracker",
       "github.com/starfaerie/My-Bets"),
    cr("1689518685545975813", "a) $CSU, $MKL, $LVMH basket: +9.81%", "CSU/MKL/LVMH +9.81%; QQQ +22.77%; ZIG +13.44%; TDW/TS/OEC +10.28%; SPY +10.3% (5 months)",
       "CSU,MKL,LVMH,QQQ,ZIG,TDW,TS,OEC", "picks_tracker", "Scores the 2023-03-03 'which outperforms over the next 5 years' poll."),
    cr("1689530373771075584", "$QQQ is still outperforming me. almost all of my out performance YTD has come from my active trading", "bets lag QQQ; YTD outperformance from active trading",
       "QQQ", "picks_tracker", "github.com/starfaerie/My-Bets"),
    cr("1691215743634022400", "happy to report my first L of the year", "loss (unquantified)", "AAMC", "trade"),
    cr("1697622477470589069", "in hindsight i literally top ticked it", "exit at the top", "CBIT.V/WULF", "trade"),
    cr("1735697118193651745", "$JXN +48% since i added it to my bets in March", "+48%", "JXN", "picks_tracker"),
    cr("1740121616229794257", "almost +20% gain today to punctuate the year", "~+20% in one day; flat vs Russell since mid-August", None, "portfolio_day"),
    cr("1741685939028873455", "the trade contributed +8% to my performance this year", "+8% contribution (picks peaked +350%, ended negative)", "CBIT.V/WULF", "trade"),
    cr("1743301646292341197", "$CIB still a top position, now a big winner", "big winner (unquantified)", "CIB", "position"),
    cr("1745461283875663872", "thanks for the free money", "called it (miners GTFO)", "BTC miners", "called_it"),
    cr("1748224903395025324", "this alpha has now fully played out", "called it (hash-committed)", "BTCW.V", "called_it"),
    cr("1838065316796276929", "total equal weighted return = 28.8%", "+28.8% equal-weighted vs S&P +50% since 2022-12-20", "VNO,GSL,RIG,LXU,AFM.V", "picks_scorecard",
       "Scores the 2022-12-20 'simple theses'; it concedes 'indexing is overpowered'."),
    cr("1840092407087673779", "i'm +64% in our first annual stock picking long/short contest", "+64% in contest; 'outperforming $SPY 200% YTD'", "SPY", "public_contest"),
    cr("1840884002154057911", "+45% YTD", "+45% YTD (flat since May 1)", None, "portfolio_ytd"),
    cr("1841863943708455080", "buying in was still one of my best % calls ever", "one of best % calls (unquantified)", "TLN (inferred)", "trade"),
    cr("1841863941762236917", "missed out on >60% of the upside when it became consensus", "missed >60% upside", "VST,CEG,TLN", "opportunity_cost"),
    cr("1847838812971430239", "the fastest double i've ever had other than $WAL", "+100% (double)", "RRGB,WAL", "trade"),
    cr("1849569538276458827", "this has been a significant source of alpha for me this year", "significant alpha (unquantified)", "GEO", "trade"),
    cr("1849830293068276028", "$PSIX now above where it was before the dip", "recovered the -20% dip", "PSIX", "called_it"),
    cr("1854370232724234734", "my all time largest percentage gain and absolute dollar win", "largest % and $ win ever", "APP", "position"),
    cr("1854534281814520172", "turned out to be a great trade when silver spreads blew out", "great trade (unquantified)", "AMRK", "trade"),
    cr("1855088510190973296", "i am really proud of my Beta and R-squared this year", "low beta / low R-squared (unquantified)", None, "risk_stats"),
    cr("1861481017279648096", "+20% already", "+20% since 2024-11-07", "TPR", "called_it"),
    cr("1866149181506597201", "the $APP trade was unreal", "entry within 17% of ATL, exit within 2% of ATH", "APP", "trade"),
    cr("1866148516441075761", "i will never time the market this perfectly again in my life", "perfect timing (unquantified)", "APP (inferred)", "trade"),
    cr("1869518699276931499", "+100% today while the market is -4% and $MSOS is -2%", "+100% in one day (name not given)", None, "trade",
       "Probably a cannabis name (quoted post is about $VREOF); unresolved."),
    cr("1871573073213972654", "what a way to capstone my year $PSIX", "unquantified", "PSIX", "trade"),
    cr("1874749539992961501", "second best year in public markets since i started sharing here", "2024 second-best year (figures in image, not captured)", None, "portfolio_year"),
    cr("1874749542777925872", "in terms of outperforming my benchmark... yeah, i'd say mission success", "beat benchmark in 2024; turnover 114%", None, "portfolio_year"),
    cr("1885334311777313079", "this is up an uncorrelated 50% in 3 months", "+50% in 3 months", "TPR", "called_it"),
    cr("1890461842759155996", "$NBIS is +50% since this tweet if you didn't get cute with your fills", "+50% since 2025-01-27", "NBIS", "called_it",
       "On 2025-04-05 it said it did not own NBIS [1908668710040240221]."),
    cr("1891864035320049687", "$NBIS is +90% if you didn't get cute with your fills", "+90%", "NBIS", "called_it"),
    cr("1973756630002172386", "$NBIS is +340% if you didn't get cute with your fills", "+340%", "NBIS", "called_it"),
    cr("1891681975938748627", "meanwhile $GRUSF is a 10x", "10x", "GRUSF", "position"),
    cr("1894399223581258134", "$MRVI my first L of the year", "loss (unquantified)", "MRVI", "trade"),
    cr("1896590946193887389", "performance is basically in line with smallcaps", "in line with small caps YTD (2025-03-03)", None, "portfolio_ytd"),
    cr("1899113582891249899", "i was smart enough to see the sentiment turn coming and sell everything", "avoided the drawdown (unquantified)", "datacenter capex", "called_it"),
    cr("1902049154085658864", "i am just as proud of my Tencent Music call", "unquantified", "TME", "called_it"),
    cr("1907225872282915216", "One year, 6 month, and YTD performance vs. the S&P500 to frame this", "figures in image (not captured)", None, "portfolio_period"),
    cr("1930257653827285515", "$APP carried my entire portfolio to a nearly 200% return since this tweet", "portfolio ~+200% since 2023-06-12", "APP", "portfolio_period"),
    cr("1930257651524649434", "narrative lottery ticket turned into the force that carried the entire market", "qualitative scorecard of 2023-06-12 best ideas", "RELY,APP,SEMR,CIB,AMRK,CRL,ULTA,DE,QCOM",
       "picks_scorecard"),
    cr("1940069022961385595", "largest contributors YTD were $TSSI and $PSIX which i no longer own", "1H 2025 YTD and 1y figures in image (not captured); MRVI the only loss", "TSSI,PSIX,MRVI",
       "portfolio_ytd"),
    cr("1960855385696559586", "generated an 18% uncorrelated return within 24 hours", "+18% in 24h", "SATS", "trade"),
    cr("1961474654964441395", "pretty happy with my +33% YTD", "+33% YTD (2025-08-29)", None, "portfolio_ytd"),
    cr("1965025724794130748", "an uncorrelated double in two weeks", "+100% in two weeks", "SATS", "trade"),
    cr("1965802140703850705", "went -35% before up +50% from here", "-35% then +50% since 2025-02-18", "MU", "called_it"),
    cr("1966134399537430556", "simply an absurd LTM. achieved without leverage", "LTM unquantified; options <5% of performance", None, "portfolio_ltm"),
    cr("1970502652774760914", "it's already in my top 20 performers of all time", "HROW top-20 all-time; AAMC 'biggest L of all time'", "HROW,AAMC", "position"),
    cr("1978690320272388267", "buying $VSCO before the show was an incredible trade", "incredible trade, two years running (unquantified)", "VSCO", "trade"),
    cr("1981018647050301799", "the factor top to the day", "NBIS -22%, IREN -25%, GEV -13%, VRT -10%, BE -20% after 2025-10-14 call", "NBIS,IREN,GEV,VRT,BE", "called_it"),
    cr("1982858252061950431", "my second L of the year", "loss (unquantified)", "NTLA", "trade"),
    cr("1983222781849547183", "past me is outperforming present me $CCJ", "unquantified", "CCJ", "opportunity_cost"),
    cr("1985331353983045636", "today i was rug pulled by the FDA", "loss (unquantified)", "QURE", "trade"),
    cr("1986848310318277063", "from +104% LTM to +74% LTM in a week", "+104% -> +74% LTM", "RELY,QURE", "portfolio_ltm"),
    cr("1986848723151036911", "Ls this year:", "losses: MRVI, NTLA, QURE, RELY (2025)", "MRVI,NTLA,QURE,RELY", "trade"),
    cr("1990606919581802593", "didn't end up creating a vehicle because it played out too quickly", "short datacenter factor played out (unquantified)", "datacenter factor", "called_it"),
    cr("1998930742534099048", "my avg yearly performance is >100% for 5 years in a row", ">100% average yearly for 5 years", None, "portfolio_multi_year"),
    cr("1999727800392253520", "before finally exiting for a 108% return less than 6 months later", "+108% (after -60% drawdown from cost)", "ARBKL", "trade"),
    cr("2009120203146424506", "short term vol printed", "vol call paid (unquantified)", "SIMO", "called_it"),
    cr("2025801898318786773", "despite the last 5 years of outperformance", "5 years of outperformance (unquantified)", None, "portfolio_multi_year"),
    cr("2045691279942828200", "I knew I was right but I had no idea how right I was", "unquantified", "MU", "called_it"),
    cr("2045691634827112511", "Narrator: it was 6 months away", "called the memory re-rating", "SK Hynix, MU", "called_it"),
    cr("2047475887646621990", "Two most expensive mistakes / errors of omission", "opportunity cost (APP options; NFLX 2022)", "APP,NFLX", "opportunity_cost"),
    cr("2047511270447083614", "my stocks do seem to only go up", "unquantified", None, "portfolio"),
    cr("2054209619992662299", "$CRWV -30% since. occasionally i make good decisions", "CRWV -30% after its 2026-05-06 sale", "CRWV", "called_it"),
    cr("2082110993606611098", "dodging a casual -30% drawdown", "avoided -30% in memory; +10% in Nintendo", "memory,NTDOY", "trade"),
    cr("2084699182959673832", "my entire portfolio is up 13.5% in the last two days", "+13.5% portfolio in 2 days", "SNDK,SKHY,QXO", "portfolio_period"),
    cr("2085106834030158102", "-6% to my LNW on this release", "-6% of liquid net worth", "APP", "trade"),
    cr("2085106835464593835", "-14% lost in opportunity cost", "-14% opportunity cost", "APP", "opportunity_cost"),
    cr("2088613083057209413", "buying $TLN out of Bk, $VLE.TO, $HROW, buying Bitcoin miner senior debt when it was trading for $0.06 on the dollar",
       "past winners list (unquantified)", "TLN,VLE.TO,HROW", "called_it"),
    cr("2090088625195356241", "what a Beautiful year it has been", "unquantified", "TWST,PSNL,HROW,TEM", "position"),
    cr("2092782644258017639", "this Q or the next is when it would show up in earnings and here we are", "called it", "CRM", "called_it"),
    cr("2095870238692917672", "My performance vs the Russel ytd", "figures in image (not captured)", None, "portfolio_ytd"),
    cr("2104911896780644593", "I made way more money than I deserved to owning the stock", "gain (unquantified)", "QURE", "trade"),
    cr("2110179615847395411", "my net worth would be up 20% today", "counterfactual +20% net worth (not realized)", "BMBL", "counterfactual"),
    cr("2114383076239503412", "my biggest winner ever in both % AND dollar terms was $APP", "largest % and $ winner", "APP", "position"),
    cr("2116067563151270020", "outperforming every hedge fund on earth for going on 6 years now", "6 years of outperformance (unquantified)", None, "portfolio_multi_year"),
    cr("2117998945876213903", "it worked out", "gain (unquantified)", "TAN", "trade"),
    cr("2118360364153012240", "+10% today thanks to the lovely people at $APP and $CCLD", "+10% portfolio in one day", "APP,CCLD", "portfolio_day"),
    cr("2118526296431137146", "crazy timing in hindsight for me to sell beta", "well-timed beta sale (unquantified)", "market beta", "called_it"),
    cr("2119321163218506180", "tfw a single trade just put me ahead of the entire list", "ahead of every fund on an end-October hedge fund list; R-squared < 0.1", None, "portfolio_ytd_relative"),
    cr("2122735747241558312", "been a great two weeks for me", "unquantified", None, "portfolio_period"),
    cr("2124868031327424880", "To everyone who told me this was cope and I was delusional", "called it (Nvidia CEO return)", "NVDA", "called_it"),
    cr("2124916147145588802", "i did not buy far enough OTM to make a million dollars", "gain implied, below $1M", "NVDA", "trade"),
    cr("1843678671695163442", "gratz to anyone who bought claims when i started talking about this and they traded for <8%", "FTX claims payout ~150% vs <8% purchase", "FTX claims", "called_it"),
    cr("1812704253263426009", "what's about to be my best trade of the year", "best trade of the year (unquantified)", "GEO", "trade"),
    cr("1946420371072364948", "to the day", "called it (subject not recoverable)", None, "called_it"),
    cr("1847410296824221971", "lol called it", "called it (non-market)", None, "called_it"),
    cr("1895507995192332508", "is my call from two years ago that we go into a recession in Q1 2025 going to actually happen?", "macro call (unresolved)", None, "called_it"),
]

# ------------------------------------------------------------------ endorsed picks
def en(pid, ticker, words, quoted_text, held=None, note=None):
    e = ev(pid, quoted_text, quoted=True)
    o = ev(pid, words) if words else {}
    out = {"date": d(pid), "post_id": pid, "ticker": ticker, "quoted_author": e.get("quoted_handle"), "quoted_id": e.get("quoted_id"),
           "quoted_date": e.get("quoted_date"), "account_words": words, "quoted_text": quoted_text,
           "account_holds_per_ledger": held, "note": note}
    return {k: v for k, v in out.items() if v is not None}

endorsed_picks = [
    en("1691593420136178021", "NU", "the lowest engagement tweets have the highest alpha", "they will likely beat the analyst expectations"),
    en("1702768597062607089", "PRGS (bearish)", "the highest alpha tweets have the lowest engagement", "$12M insurance capacity isn"),
    en("1740931228004745305", "ALPP (short)", "the highest alpha tweets have the lowest engagement", "$ALPP is currently my largest short"),
    en("1680962488098238464", "VSAT (bearish event)", "alpha is everywhere", "$VSAT -16% ah"),
    en("1686103766020546560", "BB", "$BB IOT thesis firmly on track", "Foxconn has signed up to use $BB QNX"),
    en("1703496981015130367", "GLNG", "when @mintzmyer joins you on a trade", "$GLNG. I", held="yes (inferred)", note="The account frames it as its own trade."),
    en("1737182103954206952", "AMR,METC,HCC,CEIX (coal)", "i hope you have coal this year", "$AMR $METC $HCC $CEIX"),
    en("1846912181482246436", "ASPI", "every day my feed is full of Good News", "Absolutely HUGEEE for $ASPI"),
    en("1851969827226656854", "CLPT / CLS.b", "the most mispriced publicly traded med tech asset i've ever seen", "$CLS.b with solid momentum"),
    en("1851997968166985925", "ROOT", "big congrats to @fallacyalarm on the absolute homerun that is $ROOT!", "excited I get about $ROOT"),
    en("1874197586418294943", "NXSN.TA", "now we're both looking at $NXSN", "$NXSN on the Tel Aviv exchange"),
    en("1876295505816453491", "REKR (vs SOUN)", "calling his shots like this", "$SOUN vs $REKR"),
    en("1883186503565881645", "FPH", None, "I believe that the stock could double in 2025", note="Own words are only the target emoji."),
    en("1888723842928886070", "CLF", "get long or be wrong", "buy recommendation on $CLF"),
    en("1894263776892928309", "FOA", "tweets i will be quote tweeting in 3 years", "$FOA", held="yes (1.2% on 2025-04-02)"),
    en("1896945031992484147", "VAL,BORR,TDW (offshore)", "should you be buying anyways? probably", "$VAL $BORR $TDW", held="VAL 40c calls and TDW on 2025-04-02"),
    en("1905382703186505987", "DM (NNDM merger arb)", "alpha is everywhere", "$DM looks to be an ~10% return"),
    en("1923440355736944994", "ODD", "alpha is everywhere", "$odd seems to be vastly sand bagging", note="On 2025-05-19 it says it does not own $ODD [1924290564335587399]."),
    en("1930672850375188661", "SEZL,HIMS", "alpha is everywhere", "$HIMS and $SEZL", note="On 2025-05-19 it says it does not own $SEZL."),
    en("1935407044087202205", "TSM,NVDA,MRVL", "you simply have to be long $TSMC, $NVDA, and $MRVL", "Why wouldn't TSMC work from here?"),
    en("1955849546614894605", "GTLB", "when you're right, you're right", "This still has dollar billz written all over it", held="no ('i don't own it')"),
    en("1966718408759930970", "HROW", "you just have to own it", "$HROW Bloomberg Q3 2025 data", held="yes"),
    en("1973792501967581328", "TWST", "you simply have to own it", "$TWST initiation reports", held="yes (9.5% on 2026-02-06)"),
    en("1975946313243197540", "NTLA", "tweets that will continue to age well", "Quite possibly the biotech bargain of the decade", held="yes (inferred; 'my second L')"),
    en("1980084242555302008", "TWST,NTRA", "people are finally starting to put the pieces together here", "$TWST $NTRA"),
    en("1991953232055369748", "GOOGL", "you simply have to own it", "Google’s $GOOGL AI infrastructure chief", held="yes (GOOG in 2025 books)"),
    en("1997081270162194727", "CVNA", "unreal call", "Paywall removed re: Carvana $CVNA"),
    en("1997013761065091429", "ADBE long / publishers short", "I was in the same trade as Josh", "LONG \nAdobe (ADBE)", held="short publishers (inferred); ADBE held Jan-Feb 2026"),
    en("2003105650558271608", "LLY/ABVX", "huge and well deserved W", "$abvx"),
    en("2004484449950646503", "SK Hynix (000660.KS)", "you just have to own it", "SK hynix to become the world’s first to mass-produce HBM4", held="yes (2026)"),
    en("2011697532758606325", "semicap (TSMC guidance)", "none of us own enough semicap", "Raises AI forecast"),
    en("2020388965103333676", "APP", "You just have to own it", "On Applovin Ecommerce Ads $APP", held="yes (31% on 2026-02-06)"),
    en("2029297639750348857", "BW (and BE)", "alpha is everywhere", "$BW even after this move", note="Repeated 2026-08-11: 'just own it and take a nap for 3 years' [2086996900931387420]."),
    en("2034366541790425478", "MU", "just own memory and take a nap for 3 years", "$MU Q2’26 EARNINGS HIGHLIGHTS", held="memory basket (yes)"),
    en("2037743563551985990", "NVDA, MU, SNDK", "just own memory and don't look at equities for a couple years", "Read thru for $MU / $SNDK", held="memory basket (yes)"),
    en("2052902811541885204", "PL", "Criminally underrated investor", "Wrote up some more thoughts on $PL", note="2026-03-24: 'the man hit it out of the park with $PL' [2036346199712932259]."),
    en("2060085979172745621", "SNOW", "one of the most well telegraphed software earnings beats of all time", "$SNOW is going to murder earnings tomorrow"),
    en("2067262108228849870", "QURE", "What a beautiful day", "$qure", held="yes (2025-2026)"),
    en("2083010176953745490", "REPL", "what a Beautiful day", "Huge win for $REPL"),
    en("2085014860753203531", "TWST", "what a beautiful day", "$TWST is the clear winner here", held="yes"),
    en("2089979893891354922", "SK Hynix (000660.KS)", "you just have to own it", "SK Hynix to buy back 40 trillion won", held="yes"),
    en("2104873855953379631", "ASML,TSM,AMAT,LRCX,KLAC", "none of us own enough semicap", "$ASML $TSM $AMAT $LRCX $KLAC"),
    en("2118097923703812567", "SEZL", "clearly the best BNPL company and it isn't close", "SEZZLE $SEZL Q3"),
    en("2118359597228675448", "CCLD", "this kind of opportunity shows up literally dozens of times every earnings period", "so I bought a bit in after hours at $1.82",
       held="yes (inferred, 2026-11-05)"),
    en("2119955290154291353", "HROW", "agreed on all counts. stock is probably a 3x over the next 4 years from here", "Key takeaways from $HROW", held="yes"),
    en("1849070889091948561", "NVDA", "none of us own enough $NVDA", "This is v bullish for $NVDA"),
    en("1865797474083807495", "NVDA", "none of us own enough $NVDA", "$NVDA $AMD $MRVL"),
    en("1878966239055524332", "MU", "the first chart I've seen in the sector with projected numbers actually close to my own", "$MU is worth a whole lot more than $100 per share"),
    en("2009277655028306289", "INTC", "So few people have put the pieces together on the hurricane force tailwind coming for Intel", "TSMC's N2/N3/N4/N5 capacity are totally booked"),
    en("1953340614998901023", "APP", "it's simply the greatest advertising business on earth", "Probably the greatest income statement excerpt", held="APP leg status at 2025-08: not in 2025-07-01 list"),
    en("1953600042843222423", "CPH.TO", "roughly 15% of my LNW", "$CPH.TO Blow out Q2", held="yes (~15% LNW)"),
    en("1953289685859455055", "NNI", "simply unreal quarter though. i should own more", "$NNI out with a fantastic quarter", held="yes"),
    en("2001812059101761902", "KRE", "best tails trade of 2024-2025. incredible", "$KRE Trump wins in November"),
    en("1959367116806934809", "HOOD (and SIVB call)", "the guy who called $SIVB also 10x'd on $HOOD", "Is today the day the market cares that $SIVB is insolvent?"),
    en("2046736290335568178", "ANT (Anthropic)", "Still undervalued", "valuation on my anthropic shares"),
    en("1979754893801140733", "Physical Intelligence (private)", None, "Physical Intelligence is the next OpenAI"),
]

# ------------------------------------------------------------------ current stance (2026-09-01 onward)
PERIOD = "2026-09-01"
def theme(name, stance, ids, quote_post, quote, note=None, quote_quoted=False):
    for i in ids:
        if d(i) and d(i) < PERIOD:
            ERR.append(f"theme {name}: {i} before period")
    ids = sorted(set(ids), key=lambda i: POSTS[i]["created_at"])
    latest = ids[-1]
    e = ev(quote_post, quote, quoted=quote_quoted)
    out = {"theme": name, "stance": stance, "mentions_in_period": len(ids), "mention_post_ids": ids,
           "latest_post": latest, "latest_date": d(latest), "quote_post": quote_post, "quote": quote, "note": note}
    return {k: v for k, v in out.items() if v is not None}

current = [
    theme("APP", "bullish", ["2114383076239503412", "2117370896268898605", "2118070900860076241", "2118360364153012240"],
          "2118360364153012240", "+10% today thanks to the lovely people at $APP and $CCLD", "Held (35% with RELY on 2026-11-04)."),
    theme("RELY", "bullish", [B_2026_09_04, "2118070900860076241", "2118091716100276619"],
          "2118091716100276619", "please keep selling $RELY on these numbers", "Wants lower prices to buy more."),
    theme("NVDA / Jensen Huang", "bullish", [B_2026_09_04, "2119626067975766420", "2120982877827731488", "2121100560640491939", "2122954901097742666",
          "2124873051569549693", "2124868031327424880", "2124916147145588802", "2124985631944384973", "2123127734469906661", "2122148876748800406", "2121459562985451989"],
          "2122954901097742666", "Either the man will rejoin or he will start a new company",
          "Bullish on Nvidia led by Huang; it claimed vindication on 2026-11-23. Count includes reaction quotes whose quoted post is about Nvidia or Jensen. Whether it still holds NVDA after the 'sell beta' is not stated."),
    theme("Memory (SK Hynix / $SKHY)", "neutral (ambiguous)", [B_2026_09_04, "2122873151306825875"], "2122873151306825875",
          "Mintwit and Memorytwit are mirror images of each other right now",
          "$SKHY was held on 2026-09-04. The 2026-11-18 remark compares memory bulls to aluminum bulls with no direction given; earlier in 2026 it was strongly bullish."),
    theme("QURE", "bullish (cautious)", ["2104911896780644593", "2104912895826100555", "2125440798909251770"], "2125440798909251770",
          "slowly accumulating $QURE doesn't seem dumb", "Bearish on 2026-09-29 trial data ('The ancient curse remains'), mildly bullish again 2026-11-25."),
    theme("HROW", "bullish", [B_2026_09_04, "2119955290154291353"], "2119955290154291353", "stock is probably a 3x over the next 4 years from here"),
    theme("NTDOY", "bullish (held)", [B_2026_09_04, "2099300165857194198"], B_2026_09_04, "$NTDOY", "Stance comes from the holding; the 2026-09-14 Switch 2 post is consumer chatter."),
    theme("QXO", "bullish (held)", [B_2026_09_04], B_2026_09_04, "$QXO"),
    theme("ACFN", "bullish (held)", [B_2026_09_04], B_2026_09_04, "$ACFN"),
    theme("AMZN", "bullish", [B_2026_09_04, "2117116294160097497"], "2117116294160097497", "you absolutely love to see it", "Reacting to Amazon robotics; held 2026-09-04."),
    theme("Anthropic ($ANT) IPO", "bullish", ["2104730273204367437", "2114726391656923190", "2123301679869378752", "2101664494837457248", "2123562258261565794"],
          "2123301679869378752", "I think the odds $ANT trades >$95/share within 10 minutes of opening are >95%",
          "Ownership not stated. On 2026-09-20 it reacted 'uh oh spaghetti-o' to a report that enterprise spend share fell [2101664494837457248]."),
    theme("TAN (solar ETF)", "bullish (held)", ["2117635166785138733", "2117998945876213903"], "2117998945876213903", "it worked out"),
    theme("CCLD", "bullish (held)", ["2118359597228675448", "2118360364153012240"], "2118360364153012240", "+10% today thanks to the lovely people at $APP and $CCLD"),
    theme("SEZL", "bullish", ["2118097923703812567"], "2118097923703812567", "clearly the best BNPL company and it isn't close"),
    theme("Precigenetics (private)", "bullish (holds)", ["2115829606293053917"], "2115829606293053917", "(I have)"),
    theme("Semicap", "bullish", ["2104873855953379631"], "2104873855953379631", "none of us own enough semicap"),
    theme("Datacenter buildout / compute demand", "bullish",
          ["2095277737212817915", "2101682818178773054", "2103282061184282878", "2104730273204367437", "2106248610321231929", "2106287313987031156",
           "2109389950206755098", "2110199566129922508", "2117811989988987064", "2117877125143519742", "2118007605692150095"],
          "2118007605692150095", "The compute flight to Malaysia will continue, in much larger size",
          "Includes endorsement quotes (2109389950206755098, 2117877125143519742)."),
    theme("Texas datacenters / US datacenter politics", "bearish", ["2103858290828423182", "2117801715680543132", "2117851365288624311"], "2117801715680543132",
          "Will be selling all exposure to Texas datacenters in short order"),
    theme("Compute credit / CoreWeave", "neutral-to-bullish", ["2101682818178773054", "2110199566129922508"], "2110199566129922508", "Coreweave is not in distress."),
    theme("Global yields", "rising (bearish bonds)", ["2103282061184282878", "2103319667163234417"], "2103282061184282878", "global yields will continue to go higher",
          "Partly walked back the same day: 'you all take me too seriously'."),
    theme("Harvey (private secondaries)", "bullish", ["2117878324659958167"], "2117878324659958167", "I'm still a buyer of Harvey secondaries btw!"),
    theme("Drug discovery theme", "neutral (late-cycle)", ["2106898708214534285"], "2106898708214534285", "We are very firmly out of second inning for the Drug Discovery theme."),
    theme("BMBL", "neutral (missed trade)", ["2110179615847395411", "2110179618225565999"], "2110179615847395411", "Had material alpha here"),
    theme("Housing ($BLDR)", "neutral (waiting)", ["2103099323093262452"], "2103099323093262452", "will someone ping me when it's time to get degenerately long housing through $BLDR"),
    theme("GME", "neutral (ironic)", ["2102378539320316332"], "2102378539320316332", "$GME is at the top of every deep value screen you run"),
    theme("Google", "bullish (weak)", ["2097500111622611027"], "2097500111622611027", "the numbers even after you do are incredible"),
    theme("Meta", "bullish (weak)", ["2096257547326177480"], "2096257547326177480", "Meta's Project SuperDex is under appreciated"),
    theme("Collectibles / gold", "bearish", ["2116736100937224192"], "2116736100937224192", "every collectible under the sun is seeing a pullback in volumes and price"),
    theme("Market beta / public equities", "bearish",
          ["2116736100937224192", "2118526296431137146", "2121320982778724718", "2122735747241558312", "2123644589282369940", "2123946094631772619",
           "2125440798909251770", "2125601506070278306"],
          "2125601506070278306", "regular reminder not to gamble!!"),
]

nov = {
    "summary": "Bearish market beta from 2026-11-01. Says it sold 'beta' (2026-11-06) and has been 'sitting out the market' for about a month (2026-11-20). On 2026-11-25 its top idea is to 'continue to sit out the market in cash'. No cash percentage is given in November; the last stated figure is 36% on 2026-09-04. Ambiguity: on 2026-11-04 it reported APP+RELY at a combined 35% weight and on 2026-11-05 a +10% day from APP and CCLD; no later post says these were sold.",
    "posts": [
        ev("2116736100937224192", "i'm bearish market beta"),
        ev("2117801715680543132", "Will be selling all exposure to Texas datacenters in short order"),
        ev(B_2026_11_04, "grown to 35% weight between the two of them"),
        ev("2118360364153012240", "+10% today thanks to the lovely people at $APP and $CCLD"),
        ev("2118526296431137146", "crazy timing in hindsight for me to sell beta"),
        ev("2121320982778724718", "you don't have to buy anything"),
        ev("2122735747241558312", "been a great two weeks for me but i would like to apologize to everyone else"),
        ev("2123644589282369940", "sitting out the market for the last month"),
        ev("2125440798909251770", "continue to sit out the market in cash"),
        ev("2125601506070278306", "including on public equities!!"),
    ],
    "last_stated_cash_pct": {"value": "36%", "post": B_2026_09_04, "date": d(B_2026_09_04)},
}

# ------------------------------------------------------------------ validate + write
cited = set()
def walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("post", "entry_post", "exit_post", "post_id", "via_post", "latest_post", "quote_post",
                     "last_seen_post", "first_absent_post") and isinstance(v, str):
                cited.add(v)
            elif k == "mention_post_ids":
                cited.update(v)
            else:
                walk(v)
    elif isinstance(o, list):
        for x in o:
            walk(x)

ledger = {
    "meta": {
        "account": "astridwilde",
        "source": "accounts/astridwilde/posts.jsonl (all posts, not only triage-kept)",
        "posts_in_source": len(POSTS),
        "window": [min(p["created_at"] for p in POSTS.values())[:10], max(p["created_at"] for p in POSTS.values())[:10]],
        "built": "2026-11-27",
        "schema_notes": {
            "backtest_entry_date": "Earliest defensible entry date: claimed_entry.date when it is earlier than entry_date, otherwise entry_date. Use it for backtests; entry_date/entry_post is the earliest posts.jsonl row carrying the evidence.",
            "dates": "Every *_date equals created_at[:10] (UTC) of the cited post. claimed_entry.date and quoted_date are the created_at of a quoted post; those quoted ids may not be rows in posts.jsonl.",
            "entry_basis": "stated | first_disclosed (first seen in a book or holding statement) | first_disclosed_at_exit | stated_intent | conditional_bid | recommendation | picks_tracker | inferred | hash_commitment_revealed | endorsement",
            "exit_basis": "stated | disclosed_after (exit reported after the fact, date of sale unknown) | disclosed_after_inferred | inferred | stated_intent",
            "exit_window": "No exit post: the position was in a posted holdings list (last_seen) and missing from the next one (first_absent). Below-1% or 'undisclosed' lines can hide it.",
            "entry_price_stated": "Upper bounds ('under $12', 'under $300') and limit bids are recorded as numbers and explained in note.",
            "size": "Weights exactly as stated, each with its post id.",
            "baskets": "Basket rows (MEMORY, NEOCLOUD, DATACENTER CAPEX) overlap ticker rows (SKHY, MU, SNDK, NVDA calls); do not double count.",
            "pre_window": "Some entries predate 2023-07-14 and are known only from self-quotes; claimed_entry carries that date.",
        },
    },
    "positions": positions,
    "books": books,
    "claimed_returns": claimed_returns,
    "endorsed_picks": endorsed_picks,
    "current_bullish": {"period_start": PERIOD, "themes": current, "cash_and_exposure_nov_2026": nov},
}
walk(ledger)
missing = sorted(i for i in cited if i not in POSTS)
for i in missing:
    ERR.append(f"cited id not in posts.jsonl: {i}")
ledger["meta"]["validation"] = {
    "cited_post_ids": len(cited), "cited_ids_missing_from_posts_jsonl": len(missing),
    "evidence_quotes_checked_verbatim": True, "dates_from_created_at": True,
}
if ERR:
    print("ERRORS:"); [print(" ", e) for e in ERR]; sys.exit(1)
os.makedirs(f"{ROOT}/backtest", exist_ok=True)
with open(f"{ROOT}/backtest/ledger.json", "w") as f:
    json.dump(ledger, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("ok", {k: len(v) for k, v in ledger.items() if isinstance(v, list)}, "themes", len(current), "cited", len(cited))
