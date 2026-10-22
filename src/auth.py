import streamlit as st

from src.styles import HERO_ART, LOGO_SVG, esc, render_html


LOGIN_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"], [data-testid="stExpandSidebarButton"]{display:none !important;}
.block-container{max-width:100% !important; padding:1rem 1.25rem !important;}

.lg-hero{
  position:relative; overflow:hidden; box-sizing:border-box; border-radius:24px;
  min-height:86vh; padding:clamp(28px,4vw,56px); color:#fff;
  display:flex; flex-direction:column; justify-content:space-between; gap:32px;
  background-color:#0E2A35;
  background-image:
    linear-gradient(165deg, rgba(10,31,40,.50) 0%, rgba(10,31,40,.93) 80%),
    url("https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=1800&q=85");
  background-size:cover; background-position:center;
}
.lg-art{position:absolute; left:0; right:0; bottom:0; height:46%; pointer-events:none; opacity:.9;}
.lg-top, .lg-copy, .lg-stats{position:relative; z-index:2;}
.lg-top{display:flex; align-items:center; gap:12px; font-weight:700; font-size:14px; color:#E6F0F2;}
.lg-mark{width:38px; height:38px; border-radius:11px; display:grid; place-items:center; background:linear-gradient(145deg,#1A8A7D,#0F5C63);}
.stApp .lg-copy .lg-h{
  font-family:'Fraunces',Georgia,serif; font-weight:600; color:#fff; margin:0 0 18px; padding:0;
  font-size:clamp(34px,3.8vw,58px); line-height:1.06; letter-spacing:-.03em; max-width:15ch;
}
.stApp .lg-copy .lg-p{color:#D5E3E7; font-size:17px; line-height:1.7; max-width:46ch; margin:0;}
.lg-stats{display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; max-width:560px;}
.lg-stat{
  padding:14px 16px; border-radius:16px; background:rgba(255,255,255,.08);
  border:1px solid rgba(255,255,255,.16); backdrop-filter:blur(10px);
}
.lg-stat b{display:block; font-family:'Fraunces',Georgia,serif; font-size:28px; font-weight:600; color:#fff; line-height:1.1;}
.lg-stat span{font-size:12.5px; color:#C9D9DE;}

.st-key-card_login, .st-key-card_gate{padding:38px 36px 30px !important; border-radius:24px !important;}
.lg-logo{width:52px; height:52px; border-radius:15px; display:grid; place-items:center; margin:0 auto 20px;
  background:linear-gradient(145deg,#1A8A7D,#0F5C63); box-shadow:0 16px 28px -14px rgba(26,138,125,.9);}
.lg-title{font-family:'Fraunces',Georgia,serif; font-size:clamp(28px,2.6vw,36px); font-weight:600; letter-spacing:-.02em;
  color:#0E2A35; text-align:center; line-height:1.15; margin-bottom:12px;}
.lg-text{text-align:center; color:#5C707A; font-size:15px; line-height:1.7; margin-bottom:26px;}
.lg-note{display:flex; justify-content:center; gap:8px; align-items:center; margin-top:20px; padding-top:18px;
  border-top:1px solid #E0E7EA; font-size:12.5px; color:#5C707A; text-align:center; line-height:1.6;}
.gate-ic{width:52px; height:52px; border-radius:15px; display:grid; place-items:center; margin:0 auto 18px; font-size:24px;}
.gate-ic.warn{background:#FFF3D6;} .gate-ic.stop{background:#FCE7E1;}

@media (max-width:768px){
  .lg-hero{min-height:440px; padding:26px;}
  .lg-stats{grid-template-columns:1fr 1fr 1fr;}
}
</style>
"""


def _gate_card(icon, tone, title, text):
    render_html(
        f"""
        <div class="gate-ic {tone}">{icon}</div>
        <div class="lg-title">{esc(title)}</div>
        <div class="lg-text">{esc(text)}</div>
        """
    )


def render_access_gate() -> bool:
    """
    Allow access only to authenticated users whose email is
    explicitly included in the administrator-managed allowlist.
    """

    try:
        auth_config = st.secrets.get("auth", {})
        google_config = auth_config.get("google", {})
        access_config = st.secrets.get("access", {})
    except Exception:
        auth_config = {}
        google_config = {}
        access_config = {}

    # Fail closed: do not display dashboard data until
    # authentication and the approved-user list are configured.
    if not google_config.get("client_id") or not google_config.get(
        "client_secret"
    ):
        st.markdown(LOGIN_CSS, unsafe_allow_html=True)
        _, middle, _ = st.columns([1, 1.1, 1], vertical_alignment="center")
        with middle:
            st.markdown("<div style='height:12vh'></div>", unsafe_allow_html=True)
            with st.container(key="card_gate"):
                _gate_card(
                    "⚙️",
                    "warn",
                    "Sign-in is not set up yet",
                    "Complete the authentication setup, then reload this page "
                    "to open the Rwanda Financial Inclusion Gap Explorer.",
                )
        return False

    if not st.user.is_logged_in:
        st.markdown(LOGIN_CSS, unsafe_allow_html=True)

        left, right = st.columns(
            [1.12, 0.88],
            gap="large",
            vertical_alignment="center",
        )

        with left:
            render_html(
                f"""
                <section class="lg-hero">
                  <div class="lg-art">{HERO_ART}</div>
                  <div class="lg-top"><div class="lg-mark">{LOGO_SVG}</div>
                    Rwanda Financial Inclusion</div>
                  <div class="lg-copy">
                    <h1 class="lg-h">See the gaps. Understand the opportunity.</h1>
                    <p class="lg-p">Explore how access to financial services varies
                    between Rwanda's districts and population groups, backed by
                    national survey evidence.</p>
                  </div>
                  <div class="lg-stats">
                    <div class="lg-stat"><b>30</b><span>districts mapped</span></div>
                    <div class="lg-stat"><b>4</b><span>inclusion indicators</span></div>
                    <div class="lg-stat"><b>2024</b><span>FinScope survey</span></div>
                  </div>
                </section>
                """
            )

        with right:
            _, center, _ = st.columns([0.06, 0.88, 0.06])
            with center:
                with st.container(key="card_login"):
                    render_html(
                        f"""
                        <div class="lg-logo">{LOGO_SVG}</div>
                        <div class="lg-title">Sign in to the Gap Explorer</div>
                        <div class="lg-text">Use your approved Google account to
                        open the dashboard.</div>
                        """
                    )
                    st.button(
                        "Continue with Google",
                        type="primary",
                        on_click=st.login,
                        args=("google",),
                        use_container_width=True,
                        icon=":material/login:",
                    )
                    render_html(
                        """
                        <div class="lg-note">🔒 Restricted access. Approved accounts only.<br>
                        Based on FinScope Rwanda 2024 survey data.</div>
                        """
                    )

        st.stop()

    email = str(st.user.get("email", "")).strip().lower()

    approved_emails = access_config.get("allowed_emails", [])
    if not isinstance(approved_emails, (list, tuple)):
        approved_emails = []

    approved_emails = {
        str(address).strip().lower()
        for address in approved_emails
        if str(address).strip()
    }

    if not email or email not in approved_emails:
        st.markdown(LOGIN_CSS, unsafe_allow_html=True)
        _, middle, _ = st.columns([1, 1.1, 1], vertical_alignment="center")
        with middle:
            st.markdown("<div style='height:12vh'></div>", unsafe_allow_html=True)
            with st.container(key="card_gate"):
                _gate_card(
                    "🚫",
                    "stop",
                    "This account is not approved",
                    "Your account is not approved to access this dashboard. "
                    "Contact the administrator if you believe this is a mistake.",
                )
                st.button(
                    "Sign out",
                    on_click=st.logout,
                    use_container_width=True,
                    icon=":material/logout:",
                )
        return False

    return True