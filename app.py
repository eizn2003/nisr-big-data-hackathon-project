import streamlit as st

from src.auth import render_access_gate
from src.styles import (
    app_footer,
    apply_global_styles,
    coming_soon,
    sidebar_brand,
    sidebar_dataset_card,
    sidebar_user,
    render_html,
)


st.set_page_config(
    page_title="Rwanda Financial Inclusion Gap Explorer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_global_styles()

if not render_access_gate():
    st.stop()


NAV = {
    "National overview": ":material/dashboard:",
    "District explorer": ":material/map:",
    "Population groups": ":material/groups:",
    "Priority explorer": ":material/flag:",
    "Methodology & sources": ":material/menu_book:",
}

with st.sidebar:
    sidebar_brand()
    render_html('<div class="sb-section">Explore</div>')

    selected_page = st.radio(
        "Navigate",
        list(NAV.keys()),
        format_func=lambda page: f"{NAV[page]}  {page}",
        label_visibility="collapsed",
        key="main_nav",
    )

    sidebar_dataset_card()

    st.divider()

    user_email = st.user.get("email", "")
    if user_email:
        sidebar_user(user_email)

    st.button(
        "Sign out",
        on_click=st.logout,
        use_container_width=True,
        icon=":material/logout:",
    )


if selected_page == "National overview":
    from src.pages.national_overview import render_national_overview

    render_national_overview()

elif selected_page == "District explorer":
    from src.pages.district_explorer import render_district_explorer

    render_district_explorer()

elif selected_page == "Population groups":
    from src.pages.population_groups import render_population_groups

    render_population_groups()

elif selected_page == "Priority explorer":
    from src.pages.priority_explorer import render_priority_explorer

    render_priority_explorer()

elif selected_page == "Methodology & sources":
    from src.pages.methodology import render_methodology

    render_methodology()

app_footer()