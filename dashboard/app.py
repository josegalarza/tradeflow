"""Multi-page Dash app over the tradeflow marts.

Five pages, each answering a different question:

    Overview     -- is the business working?
    Customers    -- who are they and what are they worth?
    Instruments  -- what are they trading?
    Data quality -- can I trust these numbers?
    Governance   -- who can see what?

The last two matter as much as the first three. A dashboard that only shows
business metrics asks to be trusted; one that shows its own reject rates and its
own access policy earns it.

Run with `make dash`, then open http://localhost:8050.
"""

from __future__ import annotations

import os

import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, dcc, html

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

GRAPH_CONFIG = {
    "displayModeBar": False,
    "responsive": True,
    "scrollZoom": False,
}

CARD_STYLE = {
    "backgroundColor": SURFACE,
    "border": f"1px solid {GRIDLINE}",
    "borderRadius": "10px",
    "padding": "16px 18px",
    "height": "100%",
}


def stat_tile(label: str, value: str, note: str = "") -> dbc.Col:
    """A hero number. Deliberately not a chart.

    A single figure with no comparison has no shape to plot; a gauge or a
    one-segment donut would be decoration around a number that is already the
    whole message.
    """
    return dbc.Col(
        html.Div(
            [
                html.Div(
                    label.upper(),
                    style={
                        "fontSize": "10px",
                        "letterSpacing": "0.08em",
                        "color": INK_MUTED,
                        "fontWeight": 600,
                    },
                ),
                html.Div(
                    value,
                    style={
                        "fontSize": "26px",
                        "fontWeight": 650,
                        "color": INK_PRIMARY,
                        "lineHeight": "1.25",
                        "marginTop": "4px",
                        "fontVariantNumeric": "tabular-nums",
                    },
                ),
                html.Div(
                    note,
                    style={"fontSize": "11px", "color": INK_MUTED, "marginTop": "2px"},
                ),
            ],
            style=CARD_STYLE,
        ),
        width=12,
        md=6,
        xl=3,
        class_name="mb-3",
    )


def graph_card(figure_id: str, figure) -> dbc.Col:
    return dbc.Col(
        html.Div(
            dcc.Graph(id=figure_id, figure=figure, config=GRAPH_CONFIG),
            style=CARD_STYLE,
        ),
        width=12,
        class_name="mb-3",
    )


def half_card(figure_id: str, figure) -> dbc.Col:
    return dbc.Col(
        html.Div(
            dcc.Graph(id=figure_id, figure=figure, config=GRAPH_CONFIG),
            style=CARD_STYLE,
        ),
        width=12,
        lg=6,
        class_name="mb-3",
    )


def table_card(title: str, note: str, frame, max_rows: int = 400) -> dbc.Col:
    """A table view of the same numbers.

    Present on every page that uses a low-contrast series colour: the palette's
    contrast check warns on two of its slots, and the obligation that creates is
    relief -- visible labels or a table. This is the table half of that.
    """
    display = frame.head(max_rows)
    return dbc.Col(
        html.Div(
            [
                html.Div(
                    title,
                    style={
                        "fontSize": "15px",
                        "fontWeight": 600,
                        "color": INK_PRIMARY,
                    },
                ),
                html.Div(
                    note,
                    style={
                        "fontSize": "12px",
                        "color": INK_MUTED,
                        "marginBottom": "10px",
                    },
                ),
                dbc.Table.from_dataframe(
                    display,
                    striped=False,
                    bordered=False,
                    hover=True,
                    responsive=True,
                    size="sm",
                    style={"fontSize": "12px", "color": INK_SECONDARY},
                ),
            ],
            style={**CARD_STYLE, "maxHeight": "520px", "overflowY": "auto"},
        ),
        width=12,
        class_name="mb-3",
    )


def section(title: str, body: str = "") -> dbc.Row:
    children = [
        html.H2(
            title,
            style={
                "fontSize": "18px",
                "fontWeight": 650,
                "color": INK_PRIMARY,
                "marginBottom": "2px",
            },
        )
    ]
    if body:
        children.append(
            html.P(
                body,
                style={
                    "fontSize": "13px",
                    "color": INK_SECONDARY,
                    "maxWidth": "820px",
                    "marginBottom": "14px",
                },
            )
        )
    return dbc.Row(dbc.Col(children, width=12), class_name="mt-2")


# ---------------------------------------------------------------------------- #
# Pages
# ---------------------------------------------------------------------------- #


def overview_page() -> html.Div:
    kpis = data.kpis()
    manifest = data.generator_manifest()
    scale = manifest.get("scale", "unknown")
    rows = manifest.get("total_rows", 0)

    return html.Div(
        [
            section(
                "Overview",
                "A fictional retail brokerage. Every figure below is computed "
                "from the dimensional marts, never from staging -- if a number is "
                "not in a mart, the fix is a model, not a join in this app.",
            ),
            dbc.Row(
                [
                    stat_tile(
                        "Platform equity",
                        money(kpis.get("total_equity") or 0),
                        f"across {count(kpis.get('open_accounts') or 0)} open accounts",
                    ),
                    stat_tile(
                        "Customers",
                        count(kpis.get("customers") or 0),
                        f"{count(kpis.get('trading_customers') or 0)} have traded",
                    ),
                    stat_tile(
                        "Lifetime traded",
                        money(kpis.get("lifetime_notional") or 0),
                        f"{count(kpis.get('lifetime_fills') or 0)} fills",
                    ),
                    stat_tile(
                        "Commission earned",
                        money(kpis.get("lifetime_commission") or 0),
                        f"reject rate {(kpis.get('reject_rate') or 0):.3%}",
                    ),
                ]
            ),
            dbc.Row([graph_card("equity", figures.equity_composition())]),
            dbc.Row(
                [
                    half_card("daily", figures.daily_orders_and_fills()),
                    half_card("hours", figures.orders_by_hour()),
                ]
            ),
            dbc.Row([graph_card("channel", figures.notional_by_channel())]),
            html.P(
                f"Data: synthetic, scale={scale}, {rows:,} source rows. "
                "Instrument names and sectors are real; prices are simulated and "
                "all customer data is generated.",
                style={"fontSize": "11px", "color": INK_MUTED},
            ),
        ]
    )


def customers_page() -> html.Div:
    cohorts = data.customer_cohorts()
    return html.Div(
        [
            section(
                "Customers",
                "Built on agg_customer_performance, which joins the current "
                "version of the Type 2 customer dimension. This page asks a "
                "present-tense question, which is the one case where filtering a "
                "Type 2 dimension on is_current is right rather than wrong.",
            ),
            dbc.Row([graph_card("cohorts", figures.cohort_equity())]),
            dbc.Row([graph_card("value", figures.customer_value_scatter())]),
            dbc.Row(
                [
                    table_card(
                        "Cohorts",
                        "The same numbers as the chart above, for anyone who would "
                        "rather read them.",
                        cohorts.assign(
                            equity=cohorts["equity"].map(money),
                            notional=cohorts["notional"].map(money),
                            mean_fills=cohorts["mean_fills"].round(1),
                        ),
                    )
                ]
            ),
        ]
    )


def instruments_page() -> html.Div:
    return html.Div(
        [
            section(
                "Instruments",
                "Instrument reference data is real -- symbols, names, sectors, "
                "exchanges, listing currencies. Prices are a simulated random "
                "walk, so the returns below mean nothing about any real security.",
            ),
            dbc.Row(
                [
                    half_card("top", figures.top_instruments()),
                    half_card("sectors", figures.sector_exposure()),
                ]
            ),
        ]
    )


def quality_page() -> html.Div:
    quality = data.quality_by_reason()
    return html.Div(
        [
            section(
                "Data quality",
                "The pipeline quarantines defective rows rather than dropping "
                "them, and records why. On a clean run these charts are empty; "
                "run `make demo-anomalies` to plant defects and watch the "
                "detectors fire, the quarantine fill, and every mart still build.",
            ),
            dbc.Row(
                [
                    half_card("rejects", figures.rejects_by_reason()),
                    half_card("rate", figures.reject_rate_over_time()),
                ]
            ),
            dbc.Row([graph_card("stale", figures.stale_price_share())]),
            dbc.Row(
                [
                    table_card(
                        "Quarantine detail",
                        "Every reject reason and its row count.",
                        quality
                        if not quality.empty
                        else quality.assign(**{"(no rows quarantined)": []}),
                    )
                ]
            ),
        ]
    )


def governance_page() -> html.Div:
    register = data.pii_register()
    inventory = data.warehouse_inventory()
    return html.Div(
        [
            section(
                "Governance",
                "Every column in the warehouse carries a sensitivity "
                "classification, and those tags generate both the masked role "
                "views and this page. The register below is the artefact a "
                "subject-access request actually needs.",
            ),
            dbc.Row([half_card("classes", figures.classification_distribution())]),
            dbc.Row(
                [
                    table_card(
                        "PII register",
                        "Every column carrying personal data, and how each role "
                        "sees it. 'clear' means unmasked; 'withheld' means the "
                        "column is absent from that role's view entirely.",
                        register,
                    )
                ]
            ),
            dbc.Row(
                [
                    table_card(
                        "Warehouse inventory",
                        "Every table, by layer.",
                        inventory,
                    )
                ]
            ),
        ]
    )


PAGES = {
    "/": ("Overview", overview_page),
    "/customers": ("Customers", customers_page),
    "/instruments": ("Instruments", instruments_page),
    "/quality": ("Data quality", quality_page),
    "/governance": ("Governance", governance_page),
}


def build_app() -> Dash:
    app = Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        title="tradeflow",
        suppress_callback_exceptions=True,
    )

    nav = dbc.Nav(
        [
            dbc.NavLink(
                label,
                href=path,
                active="exact",
                style={"fontSize": "13px", "padding": "6px 12px"},
            )
            for path, (label, _) in PAGES.items()
        ],
        pills=True,
        class_name="mb-3",
    )

    app.layout = html.Div(
        [
            dcc.Location(id="url"),
            dbc.Container(
                [
                    html.Div(
                        [
                            html.Span(
                                "tradeflow",
                                style={
                                    "fontSize": "20px",
                                    "fontWeight": 700,
                                    "color": INK_PRIMARY,
                                    "letterSpacing": "-0.01em",
                                },
                            ),
                            html.Span(
                                "  synthetic brokerage warehouse",
                                style={"fontSize": "13px", "color": INK_MUTED},
                            ),
                        ],
                        style={
                            "paddingTop": "20px",
                            "paddingBottom": "10px",
                            "borderBottom": f"1px solid {BASELINE}",
                            "marginBottom": "14px",
                        },
                    ),
                    nav,
                    html.Div(id="page-content"),
                    html.Div(
                        "Synthetic data. Not market data, not investment advice.",
                        style={
                            "fontSize": "11px",
                            "color": INK_MUTED,
                            "padding": "18px 0",
                        },
                    ),
                ],
                fluid=True,
                style={"maxWidth": "1320px"},
            ),
        ],
        style={
            "backgroundColor": PAGE,
            "minHeight": "100vh",
            "fontFamily": FONT_FAMILY,
        },
    )

    @app.callback(Output("page-content", "children"), Input("url", "pathname"))
    def render(pathname: str):
        try:
            _, builder = PAGES.get(pathname, PAGES["/"])
            return builder()
        except data.WarehouseUnavailable as error:
            return dbc.Alert(
                [
                    html.Strong("The warehouse has not been built yet. "),
                    html.Span(str(error)),
                ],
                color="warning",
            )

    return app


def main() -> None:
    app = build_app()
    port = int(os.environ.get("TRADEFLOW_DASH_PORT", "8050"))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
