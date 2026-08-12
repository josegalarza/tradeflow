"""Render the dashboard to a single self-contained HTML file.

The interactive Dash app requires a Python process, a built warehouse, and
someone willing to clone the repo. Most people looking at a portfolio project
will do none of those things -- so CI runs this and publishes the result to GitHub
Pages, where the charts are live, interactive and one click away.

Everything is inlined: Plotly's JS is embedded rather than loaded from a CDN, so
the page works offline and cannot break when a CDN version moves. It costs about
3 MB, which is the right trade for a page that has to work in five years.

Uses the same figure builders as the app, so the published page cannot drift from
the interactive one.

Usage::

    python -m dashboard.export
    python -m dashboard.export --out site/index.html
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import plotly.io as pio

from dashboard import data, figures
from dashboard.theme import (
    BASELINE,
    FONT_FAMILY,
    GRIDLINE,
    INK_MUTED,
    INK_PRIMARY,
    INK_SECONDARY,
    PAGE,
    SURFACE,
    count,
    money,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "dashboard" / "static_export" / "index.html"

PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}


def _figure_html(figure, include_js: bool) -> str:
    return pio.to_html(
        figure,
        include_plotlyjs=include_js,
        full_html=False,
        config=PLOTLY_CONFIG,
        default_height="100%",
    )


def _tile(label: str, value: str, note: str) -> str:
    return f"""
      <div class="tile">
        <div class="tile-label">{label}</div>
        <div class="tile-value">{value}</div>
        <div class="tile-note">{note}</div>
      </div>"""


def _table(frame, title: str, note: str, max_rows: int = 120) -> str:
    """A labelled table.

    Titled and captioned rather than bare, because these tables are also the
    *relief* the palette's contrast check obliges: two of its categorical slots
    sit below 3:1 on the light surface, and the remedy is that the same numbers
    are readable as text. An unlabelled table does not discharge that.
    """
    heading = (
        f'<div class="table-title">{title}</div><div class="table-note">{note}</div>'
    )
    if frame.empty:
        return f"{heading}<p class='muted'>Nothing to show for this run.</p>"
    body = frame.head(max_rows).to_html(
        index=False, border=0, classes="data-table", escape=False
    )
    footer = (
        f'<div class="table-note">Showing {min(len(frame), max_rows):,} '
        f"of {len(frame):,} rows.</div>"
        if len(frame) > max_rows
        else ""
    )
    return heading + body + footer


def render() -> str:
    kpis = data.kpis()
    manifest = data.generator_manifest()
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    # Plotly's JS goes in with the first figure only; repeating it per figure
    # would multiply a 3 MB payload by the number of charts.
    charts = [
        ("Platform equity", figures.equity_composition()),
        ("Daily activity", figures.daily_orders_and_fills()),
        ("Orders by hour", figures.orders_by_hour()),
        ("Traded value by channel", figures.notional_by_channel()),
        ("Equity by signup cohort", figures.cohort_equity()),
        ("Customer value", figures.customer_value_scatter()),
        ("Most-traded instruments", figures.top_instruments()),
        ("Sector exposure", figures.sector_exposure()),
        ("Quarantined rows", figures.rejects_by_reason()),
        ("Reject rate", figures.reject_rate_over_time()),
        ("Stale-priced positions", figures.stale_price_share()),
        ("Columns by classification", figures.classification_distribution()),
    ]
    rendered = [
        _figure_html(figure, include_js=(index == 0))
        for index, (_, figure) in enumerate(charts)
    ]

    tiles = "".join(
        [
            _tile(
                "PLATFORM EQUITY",
                money(kpis.get("total_equity") or 0),
                f"across {count(kpis.get('open_accounts') or 0)} open accounts",
            ),
            _tile(
                "CUSTOMERS",
                count(kpis.get("customers") or 0),
                f"{count(kpis.get('trading_customers') or 0)} have traded",
            ),
            _tile(
                "LIFETIME TRADED",
                money(kpis.get("lifetime_notional") or 0),
                f"{count(kpis.get('lifetime_fills') or 0)} fills",
            ),
            _tile(
                "COMMISSION EARNED",
                money(kpis.get("lifetime_commission") or 0),
                f"reject rate {(kpis.get('reject_rate') or 0):.3%}",
            ),
        ]
    )

    sections = [
        ("Overview", rendered[0:4], None),
        (
            "Customers",
            rendered[4:6],
            _table(
                data.customer_cohorts(),
                "Signup cohorts",
                "The same figures as the chart above, for anyone who would rather "
                "read them.",
            ),
        ),
        ("Instruments", rendered[6:8], None),
        (
            "Data quality",
            rendered[8:11],
            _table(
                data.quality_by_reason(),
                "Quarantine detail",
                "Every reject reason and its row count. Empty on a clean run.",
            ),
        ),
        (
            "Governance",
            rendered[11:12],
            _table(
                data.pii_register(),
                "PII register",
                "Every column carrying personal data, and how each role sees it. "
                "'clear' means unmasked; 'withheld' means the column is absent "
                "from that role's view entirely. Generated from the dbt tags.",
                max_rows=200,
            ),
        ),
    ]

    body = []
    for title, chart_html, table_html in sections:
        body.append(f'<h2 id="{title.lower().replace(" ", "-")}">{title}</h2>')
        body.append('<div class="grid">')
        for chunk in chart_html:
            body.append(f'<div class="card">{chunk}</div>')
        body.append("</div>")
        if table_html:
            body.append(f'<div class="card table-card">{table_html}</div>')

    nav = " · ".join(
        f'<a href="#{title.lower().replace(" ", "-")}">{title}</a>'
        for title, _, _ in sections
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>tradeflow — synthetic brokerage warehouse</title>
<style>
  :root {{
    --surface: {SURFACE};
    --page: {PAGE};
    --ink: {INK_PRIMARY};
    --ink-2: {INK_SECONDARY};
    --muted: {INK_MUTED};
    --grid: {GRIDLINE};
    --baseline: {BASELINE};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--page); color: var(--ink);
    font-family: {FONT_FAMILY}; font-size: 14px; line-height: 1.5;
  }}
  .wrap {{ max-width: 1320px; margin: 0 auto; padding: 24px 20px 48px; }}
  header {{ border-bottom: 1px solid var(--baseline); padding-bottom: 12px; margin-bottom: 8px; }}
  h1 {{ font-size: 22px; font-weight: 700; margin: 0 0 2px; letter-spacing: -0.01em; }}
  .sub {{ color: var(--muted); font-size: 13px; }}
  nav {{ margin: 12px 0 20px; font-size: 13px; }}
  nav a {{ color: var(--ink-2); text-decoration: none; }}
  nav a:hover {{ text-decoration: underline; }}
  h2 {{ font-size: 18px; font-weight: 650; margin: 32px 0 12px; }}
  .tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin-bottom: 8px; }}
  .tile {{ background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 16px 18px; }}
  .tile-label {{ font-size: 10px; letter-spacing: .08em; color: var(--muted); font-weight: 600; }}
  .tile-value {{ font-size: 26px; font-weight: 650; margin-top: 4px; font-variant-numeric: tabular-nums; }}
  .tile-note {{ font-size: 11px; color: var(--muted); }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(460px, 1fr)); gap: 12px; }}
  .card {{ background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 14px; overflow: hidden; }}
  .table-card {{ margin-top: 12px; max-height: 520px; overflow: auto; }}
  .table-title {{ font-size: 15px; font-weight: 600; color: var(--ink); }}
  .table-note {{ font-size: 12px; color: var(--muted); margin-bottom: 10px; }}
  table.data-table {{ width: 100%; border-collapse: collapse; font-size: 12px; color: var(--ink-2); }}
  table.data-table th {{ text-align: left; font-weight: 600; color: var(--muted);
    font-size: 10px; letter-spacing: .05em; text-transform: uppercase;
    border-bottom: 1px solid var(--grid); padding: 6px 10px; position: sticky; top: 0; background: var(--surface); }}
  table.data-table td {{ padding: 5px 10px; border-bottom: 1px solid var(--grid); white-space: nowrap; }}
  .muted {{ color: var(--muted); font-size: 12px; }}
  footer {{ margin-top: 36px; padding-top: 14px; border-top: 1px solid var(--grid);
    color: var(--muted); font-size: 11px; }}
  @media (max-width: 620px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>tradeflow</h1>
    <div class="sub">
      Local-first analytics engineering platform for a synthetic retail
      brokerage — dbt, DuckDB, Dagster, Dash.
    </div>
  </header>
  <nav>{nav}</nav>

  <div class="tiles">{tiles}</div>

  {"".join(body)}

  <footer>
    Generated {generated_at} from a
    <strong>{manifest.get("scale", "?")}</strong>-scale synthetic dataset
    ({manifest.get("total_rows", 0):,} source rows, seed
    {manifest.get("seed", "?")}).<br>
    Instrument symbols, names, sectors and exchanges are real-world reference
    data. Prices are a simulated random walk and every customer, account, order
    and fill is generated. This is not market data and not investment advice.
  </footer>
</div>
</body>
</html>
"""


def export(out: Path | None = None) -> Path:
    destination = out or DEFAULT_OUT
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render())
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    try:
        destination = export(args.out)
    except data.WarehouseUnavailable as error:
        print(f"error: {error}")
        return 1

    size_mb = destination.stat().st_size / 1_048_576
    print(f"wrote {destination} ({size_mb:.1f} MB, self-contained)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
