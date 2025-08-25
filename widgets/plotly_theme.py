import typing

if typing.TYPE_CHECKING:
    import plotly.graph_objects as go

# Modern color palette with 27 distinct colors
COLOR_PALETTE = [
    "#FF6B6B", "#45B7D1", "#96CEB4", "#FFEEAD", "#D4A5A5", "#9B59B6", "#3498DB", "#E74C3C", "#2ECC71", "#F1C40F",
    "#E67E22", "#1ABC9C", "#9B59B6", "#34495E", "#E74C3C", "#3498DB", "#2ECC71", "#F1C40F", "#E67E22", "#1ABC9C",
    "#9B59B6", "#34495E", "#E74C3C", "#3498DB", "#2ECC71", "#F1C40F",
]  # fmt: skip

defaultPlotlyConfig = {"displayModeBar": False, "displaylogo": False}


def apply_consistent_styling(fig: "go.Figure") -> "go.Figure":
    """Apply consistent styling from analysis_results.py"""
    fig.update_layout(
        template="plotly_white",
        font=dict(size=12, family="basiercircle,sans-serif"),
        polar=dict(
            radialaxis=dict(angle=90, tickangle=90),
            angularaxis=dict(rotation=25),
        ),
        dragmode=False,
        autosize=True,
        hovermode="x unified",
        hoverdistance=1000,
        hoversubplots="axis",
    )
    fig.update_xaxes(
        spikemode="across",
        spikedash="solid",
        spikecolor="rgba(126, 87, 194, 0.25)",  # soft purple, semi-transparent
        spikethickness=1,
    )
    return fig
