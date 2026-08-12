"""Figure builders. Shared by the Dash app and the static export.

One module so the interactive dashboard and the published HTML cannot drift into
showing different numbers -- which is the usual fate of a "quick static export"
written separately.

Each function picks its form from the data's job, per the procedure: magnitude ->
bar, change over time -> line or area, composition over time -> stacked area,
ordered category -> ordinal ramp. No dual axes anywhere; where two measures have
different scales they get two charts.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from dashboard import data
from dashboard.theme import (
    FILL_GAP,
    GRIDLINE,
    INK_MUTED,
    INK_SECONDARY,
    LINE_WIDTH,
    MARKER_SIZE,
    ORDINAL_BLUE,
    SERIES,
    STATUS,
    base_layout,
    count,
    money,
)


def _empty(message: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(**base_layout("No data"))
    figure.add_annotation(
        text=message, showarrow=False, font=dict(color=INK_MUTED, size=13)
    )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False)
    return figure


# ---------------------------------------------------------------------------- #
# Overview
# ---------------------------------------------------------------------------- #


def equity_composition() -> go.Figure:
    """Platform equity over time, split into cash and holdings.

    Stacked area because the job is composition-over-time: the two parts sum to a
    total that itself matters. A grouped line would show the same numbers and hide
    the total; a dual axis would be worse still.
    """
    frame = data.equity_curve()
    if frame.empty:
        return _empty("No account snapshots yet.")

    figure = go.Figure()
    for index, (column, label) in enumerate([("cash", "Cash"), ("holdings", "Holdings")]):
        figure.add_trace(
            go.Scatter(
                x=frame["snapshot_date"],
                y=frame[column],
                name=label,
                mode="lines",
                stackgroup="equity",
                line=dict(width=LINE_WIDTH, color=SERIES[index]),
                fillcolor=SERIES[index],
                opacity=0.85,
                hovertemplate=f"{label}: %{{y:$,.0f}}<extra></extra>",
            )
        )
    # Net funded as a reference line -- the capital customers actually put in.
    # Everything above it is gain. Drawn as a line, not a third stack segment,
    # because it is not a component of equity.
    figure.add_trace(
        go.Scatter(
            x=frame["snapshot_date"],
            y=frame["net_funded"],
            name="Net funded (capital in)",
            mode="lines",
            line=dict(width=LINE_WIDTH, color=INK_SECONDARY, dash="dot"),
            hovertemplate="Net funded: %{y:$,.0f}<extra></extra>",
        )
    )

    layout = base_layout(
        "Platform equity",
        f"Cash + holdings, {data.REPORTING_CURRENCY}. Dotted line is capital deposited.",
        height=380,
    )
    figure.update_layout(**layout)
    figure.update_yaxes(tickprefix="$", tickformat=",.0s")
    return figure


def daily_orders_and_fills() -> go.Figure:
    """Order and fill counts per day.

    Two series of the same unit and comparable scale, so one axis. If order count
    and traded notional were wanted together they would be two charts -- that is
    the dual-axis trap.
    """
    frame = data.daily_activity()
    if frame.empty:
        return _empty("No trading activity yet.")

    figure = go.Figure()
    for index, (column, label) in enumerate(
        [("orders", "Orders placed"), ("fills", "Fills"), ("cancelled", "Cancelled")]
    ):
        figure.add_trace(
            go.Scatter(
                x=frame["date_day"],
                y=frame[column],
                name=label,
                mode="lines",
                line=dict(width=LINE_WIDTH, color=SERIES[index]),
                hovertemplate=f"{label}: %{{y:,.0f}}<extra></extra>",
            )
        )

    figure.update_layout(
        **base_layout(
            "Daily activity",
            "Weekly seasonality is real: orders placed while the market is shut "
            "roll into the next session.",
        )
    )
    return figure


def notional_by_channel() -> go.Figure:
    """Traded value by channel, split by asset class.

    Horizontal stacked bar: the job is magnitude comparison across a handful of
    named categories, and horizontal keeps the labels readable without rotation.
    """
    frame = data.notional_by_channel()
    if frame.empty:
        return _empty("No executions yet.")

    pivot = frame.pivot_table(
        index="channel", columns="asset_class", values="notional", aggfunc="sum"
    ).fillna(0)
    pivot = pivot.loc[pivot.sum(axis=1).sort_values().index]

    figure = go.Figure()
    for index, asset_class in enumerate(pivot.columns):
        figure.add_trace(
            go.Bar(
                y=pivot.index,
                x=pivot[asset_class],
                name=asset_class,
                orientation="h",
                marker=dict(color=SERIES[index], line=FILL_GAP),
                hovertemplate=f"{asset_class}: %{{x:$,.0f}}<extra></extra>",
            )
        )

    layout = base_layout(
        "Traded value by channel",
        f"Gross notional, {data.REPORTING_CURRENCY}.",
    )
    layout["barmode"] = "stack"
    layout["bargap"] = 0.45
    layout["yaxis"].update(showgrid=False)
    layout["xaxis"].update(
        showgrid=True, gridcolor=GRIDLINE, tickprefix="$", tickformat=",.0s"
    )
    layout["hovermode"] = "y unified"
    figure.update_layout(**layout)
    return figure


def orders_by_hour() -> go.Figure:
    """Order volume by hour of day, split by outcome.

    The U-shape at the open and close is the point; a smooth line would imply
    continuity between 16:00 and 09:30 that does not exist.
    """
    frame = data.orders_by_hour()
    if frame.empty:
        return _empty("No orders yet.")

    pivot = frame.pivot_table(
        index="placed_hour", columns="order_status", values="orders", aggfunc="sum"
    ).fillna(0)
    order = ["filled", "partially_filled", "cancelled", "rejected"]
    columns = [column for column in order if column in pivot.columns]

    figure = go.Figure()
    for index, status in enumerate(columns):
        figure.add_trace(
            go.Bar(
                x=pivot.index,
                y=pivot[status],
                name=status.replace("_", " "),
                marker=dict(color=SERIES[index], line=FILL_GAP),
                hovertemplate=f"{status}: %{{y:,.0f}}<extra></extra>",
            )
        )

    layout = base_layout(
        "Orders by hour of day",
        "Clustered at the open and the close, as real retail flow is.",
    )
    layout["barmode"] = "stack"
    layout["bargap"] = 0.25
    figure.update_layout(**layout)
    figure.update_xaxes(dtick=2, title=dict(text="Hour (UTC)", font=dict(size=11)))
    return figure


# ---------------------------------------------------------------------------- #
# Customers
# ---------------------------------------------------------------------------- #


def cohort_equity() -> go.Figure:
    """Equity by signup cohort and tier. Stacked bar: composition per cohort."""
    frame = data.customer_cohorts()
    if frame.empty:
        return _empty("No customers yet.")

    frame["signup_month"] = pd.to_datetime(frame["signup_month"]).dt.strftime("%Y-%m")
    pivot = frame.pivot_table(
        index="signup_month", columns="customer_tier", values="equity", aggfunc="sum"
    ).fillna(0)
    tier_order = ["bronze", "silver", "gold", "platinum"]
    columns = [tier for tier in tier_order if tier in pivot.columns]

    figure = go.Figure()
    # Tier is an ordered category, so it takes the ordinal ramp rather than
    # categorical hues -- the ordering is information, and four unrelated hues
    # would throw it away.
    for index, tier in enumerate(columns):
        figure.add_trace(
            go.Bar(
                x=pivot.index,
                y=pivot[tier],
                name=tier,
                marker=dict(color=ORDINAL_BLUE[index], line=FILL_GAP),
                hovertemplate=f"{tier}: %{{y:$,.0f}}<extra></extra>",
            )
        )

    layout = base_layout(
        "Equity by signup cohort",
        "Tier shaded light to dark -- an ordered category, not four unrelated colours.",
    )
    layout["barmode"] = "stack"
    layout["bargap"] = 0.3
    figure.update_layout(**layout)
    figure.update_yaxes(tickprefix="$", tickformat=",.0s")
    return figure


def customer_value_scatter() -> go.Figure:
    """Commission paid against equity held, per customer.

    Coloured by `risk_rating` and not `customer_tier`. In a scatter every pair of
    colours sits adjacent, and the palette's all-pairs validation caps at three
    slots -- risk_rating has exactly three values, tier has four, and slot 4 beside
    slot 2 fails the separation floor.
    """
    frame = data.customer_value_distribution()
    if frame.empty:
        return _empty("No trading customers yet.")

    figure = go.Figure()
    for index, rating in enumerate(["low", "medium", "high"]):
        subset = frame[frame["risk_rating"] == rating]
        if subset.empty:
            continue
        figure.add_trace(
            go.Scattergl(
                x=subset["equity"],
                y=subset["commission"],
                name=f"{rating} risk",
                mode="markers",
                marker=dict(
                    size=MARKER_SIZE,
                    color=SERIES[index],
                    opacity=0.65,
                    # A 2px surface ring so overlapping points stay countable.
                    line=dict(width=1, color="#fcfcfb"),
                ),
                hovertemplate=(
                    f"{rating} risk<br>Equity: %{{x:$,.0f}}"
                    "<br>Commission: %{y:$,.2f}<extra></extra>"
                ),
            )
        )

    layout = base_layout(
        "Customer value",
        "Commission earned against equity held. Log scales -- both are heavy-tailed.",
        height=400,
    )
    layout["hovermode"] = "closest"
    figure.update_layout(**layout)
    figure.update_xaxes(
        type="log", tickprefix="$", title=dict(text="Equity held", font=dict(size=11))
    )
    figure.update_yaxes(
        type="log",
        tickprefix="$",
        title=dict(text="Commission paid", font=dict(size=11)),
    )
    return figure


# ---------------------------------------------------------------------------- #
# Instruments
# ---------------------------------------------------------------------------- #


def top_instruments() -> go.Figure:
    """Most-traded instruments. Single series, so no legend -- the title names it.

    Direct value labels on every bar: with 15 sorted bars the labels are the
    readable form, and it also discharges the palette's contrast obligation.
    """
    frame = data.top_instruments(15)
    if frame.empty:
        return _empty("No executions yet.")

    frame = frame.sort_values("notional")
    figure = go.Figure(
        go.Bar(
            y=frame["symbol"],
            x=frame["notional"],
            orientation="h",
            marker=dict(color=SERIES[0]),
            text=[money(value) for value in frame["notional"]],
            textposition="outside",
            textfont=dict(size=11, color=INK_SECONDARY),
            customdata=frame[["sector", "fills", "accounts"]],
            hovertemplate=(
                "<b>%{y}</b><br>%{customdata[0]}"
                "<br>Notional: %{x:$,.0f}"
                "<br>Fills: %{customdata[1]:,}"
                "<br>Accounts: %{customdata[2]:,}<extra></extra>"
            ),
        )
    )
    layout = base_layout(
        "Most-traded instruments",
        f"Gross notional, {data.REPORTING_CURRENCY}.",
        height=460,
    )
    layout["bargap"] = 0.45
    layout["yaxis"].update(showgrid=False)
    layout["xaxis"].update(showgrid=False, showticklabels=False, showline=False)
    layout["hovermode"] = "closest"
    layout["margin"]["r"] = 80
    figure.update_layout(**layout)
    return figure


def sector_exposure() -> go.Figure:
    """Market value held by sector. A bar, not a pie.

    Fourteen sectors in a pie chart is fourteen angles nobody can compare; sorted
    bars answer "which is biggest" and "by how much" at a glance.
    """
    frame = data.sector_exposure()
    if frame.empty:
        return _empty("No open positions yet.")

    frame = frame.sort_values("market_value")
    figure = go.Figure(
        go.Bar(
            y=frame["sector"],
            x=frame["market_value"],
            orientation="h",
            marker=dict(color=SERIES[0]),
            text=[money(value) for value in frame["market_value"]],
            textposition="outside",
            textfont=dict(size=11, color=INK_SECONDARY),
            customdata=frame[["holders", "unrealised_gain"]],
            hovertemplate=(
                "<b>%{y}</b><br>Market value: %{x:$,.0f}"
                "<br>Accounts holding: %{customdata[0]:,}"
                "<br>Unrealised: %{customdata[1]:$,.0f}<extra></extra>"
            ),
        )
    )
    layout = base_layout(
        "Sector exposure",
        "Market value of open positions at the latest snapshot.",
        height=460,
    )
    layout["bargap"] = 0.45
    layout["yaxis"].update(showgrid=False)
    layout["xaxis"].update(showgrid=False, showticklabels=False, showline=False)
    layout["hovermode"] = "closest"
    layout["margin"]["r"] = 80
    figure.update_layout(**layout)
    return figure


# ---------------------------------------------------------------------------- #
# Data quality
# ---------------------------------------------------------------------------- #


def rejects_by_reason() -> go.Figure:
    """What the quarantine caught, by reason.

    Empty on a clean run, which is the honest answer -- and the chart says so
    rather than rendering an empty axis.
    """
    frame = data.quality_by_reason()
    if frame.empty:
        return _empty(
            "No rows quarantined. Run `make demo-anomalies` to plant defects "
            "and see this populate."
        )

    frame = frame.sort_values("rows")
    figure = go.Figure(
        go.Bar(
            y=frame["reject_reason"].str.replace("_", " "),
            x=frame["rows"],
            orientation="h",
            # A status colour, paired with a label -- state is never hue alone.
            marker=dict(color=STATUS["critical"]),
            text=[count(value) for value in frame["rows"]],
            textposition="outside",
            textfont=dict(size=11, color=INK_SECONDARY),
            customdata=frame[["model_name"]],
            hovertemplate=(
                "<b>%{y}</b><br>Model: %{customdata[0]}"
                "<br>Rows quarantined: %{x:,}<extra></extra>"
            ),
        )
    )
    layout = base_layout(
        "Quarantined rows by reason",
        "Rows held back from the marts, with the check that rejected them.",
    )
    layout["bargap"] = 0.45
    layout["yaxis"].update(showgrid=False)
    layout["xaxis"].update(showgrid=False, showticklabels=False, showline=False)
    layout["hovermode"] = "closest"
    layout["margin"]["r"] = 70
    figure.update_layout(**layout)
    return figure


def reject_rate_over_time() -> go.Figure:
    """Reject rate per model per day, against the gate threshold.

    A rate, not a count: a raw count of bad rows rises with volume and says
    nothing about whether quality changed.
    """
    frame = data.quality_over_time()
    if frame.empty:
        return _empty("No screened rows yet.")

    figure = go.Figure()
    for index, model_name in enumerate(sorted(frame["model_name"].unique())):
        subset = frame[frame["model_name"] == model_name]
        figure.add_trace(
            go.Scatter(
                x=subset["activity_date"],
                y=subset["reject_rate"],
                name=model_name,
                mode="lines",
                line=dict(width=LINE_WIDTH, color=SERIES[index]),
                hovertemplate=f"{model_name}: %{{y:.3%}}<extra></extra>",
            )
        )

    threshold = 0.001
    figure.add_hline(
        y=threshold,
        line=dict(color=STATUS["critical"], width=1, dash="dash"),
        annotation=dict(
            text="gate threshold 0.1%",
            font=dict(size=10, color=STATUS["critical"]),
            xanchor="left",
        ),
        annotation_position="top left",
    )

    figure.update_layout(
        **base_layout(
            "Reject rate",
            "Above the dashed line, an upstream system has changed shape and the "
            "build stops.",
        )
    )
    figure.update_yaxes(tickformat=".2%")
    return figure


def stale_price_share() -> go.Figure:
    """Share of position snapshots priced from an earlier session.

    Expected to sit near 28% -- positions exist every day, equities are priced only
    on trading days, and the ASOF price join carries the last close forward. A
    number that is supposed to be 28% is only reassuring if you can watch it stay
    there.
    """
    frame = data.stale_price_share()
    if frame.empty:
        return _empty("No position snapshots yet.")

    figure = go.Figure(
        go.Scatter(
            x=frame["snapshot_date"],
            y=frame["stale_share"],
            mode="lines",
            name="Stale-priced share",
            line=dict(width=LINE_WIDTH, color=SERIES[1]),
            fill="tozeroy",
            fillcolor="rgba(235,104,52,0.12)",
            hovertemplate="%{y:.1%} of positions<extra></extra>",
        )
    )
    figure.update_layout(
        **base_layout(
            "Positions priced from an earlier session",
            "Weekends and holidays. Expected, bounded, and worth watching.",
        )
    )
    figure.update_yaxes(tickformat=".0%", rangemode="tozero")
    return figure


# ---------------------------------------------------------------------------- #
# Governance
# ---------------------------------------------------------------------------- #


def classification_distribution() -> go.Figure:
    """Columns by sensitivity classification.

    Sensitivity is ordered, so this takes the ordinal blue ramp light-to-dark
    rather than four categorical hues: the ordering is the information.
    """
    frame = data.classification_summary()
    if frame.empty:
        return _empty("No classified columns found.")

    figure = go.Figure(
        go.Bar(
            x=frame["classification"],
            y=frame["columns"],
            marker=dict(
                color=[ORDINAL_BLUE[min(rank, 3)] for rank in frame["rank"]],
                line=FILL_GAP,
            ),
            text=frame["columns"],
            textposition="outside",
            textfont=dict(size=11, color=INK_SECONDARY),
            hovertemplate="<b>%{x}</b><br>%{y:,} columns<extra></extra>",
        )
    )
    layout = base_layout(
        "Columns by classification",
        "Shaded light to dark by sensitivity. Generated from the dbt tags.",
    )
    layout["bargap"] = 0.5
    layout["hovermode"] = "closest"
    layout["yaxis"].update(showgrid=False, showticklabels=False)
    figure.update_layout(**layout)
    return figure
