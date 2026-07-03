"""Discovery scanner — breakout candidates OUTSIDE the portfolio.

Scores a curated universe of liquid names thematically adjacent to the
portfolio (AI software, semis/hardware, data centers & miners, power,
platforms) with the same breakout engine, excluding anything already held
or watched. Yahoo can't be brute-force scanned symbol-by-symbol, so a
hand-picked universe keeps the sweep fast (~70 tickers, history-only
fetches) while covering the sectors that matter to this book.
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
}


def discover(min_score: float = 0.0, limit: int = 24) -> dict:
    pf = pf_service.load_portfolio()
    owned = {i["symbol"].upper()
             for i in pf.get("holdings", []) + pf.get("watchlist", [])}

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
