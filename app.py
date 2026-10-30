from importlib import import_module

import streamlit as st

from src.auth import render_access_gate
from src.styles import (
    app_footer,
    apply_global_styles,
    render_html,
    sidebar_brand,
    sidebar_dataset_card,
    sidebar_user,
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
    "Policy alignment": ":material/account_balance:",
    "Methodology & sources": ":material/menu_book:",
}
PAGE_MODULES = {
    "National overview": ("national_overview", "render_national_overview"),
    "District explorer": ("district_explorer", "render_district_explorer"),
    "Population groups": ("population_groups", "render_population_groups"),
    "Priority explorer": ("priority_explorer", "render_priority_explorer"),
    "Policy alignment": ("policy_alignment", "render_policy_alignment"),
    "Methodology & sources": ("methodology", "render_methodology"),
}


def select_page(page):
    st.session_state["selected_page"] = page


selected_page = st.session_state.get("selected_page", "National overview")


def render_selected_page(page):
    module_name, renderer_name = PAGE_MODULES[page]
    from src.pages.nbr_dashboard import current_mode

    page_package = (
        "src.pages.combine-view" if current_mode() == "Combined" else "src.pages"
    )
    module = import_module(f"{page_package}.{module_name}")
    getattr(module, renderer_name)()


with st.sidebar:
    sidebar_brand()
    render_html('<div class="sb-section">Explore</div>')
    from src.pages.nbr_dashboard import render_mode_selector

    render_mode_selector()
    st.divider()

    with st.container(key="sidebar_navigation"):
        for index, (page, icon) in enumerate(NAV.items()):
            st.button(
                page,
                key=f"nav_{index}",
                icon=icon,
                type="primary" if page == selected_page else "secondary",
                on_click=select_page,
                args=(page,),
                use_container_width=True,
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


render_selected_page(selected_page)

app_footer()
