from pathlib import Path
import json

import pandas as pd
import plotly.graph_objects as go
from plotly.colors import sample_colorscale
import streamlit as st

from src.styles import (
    INDICATOR_THEME,
    PALETTE,
    card_title,
    esc,
    kpi_card,
    kpi_grid,
    page_header,
    render_html,
    show_district_table,
    style_chart,
)


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed"
GEOJSON_PATH = ROOT / "geoBoundaries-RWA-ADM2.geojson"
FEATURE_KEY = "properties.shapeName"

# Same indicators and wording as before, with UI-only extras.
INDICATORS = {
    theme["short"]: {
        "column": column,
        "title": theme["label"],
        "national_label": theme["national"],
        "accent": theme["accent"],
        "text_accent": theme["text_accent"],
        "scale": theme["scale"],
    }
    for column, theme in INDICATOR_THEME.items()
}
INDICATORS["Bank account"]["description"] = "Percentage of respondents who own a bank account."
INDICATORS["Bank account"]["interpretation"] = "Higher values indicate greater reported bank-account ownership."
INDICATORS["Mobile money"]["description"] = "Percentage classified as registered mobile-money users."
INDICATORS["Mobile money"]["interpretation"] = (
    "Registration does not necessarily mean the person currently uses mobile money."
)
INDICATORS["Borrowing"]["description"] = "Percentage who reported borrowing in the past 12 months."
INDICATORS["Borrowing"]["interpretation"] = (
    "Measures recent borrowing activity, not all access to formal credit."
)
INDICATORS["Doesn't save"]["description"] = "Percentage classified as not saving."
INDICATORS["Doesn't save"]["interpretation"] = (
    "A financial-vulnerability signal, not a direct measure of access to savings services."
)
INDICATORS["Emergency funds"][
    "description"
] = "Percentage of respondents who report setting aside emergency or rainy-day funds."
INDICATORS["Emergency funds"]["interpretation"] = (
    "A financial-resilience signal. It does not measure the amount saved "
    "or whether funds would cover a major emergency."
)

INDICATORS["Group saving"]["description"] = (
    "Percentage of respondents who report saving with a group, such as "
    "a cooperative, VSLA, tontine, or ikibina."
)
INDICATORS["Group saving"]["interpretation"] = (
    "Measures participation in group-based saving, not the adequacy "
    "of savings or overall financial inclusion."
)


_ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services"
BASEMAPS = {
    "Light": {"style": "carto-positron", "dark": False},
    "Dark": {"style": "carto-darkmatter", "dark": True},
    "Streets": {"style": "open-street-map", "dark": False},
    "Satellite": {
        "style": "white-bg",
        "dark": True,
        "tiles": f"{_ESRI}/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}",
    },
    "Terrain": {
        "style": "white-bg",
        "dark": False,
        "tiles": f"{_ESRI}/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}",
    },
}
PALETTE_CHOICES = ["Indicator colours", "Viridis", "Plasma", "Cividis", "Turbo"]
SPOTLIGHTS = ["Off", "Top 5", "Bottom 5", "Both"]


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
def _largest_ring(geometry):
    if geometry["type"] == "Polygon":
        rings = [geometry["coordinates"][0]]
    else:
        rings = [polygon[0] for polygon in geometry["coordinates"]]
    return max(rings, key=len)


def _geo_summary(geojson):
    centers, lons, lats = {}, [], []
    for feature in geojson["features"]:
        ring = _largest_ring(feature["geometry"])
        name = feature["properties"].get("shapeName")
        centers[name] = (
            sum(p[1] for p in ring) / len(ring),
            sum(p[0] for p in ring) / len(ring),
        )
        lons += [p[0] for p in ring]
        lats += [p[1] for p in ring]
    center = ((min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2)
    return centers, center


@st.cache_data
def load_district_data():
    district = pd.read_csv(DATA_DIR / "district_financial_inclusion.csv")
    national = pd.read_csv(DATA_DIR / "national_financial_inclusion.csv")

    with GEOJSON_PATH.open(encoding="utf-8") as file:
        geojson = json.load(file)

    district["District"] = district["District"].astype(str).str.strip()
    centers, center = _geo_summary(geojson)
    return district, national, geojson, centers, center


# --------------------------------------------------------------------------
# Map
# --------------------------------------------------------------------------
def _to_rgb(color):
    color = color.strip()
    if color.startswith("#"):
        color = color.lstrip("#")
        return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
    values = color[color.index("(") + 1:color.index(")")].split(",")
    return tuple(float(v) for v in values[:3])


def _trace_classes():
    if hasattr(go, "Choroplethmap"):
        return go.Choroplethmap, go.Scattermap, "map"
    return go.Choroplethmapbox, go.Scattermapbox, "mapbox"


def _outline_layer(geojson, names, color, width, opacity=1.0):
    wanted = set(names)
    collection = {
        "type": "FeatureCollection",
        "features": [
            f for f in geojson["features"]
            if f["properties"].get("shapeName") in wanted
        ],
    }
    return dict(
        sourcetype="geojson",
        source=collection,
        type="line",
        color=color,
        line=dict(width=width),
        opacity=opacity,
    )


def build_map(df, geojson, centers, center, cfg, metric, national_est,
              selected, short, settings):
    Choropleth, Labels, key = _trace_classes()
    base = BASEMAPS[settings["basemap"]]
    dark = base["dark"]

    scale = (
        cfg["scale"] if settings["palette"] == "Indicator colours"
        else settings["palette"]
    )
    lo, hi = float(df[metric].min()), float(df[metric].max())

    customdata = df[["Valid respondents", "rank", "diff"]].to_numpy()
    n = len(df)

    fig = go.Figure(
        Choropleth(
            geojson=geojson,
            featureidkey=FEATURE_KEY,
            locations=df["District"],
            z=df[metric],
            zmin=lo,
            zmax=hi,
            colorscale=scale,
            marker=dict(
                opacity=settings["opacity"],
                line=dict(color="#FFFFFF", width=0.9),
            ),
            selected=dict(marker=dict(opacity=settings["opacity"])),
            unselected=dict(marker=dict(opacity=settings["opacity"])),
            customdata=customdata,
            hovertemplate=(
                "<b>%{location}</b><br>"
                + short
                + ": <b>%{z:.1f}%</b><br>"
                + f"Rank %{{customdata[1]:.0f}} of {n} · "
                + "%{customdata[2]:+.1f} pp vs national<br>"
                + "%{customdata[0]:,.0f} respondents<extra></extra>"
            ),
            colorbar=dict(
                title=dict(text=short, side="top", font=dict(size=11)),
                orientation="h",
                x=0.02, y=0.04, xanchor="left", yanchor="bottom",
                len=0.34, thickness=10, nticks=4,
                ticksuffix="%", outlinewidth=0,
                bgcolor="rgba(14,42,53,.78)" if dark else "rgba(255,255,255,.88)",
                tickfont=dict(size=11, color="#FFFFFF" if dark else PALETTE["ink"]),
                xpad=12, ypad=10,
            ),
        )
    )

    if settings["labels"]:
        span = max(hi - lo, 1e-9)
        try:
            fills = sample_colorscale(scale, [(v - lo) / span for v in df[metric]])
        except Exception:
            fills = ["rgb(128,128,128)"] * len(df)
        base_bg = 30 if dark else 240
        groups = {"#FFFFFF": [], PALETTE["ink"]: []}
        for district_name, fill in zip(df["District"], fills):
            if district_name not in centers:
                continue
            r, g, b = _to_rgb(fill)
            a = settings["opacity"]
            lum = (0.2126 * (a * r + (1 - a) * base_bg)
                   + 0.7152 * (a * g + (1 - a) * base_bg)
                   + 0.0722 * (a * b + (1 - a) * base_bg)) / 255
            groups["#FFFFFF" if lum < 0.52 else PALETTE["ink"]].append(district_name)
        for color, members in groups.items():
            if not members:
                continue
            fig.add_trace(
                Labels(
                    lat=[centers[d][0] for d in members],
                    lon=[centers[d][1] for d in members],
                    text=members,
                    mode="text",
                    textfont=dict(size=11, color=color),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )

    layers = []
    if base.get("tiles"):
        layers.append(
            dict(
                below="traces",
                sourcetype="raster",
                source=[base["tiles"]],
                sourceattribution="Imagery © Esri",
            )
        )

    ranked = df.sort_values(metric, ascending=False)["District"].tolist()
    spot = settings["spotlight"]
    if spot in ("Top 5", "Both"):
        layers.append(_outline_layer(geojson, ranked[:5], "#FFFFFF" if dark else PALETTE["ink"], 2.4))
    if spot in ("Bottom 5", "Both"):
        layers.append(_outline_layer(geojson, ranked[-5:], PALETTE["coral"], 2.4))

    layers.append(_outline_layer(geojson, [selected], PALETTE["ink"], 7, 0.55))
    layers.append(_outline_layer(geojson, [selected], PALETTE["sun"], 3.4))

    fig.update_layout(
        **{
            key: dict(
                style=base["style"],
                center=dict(lat=center[0], lon=center[1]),
                zoom=settings["zoom"],
                pitch=settings["tilt"],
                bearing=settings["rotation"],
                layers=layers,
            )
        }
    )
    fig.update_layout(
        height=700,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Plus Jakarta Sans, Arial, sans-serif", color=PALETTE["ink"]),
        hoverlabel=dict(
            bgcolor=PALETTE["ink"], bordercolor=PALETTE["ink"],
            font=dict(family="Plus Jakarta Sans, Arial, sans-serif", color="#FFFFFF", size=12.5),
        ),
        uirevision=f"{settings['basemap']}-{settings['tilt']}-{settings['rotation']}",
        dragmode="pan",
    )
    return fig


# --------------------------------------------------------------------------
# Small UI pieces
# --------------------------------------------------------------------------
def _meter_pos(value, lo, hi):
    if hi <= lo:
        return 50.0
    return max(3.0, min(97.0, (value - lo) / (hi - lo) * 100))


def _inspector_html(row, cfg, metric, national_est, lo, hi, n):
    est = float(row[metric])
    diff = est - national_est
    arrow = "▲" if diff >= 0 else "▼"
    return f"""
    <div style="--accent:{cfg['accent']};--accent-text:{cfg['text_accent']}">
      <div class="insp-top">
        <div class="insp-name">{esc(row['District'])}</div>
        <div class="insp-rank">#{int(row['rank'])} of {n}</div>
      </div>
      <div class="insp-value">{est:.1f}<span>%</span></div>
      <div class="insp-sub">{esc(cfg['title'])}</div>
      <div class="meter">
        <div class="meter-track"></div>
        <div class="meter-mark" style="left:{_meter_pos(national_est, lo, hi):.1f}%">National</div>
        <div class="meter-dot" style="left:{_meter_pos(est, lo, hi):.1f}%"></div>
      </div>
      <div class="meter-ends"><span>Lowest {lo:.1f}%</span><span>Highest {hi:.1f}%</span></div>
      <div class="insp-grid">
        <div><b>{national_est:.1f}%</b><span>National</span></div>
        <div><b>{arrow} {abs(diff):.1f} pp</b><span>{'Above' if diff >= 0 else 'Below'} national</span></div>
        <div><b>{int(row['Valid respondents']):,}</b><span>Respondents</span></div>
      </div>
    </div>
    """


def _jump_to(name):
    st.session_state["dx_district"] = name


def _clicked_district(event, names):
    points = []
    try:
        points = event.get("selection", {}).get("points", []) if event else []
    except AttributeError:
        points = []
    for point in points:
        if point.get("curve_number", 0) != 0:
            continue
        name = point.get("location")
        if name in names:
            return name
    return None


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------
def render_district_explorer():
    try:
        district, national, geojson, centers, center = load_district_data()
    except (FileNotFoundError, ValueError, KeyError) as error:
        st.error(
            "The district data or boundary file could not be loaded. "
            "Check the files in data/processed and the project root."
        )
        st.caption(str(error))
        return

    names = sorted(district["District"].unique())
    st.session_state.setdefault("dx_district", names[0])
    pending = st.session_state.pop("_dx_pending", None)
    if pending in names:
        st.session_state["dx_district"] = pending
    if st.session_state["dx_district"] not in names:
        st.session_state["dx_district"] = names[0]

    # Widget values are already in session_state before the widgets render,
    # so the hero can reflect the current selection while controls sit below it.
    indicator_name = st.session_state.get("dx_indicator") or list(INDICATORS.keys())[0]
    cfg = INDICATORS[indicator_name]
    metric = cfg["column"]
    selected_district = st.session_state["dx_district"]

    nat_hit = national.loc[
        national["Indicator"].eq(cfg["national_label"]), "Estimate (%)"
    ]
    if nat_hit.empty:
        st.error(f"National estimate missing for {indicator_name}.")
        return
    national_est = float(nat_hit.iloc[0])

    df = district.reset_index(drop=True).copy()
    df["rank"] = df[metric].rank(ascending=False, method="min").astype(int)
    df["diff"] = df[metric] - national_est
    n = len(df)
    lo, hi = float(df[metric].min()), float(df[metric].max())
    sel = df.loc[df["District"].eq(selected_district)].iloc[0]
    highest = df.loc[df[metric].idxmax()]
    lowest = df.loc[df[metric].idxmin()]
    est = float(sel[metric])
    diff = est - national_est

    page_header(
        "District explorer",
        f"How {cfg['title'].lower()} varies across Rwanda's {n} districts. "
        "Click any district on the map to inspect it.",
        pill="FinScope Rwanda 2024",
        size="tall",
        below_html=kpi_grid(
            [
                kpi_card("Selected district", f"{est:.1f}", "%", est, cfg["accent"],
                         f"<b>{esc(selected_district)}</b>"),
                kpi_card("National estimate", f"{national_est:.1f}", "%", national_est,
                         PALETTE["ink2"], "Weighted national level"),
                kpi_card("Difference from national", f"{diff:+.1f}", " pp",
                         abs(diff) / max(hi - lo, 1e-9) * 100, PALETTE["sun"],
                         "Above national" if diff >= 0 else "Below national"),
                kpi_card("Rank among districts", f"#{int(sel['rank'])}", f" of {n}",
                         (n - int(sel["rank"]) + 1) / n * 100, "#5FB8AB",
                         f"Highest <b>{esc(highest['District'])}</b> · "
                         f"Lowest <b>{esc(lowest['District'])}</b>"),
            ]
        ),
    )

    st.markdown("")

    # ---- Controls -------------------------------------------------------
    with st.container(key="card_controls"):
        c_ind, c_dist, c_set = st.columns(
            [2.8, 1.3, 0.8], gap="medium", vertical_alignment="bottom"
        )
        with c_ind:
            st.segmented_control(
                "Indicator",
                list(INDICATORS.keys()),
                default=list(INDICATORS.keys())[0],
                key="dx_indicator",
            )
        with c_dist:
            st.selectbox(
                "District", names, key="dx_district"
            )
        with c_set:
            with st.popover(
                "Map settings",
                icon=":material/tune:",
                use_container_width=True,
            ):
                basemap = st.selectbox("Basemap", list(BASEMAPS), key="dx_basemap")
                palette = st.selectbox("Colours", PALETTE_CHOICES, key="dx_palette")
                opacity = st.slider("Fill opacity", 0.3, 1.0, 0.85, 0.05, key="dx_opacity")
                spotlight = st.selectbox("Outline extremes", SPOTLIGHTS, key="dx_spot")
                labels = st.toggle("Show district names", value=False, key="dx_labels")
                tilt = st.slider("Tilt", 0, 60, 0, key="dx_tilt")
                rotation = st.slider("Rotation", -90, 90, 0, key="dx_rot")

    settings = dict(
        basemap=basemap, palette=palette, opacity=opacity, spotlight=spotlight,
        labels=labels, tilt=tilt, rotation=rotation, zoom=7.3,
    )

    st.markdown("")

    # ---- Hero map + inspector --------------------------------------------
    map_col, insp_col = st.columns([2.85, 1], gap="medium")

    with map_col:
        with st.container(key="card_map"):
            legend = ""
            if spotlight in ("Top 5", "Both"):
                top_color = "#FFFFFF" if BASEMAPS[basemap]["dark"] else PALETTE["ink"]
                legend += (
                    f'<span class="chip"><i style="border-color:{top_color};'
                    f'background:{"#0E2A35" if top_color == "#FFFFFF" else "#fff"}"></i>Highest 5</span>'
                )
            if spotlight in ("Bottom 5", "Both"):
                legend += (
                    f'<span class="chip"><i style="border-color:{PALETTE["coral"]}"></i>Lowest 5</span>'
                )
            legend += (
                f'<span class="chip"><i style="border-color:{PALETTE["sun"]}"></i>Selected</span>'
            )
            render_html(
                f"""
                <div class="map-strip">
                  <div>
                    <div class="ct">{esc(cfg['title'])}</div>
                    <div class="cs">Click a district to inspect it · scroll to zoom · drag to pan</div>
                  </div>
                  <div class="chips">{legend}</div>
                </div>
                """
            )

            fig = build_map(
                df, geojson, centers, center, cfg, metric, national_est,
                selected_district, indicator_name, settings,
            )
            event = st.plotly_chart(
                fig,
                use_container_width=True,
                key="dx_map",
                on_select="rerun",
                selection_mode="points",
                config={
                    "scrollZoom": True,
                    "displaylogo": False,
                    "modeBarButtonsToRemove": ["select2d", "lasso2d"],
                },
            )

    # Map click -> selection (applied on the next run, before widgets render)
    clicked = _clicked_district(event, names)
    if clicked and clicked != st.session_state.get("_dx_last_click"):
        st.session_state["_dx_last_click"] = clicked
        if clicked != selected_district:
            st.session_state["_dx_pending"] = clicked
            st.rerun()

    with insp_col:
        with st.container(key="card_inspector"):
            render_html(_inspector_html(sel, cfg, metric, national_est, lo, hi, n))
            st.button(
                f"Highest: {highest['District']} · {highest[metric]:.1f}%",
                key="dx_go_high",
                on_click=_jump_to,
                args=(highest["District"],),
                use_container_width=True,
                icon=":material/arrow_upward:",
            )
            st.button(
                f"Lowest: {lowest['District']} · {lowest[metric]:.1f}%",
                key="dx_go_low",
                on_click=_jump_to,
                args=(lowest["District"],),
                use_container_width=True,
                icon=":material/arrow_downward:",
            )
            render_html(
                f"""
                <div class="insp-note"><b>{esc(cfg['description'])}</b><br>
                {esc(cfg['interpretation'])}<br>
                The gap between extremes is {hi - lo:.1f} pp. It is a
                description, not a causal explanation.</div>
                """
            )

    st.markdown("")

    # ---- Ranking + profile + distribution --------------------------------
    rank_col, side_col = st.columns([1.45, 1], gap="medium")

    with rank_col:
        with st.container(key="card_ranking"):
            card_title(
                "All districts, ranked",
                "The highlighted bar is your selected district; the dotted "
                "line is the national estimate.",
            )
            ordered = df.sort_values(metric, ascending=True)
            bar_colors = [
                PALETTE["sun"] if d == selected_district else cfg["accent"]
                for d in ordered["District"]
            ]
            rank_fig = go.Figure(
                go.Bar(
                    x=ordered[metric],
                    y=ordered["District"],
                    orientation="h",
                    marker=dict(color=bar_colors),
                    text=ordered[metric],
                    texttemplate="%{text:.1f}%",
                    textposition="outside",
                    cliponaxis=False,
                    textfont=dict(size=11, color=PALETTE["ink"]),
                    customdata=ordered[["Valid respondents"]],
                    hovertemplate=(
                        "%{y}<br>" + cfg["title"] + ": %{x:.2f}%<br>"
                        "%{customdata[0]:,.0f} respondents<extra></extra>"
                    ),
                )
            )
            rank_fig.add_vline(
                x=national_est, line_dash="dot", line_color=PALETTE["ink"], line_width=1.5
            )
            rank_fig.update_layout(bargap=0.32)
            rank_fig.update_xaxes(
                title=None, ticksuffix="%",
                range=[0, min(100, hi + 9)],
                gridcolor=PALETTE["grid"], zeroline=False,
            )
            rank_fig.update_yaxes(title=None, showgrid=False, tickfont=dict(size=11))
            st.plotly_chart(
                style_chart(rank_fig, 720, margin=dict(l=4, r=24, t=10, b=4)),
                use_container_width=True,
                key="dx_ranking",
                config={"displayModeBar": False},
            )

    with side_col:
        with st.container(key="card_profile"):
            card_title(
                f"{selected_district} across indicators",
                "The selected district against the national estimate.",
            )
            nat_map = dict(zip(national["Indicator"], national["Estimate (%)"]))
            shorts, d_vals, n_vals = [], [], []
            for column, theme in INDICATOR_THEME.items():
                if column in df.columns:
                    shorts.append(theme["short"])
                    d_vals.append(float(sel[column]))
                    n_vals.append(float(nat_map.get(theme["national"], float("nan"))))
            prof = go.Figure()
            prof.add_bar(
                y=shorts, x=d_vals, orientation="h", name=selected_district,
                marker_color=PALETTE["sun"],
                text=d_vals, texttemplate="%{text:.1f}%", textposition="outside",
                cliponaxis=False,
            )
            prof.add_bar(
                y=shorts, x=n_vals, orientation="h", name="National",
                marker_color=PALETTE["ink2"],
                text=n_vals, texttemplate="%{text:.1f}%", textposition="outside",
                cliponaxis=False,
            )
            prof.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
            prof.update_xaxes(
                title=None, ticksuffix="%", range=[0, 100],
                gridcolor=PALETTE["grid"], zeroline=False,
            )
            prof.update_yaxes(title=None, autorange="reversed", showgrid=False)
            st.plotly_chart(
                style_chart(prof, 330, margin=dict(l=4, r=26, t=10, b=4)),
                use_container_width=True,
                key="dx_profile",
                config={"displayModeBar": False},
            )

        st.markdown("")

        with st.container(key="card_distribution"):
            card_title(
                "Where districts cluster",
                f"How the 30 districts spread on {cfg['title'].lower()}.",
            )
            dist = go.Figure(
                go.Histogram(
                    x=df[metric], nbinsx=8,
                    marker=dict(color=cfg["accent"], opacity=0.55,
                                line=dict(color="#FFFFFF", width=1.5)),
                    hovertemplate="%{x}%: %{y} districts<extra></extra>",
                    showlegend=False,
                )
            )
            dist.add_vline(x=float(sel[metric]), line_color=PALETTE["sun"], line_width=4)
            dist.add_vline(x=national_est, line_color=PALETTE["ink"], line_width=1.8, line_dash="dot")
            dist.add_trace(go.Scatter(
                x=[None], y=[None], mode="lines", name=selected_district,
                line=dict(color=PALETTE["sun"], width=4)))
            dist.add_trace(go.Scatter(
                x=[None], y=[None], mode="lines", name="National",
                line=dict(color=PALETTE["ink"], width=2, dash="dot")))
            dist.update_layout(bargap=0.06)
            dist.update_xaxes(title=None, ticksuffix="%", showgrid=False, zeroline=False)
            dist.update_yaxes(title="Districts", dtick=2, gridcolor=PALETTE["grid"], zeroline=False)
            st.plotly_chart(
                style_chart(dist, 250),
                use_container_width=True,
                key="dx_distribution",
                config={"displayModeBar": False},
            )

    st.markdown("")

    # ---- Table ------------------------------------------------------------
    with st.container(key="card_table"):
        card_title(
            "District data",
            "All four indicators for every district, sorted by the indicator above. "
            "Use the search icon in the table to find a district.",
        )
        show_district_table(
            df,
            sort_by=metric,
            key="district_explorer_download",
            file_name="rwanda_district_explorer.csv",
            height=440,
        )

    render_html(
        '<div class="src-note">Source: FinScope Rwanda 2024. Estimates are '
        "weighted survey results, not live measurements. Differences alone "
        "do not establish statistical significance or explain their causes.</div>"
    )
