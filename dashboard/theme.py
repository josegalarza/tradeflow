"""Chart theme: one palette, one set of mark specs, applied everywhere.

The palette is validated rather than chosen by eye. Running the reference
validator over these four slots on the light surface gives:

    Lightness band       PASS  all 4 inside L 0.43-0.77
    Chroma floor         PASS  all 4 >= 0.1
    CVD separation       PASS  worst adjacent yellow<->aqua dE 9.1 (protan)
    Normal-vision floor  PASS  worst adjacent dE 22.9
    Contrast vs surface  WARN  aqua 2.74 and yellow 2.11 are below 3:1

That WARN is not dismissable: it obligates *relief* -- every series using aqua or
yellow carries a legend entry and either a direct label or a table view of the
same numbers. Both are shipped, which is why the palette is used as-is rather
than re-stepped.

Two consequences worth knowing before adding a chart:

* **Slots are assigned in fixed order and never cycled.** A ninth series is not a
  ninth hue; it folds into "Other" or the chart becomes small multiples.
* **All-pairs forms cap at three slots.** In a scatter or bubble chart every pair
  of colours is adjacent, and slot 4 (yellow) beside slot 2 (orange) fails the
  separation floor. So the customer scatter is coloured by `risk_rating` -- which
  has exactly three values -- and not by `customer_tier`, which has four.

The theme commits to a single light surface. A runtime dark mode would mean
either two baked figure sets or JS re-layout on a static export, and a
half-implemented dark mode that leaves the plot area light is worse than an
honest single surface.
"""

from __future__ import annotations

# Categorical slots, in fixed assignment order.
SERIES = [
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua      (sub-3:1 -- direct labels or table required)
    "#eda100",  # 4 yellow    (sub-3:1 -- direct labels or table required)
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
]

#: Ordinal steps for ordered categories (classification levels). Starts at step
#: 250 because anything lighter fails the 2:1 floor against the light surface.
ORDINAL_BLUE = ["#86b6ef", "#3987e5", "#256abf", "#104281"]

#: Reserved status colours. Never reused as a series colour, and always paired
#: with a label so state is never carried by hue alone.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

FONT_FAMILY = (
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, '
    "Helvetica, Arial, sans-serif"
)

#: Mark specs. Thin marks, recessive chrome, generous hit targets.
LINE_WIDTH = 2
MARKER_SIZE = 8
#: A 2px surface-coloured gap between adjacent fills, so stacked segments read as
#: separate quantities rather than one blurred mass.
FILL_GAP = dict(width=2, color=SURFACE)


def base_layout(title: str, subtitle: str = "", height: int = 360) -> dict:
    """Layout shared by every figure.

    Titles and labels wear ink tokens, never a series colour: a coloured mark
    beside a label carries the identity, and colouring the text as well makes the
    chart louder without making it clearer.
    """
    heading = title
    if subtitle:
        heading = (
            f"{title}<br><span style='font-size:12px;color:{INK_MUTED}'>{subtitle}</span>"
        )
    return dict(
        title=dict(
            text=heading,
            font=dict(size=15, color=INK_PRIMARY, family=FONT_FAMILY),
            x=0,
            xanchor="left",
            y=0.97,
        ),
        height=height,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT_FAMILY, size=12, color=INK_SECONDARY),
        margin=dict(l=8, r=16, t=64 if subtitle else 52, b=8),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            linecolor=BASELINE,
            linewidth=1,
            ticks="outside",
            tickcolor=BASELINE,
            ticklen=4,
            tickfont=dict(color=INK_MUTED, size=11),
            automargin=True,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=GRIDLINE,
            gridwidth=1,
            zeroline=False,
            showline=False,
            tickfont=dict(color=INK_MUTED, size=11),
            automargin=True,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.0,
            xanchor="right",
            x=1.0,
            font=dict(size=11, color=INK_SECONDARY),
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
        ),
        # Crosshair + shared tooltip: an HTML chart is interactive, so the hover
        # layer ships by default rather than on request.
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=SURFACE,
            bordercolor=BASELINE,
            font=dict(family=FONT_FAMILY, size=12, color=INK_PRIMARY),
        ),
        dragmode=False,
    )


def money(value: float) -> str:
    """Compact currency, for labels and tiles."""
    for threshold, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= threshold:
            return f"${value / threshold:,.1f}{suffix}"
    return f"${value:,.0f}"


def count(value: float) -> str:
    for threshold, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= threshold:
            return f"{value / threshold:,.1f}{suffix}"
    return f"{value:,.0f}"
