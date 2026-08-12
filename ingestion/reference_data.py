"""Static reference data for the tradeflow generator.

Instrument metadata here is real-world (symbols, names, sectors, exchanges,
listing currencies) because a warehouse that models sectors and currencies is
only interesting if those values behave like the real thing. The numeric
parameters (``start_price``, ``annual_drift``, ``annual_vol``,
``dividend_yield``) are plausible-but-invented inputs to the simulated price
walk in ``generate.py`` -- they are not market data and must never be read as a
forecast of anything.

The multi-currency spread is deliberate: ASX listings in AUD and European
listings in EUR/GBP force the warehouse to do real FX conversion into a single
reporting currency, which is where most naive dimensional models fall over.
"""

from __future__ import annotations

# fmt: off
# symbol, name, asset_class, exchange, sector, currency,
#   start_price, annual_drift, annual_vol, dividend_yield, popularity
INSTRUMENTS: list[tuple] = [
    # --- US mega-cap equities -------------------------------------------------
    ("AAPL",  "Apple Inc.",                        "equity", "NASDAQ", "Information Technology", "USD", 189.50,  0.12, 0.26, 0.0050, 100),
    ("MSFT",  "Microsoft Corporation",             "equity", "NASDAQ", "Information Technology", "USD", 412.30,  0.14, 0.24, 0.0075,  95),
    ("NVDA",  "NVIDIA Corporation",                "equity", "NASDAQ", "Information Technology", "USD", 118.40,  0.28, 0.48, 0.0003,  98),
    ("AMZN",  "Amazon.com, Inc.",                  "equity", "NASDAQ", "Consumer Discretionary", "USD", 178.20,  0.15, 0.30, 0.0000,  80),
    ("GOOGL", "Alphabet Inc. Class A",             "equity", "NASDAQ", "Communication Services", "USD", 165.80,  0.13, 0.27, 0.0045,  75),
    ("META",  "Meta Platforms, Inc.",              "equity", "NASDAQ", "Communication Services", "USD", 495.60,  0.18, 0.36, 0.0035,  70),
    ("TSLA",  "Tesla, Inc.",                       "equity", "NASDAQ", "Consumer Discretionary", "USD", 248.90,  0.10, 0.55, 0.0000,  92),
    ("BRK.B", "Berkshire Hathaway Inc. Class B",   "equity", "NYSE",   "Financials",             "USD", 428.10,  0.09, 0.16, 0.0000,  30),
    ("JPM",   "JPMorgan Chase & Co.",              "equity", "NYSE",   "Financials",             "USD", 198.70,  0.10, 0.22, 0.0230,  40),
    ("V",     "Visa Inc. Class A",                 "equity", "NYSE",   "Financials",             "USD", 275.40,  0.11, 0.20, 0.0080,  35),
    ("JNJ",   "Johnson & Johnson",                 "equity", "NYSE",   "Health Care",            "USD", 152.30,  0.06, 0.15, 0.0310,  28),
    ("UNH",   "UnitedHealth Group Incorporated",   "equity", "NYSE",   "Health Care",            "USD", 512.80,  0.08, 0.24, 0.0150,  22),
    ("XOM",   "Exxon Mobil Corporation",           "equity", "NYSE",   "Energy",                 "USD", 114.20,  0.07, 0.25, 0.0330,  25),
    ("CVX",   "Chevron Corporation",               "equity", "NYSE",   "Energy",                 "USD",  158.40, 0.06, 0.24, 0.0410,  18),
    ("PG",    "The Procter & Gamble Company",      "equity", "NYSE",   "Consumer Staples",       "USD", 167.90,  0.07, 0.14, 0.0240,  20),
    ("KO",    "The Coca-Cola Company",             "equity", "NYSE",   "Consumer Staples",       "USD",  62.40,  0.06, 0.15, 0.0300,  24),
    ("WMT",   "Walmart Inc.",                      "equity", "NYSE",   "Consumer Staples",       "USD",  68.30,  0.12, 0.19, 0.0110,  26),
    ("DIS",   "The Walt Disney Company",           "equity", "NYSE",   "Communication Services", "USD",  98.60,  0.08, 0.28, 0.0090,  32),
    ("BA",    "The Boeing Company",                "equity", "NYSE",   "Industrials",            "USD", 178.50,  0.05, 0.38, 0.0000,  30),
    ("CAT",   "Caterpillar Inc.",                  "equity", "NYSE",   "Industrials",            "USD", 342.70,  0.10, 0.26, 0.0170,  15),
    ("AMD",   "Advanced Micro Devices, Inc.",      "equity", "NASDAQ", "Information Technology", "USD", 148.20,  0.20, 0.45, 0.0000,  60),
    ("INTC",  "Intel Corporation",                 "equity", "NASDAQ", "Information Technology", "USD",  31.40, -0.02, 0.40, 0.0130,  38),
    ("NFLX",  "Netflix, Inc.",                     "equity", "NASDAQ", "Communication Services", "USD", 628.90,  0.17, 0.34, 0.0000,  34),
    ("COST",  "Costco Wholesale Corporation",      "equity", "NASDAQ", "Consumer Staples",       "USD", 842.10,  0.13, 0.20, 0.0055,  16),

    # --- ETFs ----------------------------------------------------------------
    ("SPY",   "SPDR S&P 500 ETF Trust",            "etf",    "NYSE",   "Broad Market",           "USD", 542.30,  0.10, 0.16, 0.0130,  90),
    ("QQQ",   "Invesco QQQ Trust Series I",        "etf",    "NASDAQ", "Broad Market",           "USD", 468.70,  0.13, 0.21, 0.0060,  85),
    ("VTI",   "Vanguard Total Stock Market ETF",   "etf",    "NYSE",   "Broad Market",           "USD", 268.40,  0.10, 0.16, 0.0135,  55),
    ("VOO",   "Vanguard S&P 500 ETF",              "etf",    "NYSE",   "Broad Market",           "USD", 498.20,  0.10, 0.16, 0.0135,  58),
    ("IWM",   "iShares Russell 2000 ETF",          "etf",    "NYSE",   "Small Cap",              "USD", 214.60,  0.08, 0.23, 0.0120,  30),
    ("AGG",   "iShares Core U.S. Aggregate Bond",  "etf",    "NYSE",   "Fixed Income",           "USD",  98.40,  0.03, 0.06, 0.0350,  20),
    ("GLD",   "SPDR Gold Shares",                  "etf",    "NYSE",   "Commodities",            "USD", 218.90,  0.07, 0.14, 0.0000,  35),
    ("ARKK",  "ARK Innovation ETF",                "etf",    "NYSE",   "Thematic",               "USD",  48.20,  0.06, 0.52, 0.0000,  28),

    # --- Australian listings (AUD) -------------------------------------------
    ("CBA.AX", "Commonwealth Bank of Australia",   "equity", "ASX",    "Financials",             "AUD", 128.40,  0.08, 0.19, 0.0380,  22),
    ("BHP.AX", "BHP Group Limited",                "equity", "ASX",    "Materials",              "AUD",  42.80,  0.06, 0.27, 0.0510,  20),
    ("CSL.AX", "CSL Limited",                      "equity", "ASX",    "Health Care",            "AUD", 292.60,  0.09, 0.22, 0.0130,  14),
    ("WES.AX", "Wesfarmers Limited",               "equity", "ASX",    "Consumer Discretionary", "AUD",  68.90,  0.09, 0.21, 0.0290,  12),
    ("VAS.AX", "Vanguard Australian Shares ETF",   "etf",    "ASX",    "Broad Market",           "AUD",  98.20,  0.07, 0.15, 0.0400,  16),

    # --- European listings ---------------------------------------------------
    ("ASML.AS", "ASML Holding N.V.",               "equity", "AEX",    "Information Technology", "EUR", 842.50,  0.16, 0.33, 0.0100,  18),
    ("SAP.DE",  "SAP SE",                          "equity", "XETRA",  "Information Technology", "EUR", 192.30,  0.12, 0.23, 0.0110,  12),
    ("SHEL.L",  "Shell plc",                       "equity", "LSE",    "Energy",                 "GBP",  28.40,  0.06, 0.24, 0.0390,  10),
    ("AZN.L",   "AstraZeneca PLC",                 "equity", "LSE",    "Health Care",            "GBP", 122.60,  0.09, 0.21, 0.0200,   9),

    # --- Crypto (traded 7 days a week -- see generate.py) --------------------
    ("BTC-USD", "Bitcoin",                         "crypto", "CRYPTO", "Digital Assets",         "USD", 62400.00, 0.30, 0.68, 0.0000, 88),
    ("ETH-USD", "Ethereum",                        "crypto", "CRYPTO", "Digital Assets",         "USD",  3120.00, 0.28, 0.75, 0.0000, 72),
    ("SOL-USD", "Solana",                          "crypto", "CRYPTO", "Digital Assets",         "USD",   142.60, 0.35, 0.95, 0.0000, 50),
]
# fmt: on

INSTRUMENT_COLUMNS = [
    "symbol",
    "instrument_name",
    "asset_class",
    "exchange",
    "sector",
    "currency",
    "start_price",
    "annual_drift",
    "annual_volatility",
    "dividend_yield",
    "popularity",
]

# Currency pairs quoted against the reporting currency (USD). Start rates are
# plausible round numbers; the walk is simulated in generate.py.
FX_PAIRS: list[tuple[str, str, float, float]] = [
    # base, quote, start_rate, annual_vol
    ("AUD", "USD", 0.6620, 0.09),
    ("EUR", "USD", 1.0840, 0.07),
    ("GBP", "USD", 1.2710, 0.08),
]

REPORTING_CURRENCY = "USD"

# Execution venues, weighted. Real venue names -- retail order flow in the US is
# overwhelmingly routed to wholesalers rather than to a lit exchange, and the
# weights reflect that so venue analysis in the marts is not uniform noise.
VENUES: list[tuple[str, int]] = [
    ("CITADEL_CONNECT", 34),
    ("VIRTU_AMERICAS", 22),
    ("JANE_STREET", 12),
    ("NYSE_ARCA", 10),
    ("NASDAQ_BX", 9),
    ("IEX", 5),
    ("CBOE_EDGX", 5),
    ("ASX_CENTREPOINT", 3),
]

# Countries the broker onboards from, weighted, with the national-ID format
# used by the generator. The ID is fake but shaped like the real thing, which
# is what makes it a useful test subject for the classification framework.
COUNTRIES: list[tuple[str, str, int]] = [
    # country_code, national_id_format, weight
    ("US", "###-##-####", 45),
    ("AU", "### ### ###", 20),
    ("GB", "@@ ## ## ## @", 12),
    ("CA", "### ### ###", 8),
    ("DE", "##############", 6),
    ("NL", "#########", 4),
    ("SG", "@#######@", 3),
    ("NZ", "##-###-###", 2),
]

ACCOUNT_TYPES: list[tuple[str, int]] = [
    ("cash", 55),
    ("margin", 30),
    ("retirement", 15),
]

CHANNELS: list[tuple[str, int]] = [
    ("ios", 38),
    ("android", 27),
    ("web", 30),
    ("api", 5),
]

ORDER_TYPES: list[tuple[str, int]] = [
    ("market", 58),
    ("limit", 34),
    ("stop", 5),
    ("stop_limit", 3),
]

# Terminal order states and their share of all orders. Retail cancel rates are
# high and reject rates are low but non-zero; both matter for the accumulating
# snapshot fact.
ORDER_STATUSES: list[tuple[str, int]] = [
    ("filled", 78),
    ("partially_filled", 6),
    ("cancelled", 13),
    ("rejected", 3),
]

APP_EVENT_TYPES: list[tuple[str, int]] = [
    ("session_start", 30),
    ("view_portfolio", 22),
    ("view_instrument", 18),
    ("search_instrument", 8),
    ("watchlist_add", 6),
    ("open_order_ticket", 7),
    ("view_statement", 4),
    ("update_profile", 2),
    ("kyc_document_upload", 1),
    ("session_end", 2),
]

DEVICE_FAMILIES: list[tuple[str, str, int]] = [
    # device_family, user_agent, weight
    ("iPhone", "TradeflowApp/4.2.1 (iPhone; iOS 17.5.1; Scale/3.00)", 32),
    ("iPad", "TradeflowApp/4.2.1 (iPad; iOS 17.5.1; Scale/2.00)", 5),
    ("Android", "TradeflowApp/4.2.0 (Linux; Android 14; Pixel 8)", 24),
    (
        "Chrome",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        22,
    ),
    (
        "Safari",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        13,
    ),
    ("API", "tradeflow-python-sdk/2.1.0", 4),
]

CASH_MOVEMENT_TYPES: list[tuple[str, int]] = [
    ("deposit", 40),
    ("withdrawal", 18),
    ("dividend", 24),
    ("fee", 14),
    ("interest", 4),
]

PAYMENT_METHODS: list[tuple[str, int]] = [
    ("bank_transfer", 46),
    ("card", 24),
    ("direct_debit", 18),
    ("payid", 8),
    ("wire", 4),
]

KYC_STATUSES: list[str] = ["pending", "verified", "rejected", "review_required"]

RISK_RATINGS: list[str] = ["low", "medium", "high"]

CUSTOMER_TIERS: list[str] = ["bronze", "silver", "gold", "platinum"]

# US market holidays observed by the generator's trading calendar. Enough years
# to cover the largest scale preset; equity markets close, crypto does not.
MARKET_HOLIDAYS: list[str] = [
    # 2023
    "2023-01-02",
    "2023-01-16",
    "2023-02-20",
    "2023-04-07",
    "2023-05-29",
    "2023-06-19",
    "2023-07-04",
    "2023-09-04",
    "2023-11-23",
    "2023-12-25",
    # 2024
    "2024-01-01",
    "2024-01-15",
    "2024-02-19",
    "2024-03-29",
    "2024-05-27",
    "2024-06-19",
    "2024-07-04",
    "2024-09-02",
    "2024-11-28",
    "2024-12-25",
    # 2025
    "2025-01-01",
    "2025-01-20",
    "2025-02-17",
    "2025-04-18",
    "2025-05-26",
    "2025-06-19",
    "2025-07-04",
    "2025-09-01",
    "2025-11-27",
    "2025-12-25",
    # 2026
    "2026-01-01",
    "2026-01-19",
    "2026-02-16",
    "2026-04-03",
    "2026-05-25",
    "2026-06-19",
    "2026-07-03",
    "2026-09-07",
    "2026-11-26",
    "2026-12-25",
    # 2027
    "2027-01-01",
    "2027-01-18",
    "2027-02-15",
    "2027-03-26",
    "2027-05-31",
    "2027-06-18",
    "2027-07-05",
    "2027-09-06",
    "2027-11-25",
    "2027-12-24",
]
