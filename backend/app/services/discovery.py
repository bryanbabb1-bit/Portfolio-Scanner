"""Discovery scanner — breakout candidates OUTSIDE the portfolio.

Scores a curated universe of liquid names with the same breakout engine,
excluding anything already held or watched. Yahoo can't be brute-force
scanned symbol-by-symbol, so a hand-picked universe keeps the sweep fast
(history-only fetches).

WHY THIS UNIVERSE IS MARKET-WIDE. It used to be five themes — AI, AI
Infrastructure, Compute Power, Energy, Tech — where even "Energy" meant
Vistra and Oklo, i.e. power generation for data centres. Every sleeve was an
AI derivative. That made the scout structurally incapable of proposing
anything outside the sectors already owned: it could only ever find more of
the same, so "the advisor keeps recommending semis" was a property of this
file, not a judgement it had reached.

The growth tilt belongs in the SCORING, not the universe. `breakout_score`
already rewards momentum, volume expansion and proximity to highs, so a slow
defensive compounder simply won't rank unless it is genuinely setting up.
Filtering those names out here instead would just build a slightly larger
cage. Breadth here, opinion in the ranking.

Themes are grouped so the frontend filter, the theme classifier
(`themes._seed`) and the strategy's allocation vocabulary all stay in sync —
adding a sleeve here automatically teaches every one of those layers about it.
"""
from __future__ import annotations

from . import market_data, screener
from . import portfolio as pf_service

# (symbol, company) grouped under the portfolio's own theme names so the
# frontend theme filter and cards line up with everything else.
UNIVERSE: dict[str, list[tuple[str, str]]] = {
    "AI": [
        ("GOOGL", "Alphabet"), ("ORCL", "Oracle"), ("CRM", "Salesforce"),
        ("SNOW", "Snowflake"), ("CRWD", "CrowdStrike"), ("PANW", "Palo Alto Networks"),
        ("NET", "Cloudflare"), ("DDOG", "Datadog"), ("MDB", "MongoDB"),
        ("ADBE", "Adobe"), ("IBM", "IBM"), ("SOUN", "SoundHound AI"),
        ("PATH", "UiPath"), ("TEM", "Tempus AI"), ("AI", "C3.ai"),
    ],
    "AI Infrastructure": [
        ("ARM", "Arm Holdings"), ("ANET", "Arista Networks"), ("MRVL", "Marvell"),
        ("QCOM", "Qualcomm"), ("INTC", "Intel"), ("TXN", "Texas Instruments"),
        ("LRCX", "Lam Research"), ("AMAT", "Applied Materials"), ("KLAC", "KLA"),
        ("ASML", "ASML"), ("SMCI", "Super Micro"), ("DELL", "Dell Technologies"),
        ("HPE", "HP Enterprise"), ("WDC", "Western Digital"), ("STX", "Seagate"),
        ("CRDO", "Credo Technology"), ("ALAB", "Astera Labs"), ("COHR", "Coherent"),
        ("MPWR", "Monolithic Power"), ("ON", "ON Semiconductor"),
        # momentum-prone memory/optics/AI-hardware complex (the SNDK pattern)
        ("SNDK", "Sandisk"), ("RMBS", "Rambus"), ("NTAP", "NetApp"),
        ("SMTC", "Semtech"), ("AAOI", "Applied Optoelectronics"),
        ("TER", "Teradyne"), ("ONTO", "Onto Innovation"),
        ("CLS", "Celestica"), ("JBL", "Jabil"),
    ],
    "Compute Power": [
        ("VRT", "Vertiv"), ("CORZ", "Core Scientific"), ("HUT", "Hut 8"),
        ("RIOT", "Riot Platforms"), ("MARA", "MARA Holdings"),
        ("APLD", "Applied Digital"), ("BTDR", "Bitdeer"), ("HIVE", "HIVE Digital"),
        ("DLR", "Digital Realty"), ("EQIX", "Equinix"), ("GDS", "GDS Holdings"),
    ],
    "Energy": [
        ("MOD", "Modine Manufacturing"), ("POWL", "Powell Industries"),
        ("VST", "Vistra"), ("CEG", "Constellation Energy"), ("NRG", "NRG Energy"),
        ("TLN", "Talen Energy"), ("OKLO", "Oklo"), ("SMR", "NuScale Power"),
        ("NEE", "NextEra Energy"), ("ETN", "Eaton"), ("PWR", "Quanta Services"),
        ("GEV", "GE Vernova"), ("CCJ", "Cameco"), ("LEU", "Centrus Energy"),
        ("FSLR", "First Solar"), ("BE", "Bloom Energy"),
    ],
    "Tech": [
        ("AAPL", "Apple"), ("NFLX", "Netflix"), ("SHOP", "Shopify"),
        ("SE", "Sea Limited"), ("UBER", "Uber"), ("TSLA", "Tesla"),
        ("SPOT", "Spotify"), ("APP", "AppLovin"),
    ],
    # ---- sleeves the book has ZERO exposure to -----------------------------
    # These exist so the scout, the theme classifier and the strategy's
    # allocation targets can all express an idea outside the AI complex. They
    # are large, liquid and boring on purpose: the point is coverage, and the
    # breakout score decides whether any of them actually earn a mention.
    "Healthcare": [
        ("LLY", "Eli Lilly"), ("UNH", "UnitedHealth"), ("JNJ", "Johnson & Johnson"),
        ("ABBV", "AbbVie"), ("MRK", "Merck"), ("PFE", "Pfizer"),
        ("TMO", "Thermo Fisher"), ("ABT", "Abbott"), ("ISRG", "Intuitive Surgical"),
        ("VRTX", "Vertex Pharmaceuticals"), ("REGN", "Regeneron"), ("AMGN", "Amgen"),
        ("DHR", "Danaher"), ("BSX", "Boston Scientific"), ("MDT", "Medtronic"),
        ("SYK", "Stryker"), ("GILD", "Gilead"), ("HCA", "HCA Healthcare"),
    ],
    "Financials": [
        ("BRK-B", "Berkshire Hathaway"), ("JPM", "JPMorgan Chase"), ("V", "Visa"),
        ("MA", "Mastercard"), ("BAC", "Bank of America"), ("WFC", "Wells Fargo"),
        ("GS", "Goldman Sachs"), ("MS", "Morgan Stanley"), ("AXP", "American Express"),
        ("SPGI", "S&P Global"), ("BLK", "BlackRock"), ("SCHW", "Charles Schwab"),
        ("PGR", "Progressive"), ("CB", "Chubb"), ("KKR", "KKR"),
        ("ICE", "Intercontinental Exchange"), ("COIN", "Coinbase"),
        ("HOOD", "Robinhood"),
    ],
    "Consumer": [
        ("COST", "Costco"), ("WMT", "Walmart"), ("PG", "Procter & Gamble"),
        ("KO", "Coca-Cola"), ("PEP", "PepsiCo"), ("MCD", "McDonald's"),
        ("HD", "Home Depot"), ("NKE", "Nike"), ("SBUX", "Starbucks"),
        ("TGT", "Target"), ("LOW", "Lowe's"), ("CL", "Colgate-Palmolive"),
        ("MDLZ", "Mondelez"), ("DIS", "Disney"), ("BKNG", "Booking Holdings"),
        ("CMG", "Chipotle"), ("LULU", "Lululemon"),
    ],
    "Industrials": [
        ("CAT", "Caterpillar"), ("DE", "Deere"), ("HON", "Honeywell"),
        ("GE", "GE Aerospace"), ("UNP", "Union Pacific"), ("UPS", "UPS"),
        ("LMT", "Lockheed Martin"), ("RTX", "RTX"), ("BA", "Boeing"),
        ("MMM", "3M"), ("ADP", "ADP"), ("CSX", "CSX"), ("WM", "Waste Management"),
        ("PH", "Parker Hannifin"), ("EMR", "Emerson Electric"),
        ("ITW", "Illinois Tool Works"), ("GD", "General Dynamics"),
    ],
    "Energy & Materials": [
        ("XOM", "Exxon Mobil"), ("CVX", "Chevron"), ("COP", "ConocoPhillips"),
        ("SLB", "SLB"), ("EOG", "EOG Resources"), ("PSX", "Phillips 66"),
        ("MPC", "Marathon Petroleum"), ("OXY", "Occidental Petroleum"),
        ("LIN", "Linde"), ("APD", "Air Products"), ("SHW", "Sherwin-Williams"),
        ("FCX", "Freeport-McMoRan"), ("NEM", "Newmont"), ("NUE", "Nucor"),
    ],
    "International": [
        ("BABA", "Alibaba"), ("SAP", "SAP"), ("TM", "Toyota"),
        ("NVO", "Novo Nordisk"), ("AZN", "AstraZeneca"), ("HSBC", "HSBC"),
        ("RY", "Royal Bank of Canada"), ("SONY", "Sony"), ("MELI", "MercadoLibre"),
        ("NU", "Nu Holdings"), ("INFY", "Infosys"), ("SHEL", "Shell"),
    ],
    # Index and factor ETFs. Also the home for equity ETFs generally, which
    # previously fell through to "Cash & Income" and were therefore treated as
    # dry powder rather than as market exposure.
    "Broad Market": [
        ("SPY", "S&P 500"), ("VOO", "Vanguard S&P 500"), ("QQQ", "Nasdaq 100"),
        ("VTI", "Total US Market"), ("IWM", "Russell 2000"), ("DIA", "Dow 30"),
        ("RSP", "S&P 500 Equal Weight"), ("SPMO", "S&P 500 Momentum"),
        ("MTUM", "US Momentum Factor"), ("SCHD", "Dividend Equity"),
        ("VIG", "Dividend Appreciation"), ("AVUV", "US Small Cap Value"),
        ("VXUS", "Total International"), ("VEA", "Developed Markets"),
        ("VWO", "Emerging Markets"), ("GLD", "Gold"),
    ],
}

# Sleeves that existed before the universe was widened — i.e. the book's
# incumbent exposure. Kept so anything can ask "is this idea inside the box
# the client was already in, or genuinely new?"
CORE_THEMES = ("AI", "AI Infrastructure", "Compute Power", "Energy", "Tech")

# Canonical descriptions. This is the SINGLE source of the theme vocabulary —
# the ticker classifier's menu and the strategy's allocation targets both read
# it, so a sleeve added above becomes expressible everywhere at once. Written
# plainly and without an AI frame: the old portfolio.json copy described Energy
# as "the fuel behind the compute buildout", which told the model that even
# utilities were an AI trade.
THEME_DESCRIPTIONS: dict[str, str] = {
    "AI": "Companies building or monetizing artificial intelligence",
    "AI Infrastructure": "Chips, networking, memory and systems that AI runs on",
    "Compute Power": "Data centers, cooling and hyperscale compute capacity",
    "Energy": "Power generation and grid infrastructure",
    "Tech": "Broad technology leaders and consumer platforms",
    "Healthcare": "Pharma, biotech, medical devices and health services",
    "Financials": "Banks, insurers, payments, exchanges and asset managers",
    "Consumer": "Retail, staples, restaurants and consumer brands",
    "Industrials": "Machinery, aerospace, defense, transport and logistics",
    "Energy & Materials": "Oil and gas, chemicals, metals and mining",
    "International": "Non-US listed leaders and emerging markets",
    "Broad Market": "Index, factor and diversified equity ETFs",
    "Cash & Income": "Treasury bills, bonds and cash-equivalent income holdings",
}


def all_themes() -> list[str]:
    """Every theme this app can express, for classifiers and allocation."""
    return list(THEME_DESCRIPTIONS.keys())


def theme_menu(extra: dict[str, str] | None = None) -> dict[str, str]:
    """The full theme vocabulary, with the user's own descriptions winning.

    Merged rather than replaced so a hand-edited description in portfolio.json
    is preserved, while sleeves the user has never held still appear.
    """
    menu = dict(THEME_DESCRIPTIONS)
    for name, desc in (extra or {}).items():
        if isinstance(desc, str) and desc.strip():
            menu[name] = desc.strip()
    return menu


def discover(min_score: float = 0.0, limit: int = 24,
             include_owned: bool = False) -> dict:
    """Score the universe. Owned names are excluded by default.

    include_owned=True is for the Clean Sheet build, which must be able to
    pick a name the client already holds. Excluding them there would rig the
    result: the from-scratch book could never overlap the real one, so the
    overlap metric would always read zero regardless of the truth.
    """
    pf = pf_service.load_portfolio()
    owned = set() if include_owned else {
        i["symbol"].upper()
        for i in pf.get("holdings", []) + pf.get("watchlist", [])
    }

    entries = [(sym, name, theme)
               for theme, rows in UNIVERSE.items()
               for sym, name in rows
               if sym not in owned]

    market_data.warm_cache([s for s, _, _ in entries], max_workers=12, light=True)

    cands = []
    for sym, name, theme in entries:
        try:
            md = market_data.get_price_data(sym)
            c = screener.evaluate(sym, theme, md)
            if not c.quote.name or c.quote.name == sym:
                c.quote.name = name  # light fetch has no company name
            cands.append(c)
        except Exception as exc:
            print(f"[discover] skipping {sym}: {exc!r}")

    cands = [c for c in cands if c.score >= min_score]
    cands.sort(key=lambda c: c.score, reverse=True)
    source = "mock" if any(c.quote.source == "mock" for c in cands) else "live"
    return {
        "count": len(cands),
        "universe": len(entries),
        "source": source,
        "results": cands[:limit],
    }
