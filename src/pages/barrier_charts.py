import plotly.graph_objects as go

from src import data
from src.styles import PALETTE, style_chart


def district_family_figure(rows):
    family_shares = data.barrier_family_shares(rows).set_index("Barrier family")[
        "Weighted share (%)"
    ]
    family_shares = (
        family_shares.reindex(data.BARRIER_FAMILY_ORDER)
        .dropna()
        .sort_values(ascending=True)
    )
    figure = go.Figure(
        go.Bar(
            x=family_shares.values,
            y=family_shares.index,
            orientation="h",
            marker=dict(
                color=[
                    data.BARRIER_FAMILY_COLORS[family]
                    for family in family_shares.index
                ]
            ),
            text=family_shares.values,
            texttemplate="%{text:.1f}%",
            textposition="outside",
            textfont=dict(size=12, color=PALETTE["ink"]),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{x:.2f}%<extra></extra>",
        )
    )
    figure.update_layout(bargap=0.3)
    figure.update_xaxes(
        range=[0, 100],
        ticksuffix="%",
        title=None,
        gridcolor=PALETTE["grid"],
        zeroline=False,
    )
    figure.update_yaxes(
        title=None, showgrid=False, automargin=True, tickfont=dict(size=12)
    )
    return style_chart(figure, 330, margin=dict(l=4, r=40, t=8, b=4))
