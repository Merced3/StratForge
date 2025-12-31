# web_dash/charts/theme.py

# Color theme for charts
PAPER_BG = "#dfe3e8"   # overall page bg
PLOT_BG  = "#d4d8df"   # darker plot area so bright lines pop
GRID     = "#b8c0cb"   # thin grid that stays visible on the darker plot bg

# Candle colors
GREEN    = "#16a34a"
RED      = "#ef4444"

def apply_layout(fig, title, uirevision):
    fig.update_layout(
        title=title,
        margin=dict(l=30, r=20, t=40, b=30),
        paper_bgcolor=PAPER_BG, plot_bgcolor=PLOT_BG,
        xaxis=dict(title=None, showspikes=True, spikemode="across", spikesnap="cursor"),
        yaxis=dict(title=None, gridcolor=GRID, zeroline=False),
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=700, uirevision=uirevision,
    )
