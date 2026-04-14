"""
streamlit_app.py — Animated Streamlit UI with emerald/amber theme.

Tabs: Briefing · GitHub Trends · Raw Sources · Timeline
Sidebar: topic history, sample topics, settings
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Page config (MUST be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="CI & Market Research System",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Animated dark theme — emerald + amber + violet ────────────────────────────
_CSS = """
<style>
/* ── Animated gradient background ──────────────────────────────────────── */
@keyframes bgShift {
    0%   { background-position: 0% 50%; }
    25%  { background-position: 50% 100%; }
    50%  { background-position: 100% 50%; }
    75%  { background-position: 50% 0%; }
    100% { background-position: 0% 50%; }
}

@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(24px); }
    to   { opacity: 1; transform: translateY(0); }
}

@keyframes fadeIn {
    from { opacity: 0; }
    to   { opacity: 1; }
}

@keyframes slideInLeft {
    from { opacity: 0; transform: translateX(-30px); }
    to   { opacity: 1; transform: translateX(0); }
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50%      { opacity: 0.6; }
}

@keyframes shimmer {
    0%   { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}

@keyframes borderGlow {
    0%, 100% { border-color: rgba(52, 211, 153, 0.2); }
    50%      { border-color: rgba(52, 211, 153, 0.5); }
}

.stApp {
    background: linear-gradient(-45deg, #0a0f0d, #0d1117, #111318, #0f1610, #0d1117);
    background-size: 400% 400%;
    animation: bgShift 25s ease infinite;
    color: #d1d5db;
}

/* ── Sidebar ────────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: rgba(10, 15, 13, 0.92) !important;
    border-right: 1px solid rgba(52, 211, 153, 0.15);
    backdrop-filter: blur(16px);
}

section[data-testid="stSidebar"] .stButton > button {
    background: rgba(52, 211, 153, 0.08) !important;
    border: 1px solid rgba(52, 211, 153, 0.2) !important;
    color: #a7f3d0 !important;
    transition: all 0.3s ease;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(52, 211, 153, 0.18) !important;
    border-color: rgba(52, 211, 153, 0.4) !important;
    transform: translateX(4px);
}

/* ── Cards with animation ───────────────────────────────────────────────── */
.ci-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(52, 211, 153, 0.12);
    border-radius: 14px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.8rem;
    backdrop-filter: blur(8px);
    transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
    animation: fadeInUp 0.5s ease-out both;
}
.ci-card:hover {
    border-color: rgba(52, 211, 153, 0.4);
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(52, 211, 153, 0.08);
}

.ci-card-threat {
    border-color: rgba(251, 146, 60, 0.25);
}
.ci-card-threat:hover {
    border-color: rgba(251, 146, 60, 0.5);
    box-shadow: 0 8px 32px rgba(251, 146, 60, 0.08);
}

.ci-card-opp {
    border-color: rgba(52, 211, 153, 0.25);
}
.ci-card-opp:hover {
    border-color: rgba(52, 211, 153, 0.5);
    box-shadow: 0 8px 32px rgba(52, 211, 153, 0.08);
}

/* ── Metric chips ───────────────────────────────────────────────────────── */
.metric-chip {
    display: inline-block;
    background: rgba(52, 211, 153, 0.08);
    border: 1px solid rgba(52, 211, 153, 0.25);
    border-radius: 20px;
    padding: 0.2rem 0.7rem;
    font-size: 0.8rem;
    margin: 0.15rem;
    color: #6ee7b7;
    transition: all 0.2s;
}
.metric-chip:hover { background: rgba(52, 211, 153, 0.15); }

/* ── Sentiment badges ───────────────────────────────────────────────────── */
.sentiment-positive { color: #34d399; font-weight: 700; }
.sentiment-neutral  { color: #fbbf24; font-weight: 700; }
.sentiment-negative { color: #fb923c; font-weight: 700; }

/* ── Tag pill ───────────────────────────────────────────────────────────── */
.tag-pill {
    display: inline-block;
    background: rgba(167, 139, 250, 0.1);
    border: 1px solid rgba(167, 139, 250, 0.3);
    border-radius: 12px;
    padding: 0.15rem 0.6rem;
    font-size: 0.75rem;
    margin: 0.1rem;
    color: #c4b5fd;
    transition: all 0.2s;
}
.tag-pill:hover { background: rgba(167, 139, 250, 0.2); }

/* ── Section headers ────────────────────────────────────────────────────── */
.section-header {
    color: #6ee7b7;
    font-size: 1.05rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    border-bottom: 1px solid rgba(52, 211, 153, 0.15);
    padding-bottom: 0.5rem;
    margin: 1.4rem 0 0.8rem;
    animation: slideInLeft 0.4s ease-out both;
}

/* ── Text input — DARK background, bright text ──────────────────────────── */
.stTextInput > div > div > input {
    background: rgba(17, 24, 22, 0.95) !important;
    border: 1px solid rgba(52, 211, 153, 0.3) !important;
    border-radius: 12px !important;
    color: #f0fdf4 !important;
    font-size: 1rem !important;
    padding: 0.7rem 1rem !important;
    caret-color: #34d399 !important;
    transition: border-color 0.3s;
}
.stTextInput > div > div > input:focus {
    border-color: #34d399 !important;
    box-shadow: 0 0 0 2px rgba(52, 211, 153, 0.15) !important;
}
.stTextInput > div > div > input::placeholder {
    color: #6b7280 !important;
}

/* ── Primary button ─────────────────────────────────────────────────────── */
.stButton > button {
    background: linear-gradient(135deg, #059669, #7c3aed) !important;
    border: none !important;
    border-radius: 12px !important;
    color: #fff !important;
    font-weight: 700 !important;
    padding: 0.6rem 1.6rem !important;
    font-size: 0.95rem !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
}
.stButton > button:hover {
    transform: scale(1.04) !important;
    box-shadow: 0 6px 24px rgba(52, 211, 153, 0.2) !important;
}

/* ── Download buttons — visible on dark bg ──────────────────────────────── */
.stDownloadButton > button {
    background: rgba(52, 211, 153, 0.1) !important;
    border: 1px solid rgba(52, 211, 153, 0.35) !important;
    border-radius: 10px !important;
    color: #6ee7b7 !important;
    font-weight: 600 !important;
    padding: 0.5rem 1.2rem !important;
    transition: all 0.3s !important;
}
.stDownloadButton > button:hover {
    background: rgba(52, 211, 153, 0.2) !important;
    border-color: #34d399 !important;
    transform: translateY(-1px) !important;
}

/* ── Tab styling ────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: rgba(10, 15, 13, 0.5);
    border-radius: 12px;
    padding: 4px;
    gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 10px;
    color: #9ca3af;
    font-weight: 600;
    transition: all 0.25s;
}
.stTabs [aria-selected="true"] {
    background: rgba(52, 211, 153, 0.12) !important;
    color: #6ee7b7 !important;
}

/* ── Expander (sources) ─────────────────────────────────────────────────── */
.streamlit-expanderHeader {
    background: rgba(255,255,255,0.03) !important;
    border-radius: 10px !important;
    color: #d1d5db !important;
    font-weight: 600 !important;
    transition: background 0.2s;
}
.streamlit-expanderHeader:hover {
    background: rgba(52, 211, 153, 0.06) !important;
}
.streamlit-expanderContent {
    background: rgba(255,255,255,0.02) !important;
    border-radius: 0 0 10px 10px !important;
}

/* ── Metric cards ───────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: rgba(52, 211, 153, 0.04);
    border: 1px solid rgba(52, 211, 153, 0.12);
    border-radius: 12px;
    padding: 0.8rem;
    animation: fadeInUp 0.5s ease-out both;
}
[data-testid="stMetricLabel"] { color: #9ca3af !important; }
[data-testid="stMetricValue"] { color: #6ee7b7 !important; }

/* ── Progress / spinner ─────────────────────────────────────────────────── */
.stSpinner > div { border-top-color: #34d399 !important; }

/* ── Scrollbar ──────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: rgba(255,255,255,0.02); }
::-webkit-scrollbar-thumb { background: rgba(52, 211, 153, 0.25); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(52, 211, 153, 0.4); }

/* ── Source link cards ──────────────────────────────────────────────────── */
.source-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(167, 139, 250, 0.15);
    border-radius: 12px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.6rem;
    transition: all 0.3s ease;
    animation: fadeInUp 0.4s ease-out both;
}
.source-card:hover {
    border-color: rgba(167, 139, 250, 0.4);
    transform: translateY(-1px);
}
.source-card a {
    color: #a78bfa !important;
    text-decoration: none;
    font-weight: 600;
}
.source-card a:hover { color: #c4b5fd !important; }
.source-card p {
    color: #9ca3af;
    font-size: 0.88rem;
    line-height: 1.6;
    margin-top: 0.4rem;
}

/* ── Timeline dot ───────────────────────────────────────────────────────── */
.tl-dot {
    width: 14px; height: 14px; border-radius: 50%;
    margin-top: 10px;
    animation: pulse 2s infinite;
}

/* ── Shimmer loading placeholder ────────────────────────────────────────── */
.shimmer {
    background: linear-gradient(90deg, rgba(52,211,153,0.05) 25%, rgba(52,211,153,0.12) 50%, rgba(52,211,153,0.05) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 8px;
    height: 20px;
    margin: 8px 0;
}

/* ── Animated border glow on report banner ──────────────────────────────── */
.report-banner {
    display: flex; justify-content: space-between; align-items: center;
    background: rgba(52, 211, 153, 0.04);
    border: 1px solid rgba(52, 211, 153, 0.2);
    border-radius: 14px;
    padding: 0.8rem 1.4rem;
    margin: 1rem 0;
    animation: borderGlow 3s ease-in-out infinite, fadeIn 0.6s ease-out both;
}

/* ── Divider ────────────────────────────────────────────────────────────── */
hr { border-color: rgba(52, 211, 153, 0.1) !important; }
</style>
"""

st.markdown(_CSS, unsafe_allow_html=True)


# ── Lazy imports (after page config) ─────────────────────────────────────────
from data.sample_topics import SAMPLE_TOPICS  # noqa: E402
from orchestrator import ResearchOrchestrator  # noqa: E402
from config import validate_required_keys       # noqa: E402


# ── Session state ─────────────────────────────────────────────────────────────
def _init_state() -> None:
    defaults: dict[str, Any] = {
        "report": None,
        "topic_history": [],
        "is_loading": False,
        "error": None,
        "elapsed": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _sidebar() -> str | None:
    with st.sidebar:
        st.markdown(
            "<div style='animation:fadeIn 0.8s ease-out'>"
            "<h2 style='color:#6ee7b7;margin-bottom:0;font-size:1.5rem'>CI Research</h2>"
            "<p style='color:#6b7280;font-size:0.78rem;margin-top:4px'>"
            "Groq LLaMA 3.3 + Tavily + GitHub</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.divider()

        missing = validate_required_keys()
        if missing:
            st.error(f"Missing keys: {', '.join(missing)}")
        else:
            st.success("API keys configured", icon="✅")

        st.divider()

        st.markdown("<span style='color:#6ee7b7;font-weight:700;font-size:0.9rem'>SAMPLE TOPICS</span>", unsafe_allow_html=True)
        selected = None
        for topic in SAMPLE_TOPICS[:6]:
            if st.button(topic, key=f"sample_{topic}", use_container_width=True):
                selected = topic

        st.divider()

        if st.session_state.topic_history:
            st.markdown("<span style='color:#fbbf24;font-weight:700;font-size:0.9rem'>RECENT</span>", unsafe_allow_html=True)
            for t in reversed(st.session_state.topic_history[-5:]):
                if st.button(f"↩ {t}", key=f"hist_{t}", use_container_width=True):
                    selected = t

        st.divider()
        with st.expander("About this system"):
            st.markdown("""
**5 Agents:**
- Search — Tavily / DuckDuckGo
- Scraper — HTTP + Fetch MCP
- GitHub — REST + MCP
- Analyst — Groq LLaMA 3.3
- Report Writer — JSON + MD

**Memory:** SQLite deduplication
""")
        return selected


# ── Hero header ───────────────────────────────────────────────────────────────

def _hero_header() -> None:
    st.markdown(
        """
        <div style="text-align:center;padding:1.5rem 0 0.5rem;animation:fadeInUp 0.7s ease-out">
          <h1 style="
            background: linear-gradient(135deg, #34d399, #a78bfa, #fbbf24);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.5rem;
            font-weight: 800;
            margin-bottom: 0.3rem;
            letter-spacing: -0.02em;
          ">Multi-Agent CI & Market Research</h1>
          <p style="color:#6b7280;font-size:0.95rem;animation:fadeIn 1.2s ease-out">
            Real-time competitive intelligence — Tavily · GitHub · Groq LLaMA 3.3
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _search_bar() -> str | None:
    col1, col2 = st.columns([5, 1])
    with col1:
        topic = st.text_input(
            label="Research topic",
            placeholder='e.g.  "OpenAI competitors"  or  "HR tech market"',
            label_visibility="collapsed",
            key="topic_input",
        )
    with col2:
        go_clicked = st.button("Research", use_container_width=True, type="primary")

    if go_clicked and topic and topic.strip():
        return topic.strip()
    return None


# ── Tab: Briefing ─────────────────────────────────────────────────────────────

def _tab_briefing(report: dict) -> None:
    eb = report.get("executive_briefing", {})
    actions = report.get("recommended_actions", [])

    sentiment = eb.get("sentiment", "neutral")
    score = eb.get("sentiment_score", 0.0)
    sentiment_cls = f"sentiment-{sentiment}"
    bar_pct = int((score + 1) / 2 * 100)
    bar_color = {"positive": "#34d399", "negative": "#fb923c"}.get(sentiment, "#fbbf24")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trends", len(eb.get("key_trends", [])))
    c2.metric("Threats", len(eb.get("threats", [])))
    c3.metric("Opportunities", len(eb.get("opportunities", [])))
    c4.metric("Sources", len(report.get("sources", [])))

    st.divider()

    # Executive summary
    st.markdown(
        f"""
        <div class="ci-card" style="animation-delay:0.1s">
          <div class="section-header">Executive Summary</div>
          <p style="color:#d1d5db;line-height:1.75;font-size:0.95rem">{eb.get('summary','—')}</p>
          <div style="margin-top:1rem;display:flex;align-items:center;gap:12px">
            <span style="color:#9ca3af">Sentiment:</span>
            <span class="{sentiment_cls}">{sentiment.upper()}</span>
            <span style="color:#6b7280">({score:+.2f})</span>
            <div style="flex:1;background:rgba(255,255,255,0.06);border-radius:6px;height:8px;overflow:hidden">
              <div style="background:{bar_color};width:{bar_pct}%;height:8px;border-radius:6px;transition:width 1s ease"></div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_t, col_th, col_op = st.columns(3)

    with col_t:
        st.markdown('<div class="section-header">Key Trends</div>', unsafe_allow_html=True)
        for i, t in enumerate(eb.get("key_trends", [])):
            st.markdown(
                f"<div class='ci-card' style='padding:0.7rem 1rem;animation-delay:{i*0.1}s'>"
                f"<span style='color:#34d399;margin-right:6px'>▹</span>{t}</div>",
                unsafe_allow_html=True,
            )

    with col_th:
        st.markdown('<div class="section-header">Threats</div>', unsafe_allow_html=True)
        for i, t in enumerate(eb.get("threats", [])):
            st.markdown(
                f"<div class='ci-card ci-card-threat' style='padding:0.7rem 1rem;animation-delay:{i*0.1}s'>"
                f"<span style='color:#fb923c;margin-right:6px'>▸</span>{t}</div>",
                unsafe_allow_html=True,
            )

    with col_op:
        st.markdown('<div class="section-header">Opportunities</div>', unsafe_allow_html=True)
        for i, o in enumerate(eb.get("opportunities", [])):
            st.markdown(
                f"<div class='ci-card ci-card-opp' style='padding:0.7rem 1rem;animation-delay:{i*0.1}s'>"
                f"<span style='color:#34d399;margin-right:6px'>◆</span>{o}</div>",
                unsafe_allow_html=True,
            )

    entities = eb.get("key_entities", [])
    if entities:
        st.markdown('<div class="section-header">Key Entities</div>', unsafe_allow_html=True)
        pills = " ".join(f"<span class='tag-pill'>{e}</span>" for e in entities)
        st.markdown(f"<div style='padding:0.5rem 0;animation:fadeIn 0.8s ease-out'>{pills}</div>", unsafe_allow_html=True)

    if actions:
        st.markdown('<div class="section-header">Recommended Actions</div>', unsafe_allow_html=True)
        for i, a in enumerate(actions, 1):
            st.markdown(
                f"<div class='ci-card' style='padding:0.7rem 1rem;animation-delay:{i*0.08}s'>"
                f"<span style='color:#fbbf24;font-weight:700;margin-right:8px'>{i}.</span>"
                f"<span style='color:#d1d5db'>{a}</span></div>",
                unsafe_allow_html=True,
            )


# ── Tab: GitHub ───────────────────────────────────────────────────────────────

def _tab_github(report: dict) -> None:
    repos = report.get("github_trends", [])
    if not repos:
        st.markdown(
            "<div style='text-align:center;padding:3rem;color:#6b7280;animation:fadeIn 0.6s'>"
            "<div style='font-size:3rem;margin-bottom:0.5rem'>🐙</div>"
            "No GitHub data found for this topic.<br>"
            "<span style='font-size:0.85rem'>Try a more tech-specific query like \"AI agent frameworks\"</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    df = pd.DataFrame(repos)

    # Bar chart
    fig_stars = px.bar(
        df.head(10), x="full_name", y="stars", color="stars",
        color_continuous_scale=["#064e3b", "#059669", "#34d399", "#6ee7b7"],
        title="Top Repos by Stars", text="stars",
        labels={"full_name": "Repository", "stars": "Stars"},
    )
    fig_stars.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
    fig_stars.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#d1d5db", xaxis_tickangle=-35, showlegend=False,
        margin=dict(t=50, b=120),
        xaxis=dict(gridcolor="rgba(255,255,255,0.03)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.03)"),
    )
    st.plotly_chart(fig_stars, use_container_width=True)

    if "language" in df.columns and df["language"].notna().any():
        lang_counts = df["language"].value_counts().reset_index()
        lang_counts.columns = ["language", "count"]
        fig_lang = px.pie(
            lang_counts, names="language", values="count",
            title="Language Distribution",
            color_discrete_sequence=["#34d399", "#a78bfa", "#fbbf24", "#fb923c", "#60a5fa", "#f472b6"],
            hole=0.5,
        )
        fig_lang.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#d1d5db")

        col_pie, col_stats = st.columns([1, 1])
        with col_pie:
            st.plotly_chart(fig_lang, use_container_width=True)
        with col_stats:
            st.markdown('<div class="section-header">Repo Stats</div>', unsafe_allow_html=True)
            total_stars = int(df["stars"].sum())
            avg_issues = int(df["open_issues"].mean()) if "open_issues" in df.columns else 0
            st.metric("Total Stars", f"{total_stars:,}")
            st.metric("Avg Open Issues", avg_issues)
            if "recent_commits" in df.columns and not df["recent_commits"].isna().all():
                most_active = df.loc[df["recent_commits"].idxmax(), "full_name"]
                st.metric("Most Active (30d)", most_active)

    # Repo cards
    st.markdown('<div class="section-header">Repository Details</div>', unsafe_allow_html=True)
    for i, r in enumerate(repos[:10]):
        topics_html = " ".join(f"<span class='tag-pill'>{t}</span>" for t in r.get("topics", [])[:5])
        st.markdown(
            f"""
            <div class="ci-card" style="animation-delay:{i*0.08}s">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
                <div style="flex:1;min-width:200px">
                  <a href="https://github.com/{r['full_name']}" target="_blank"
                     style="color:#6ee7b7;font-weight:700;font-size:1.05rem;text-decoration:none">
                    {r['full_name']}
                  </a>
                  <p style="color:#9ca3af;margin:0.3rem 0 0.5rem;font-size:0.88rem">
                    {r.get('description','')[:140]}
                  </p>
                  <div>{topics_html}</div>
                </div>
                <div style="text-align:right;min-width:130px">
                  <div class="metric-chip">⭐ {r['stars']:,}</div>
                  <div class="metric-chip">🍴 {r.get('forks',0):,}</div>
                  <div class="metric-chip">🔧 {r.get('open_issues',0)}</div>
                  <div style="color:#6b7280;font-size:0.78rem;margin-top:6px">
                    {r.get('language','')} · {r.get('latest_release','N/A')}
                  </div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ── Tab: Sources (links only — no raw dump) ──────────────────────────────────

def _tab_sources(report: dict) -> None:
    sources = report.get("sources", [])
    if not sources:
        st.info("No sources available.")
        return

    st.markdown(
        f"<div style='color:#9ca3af;margin-bottom:1rem;animation:fadeIn 0.5s'>"
        f"<strong style='color:#d1d5db'>{len(sources)}</strong> sources collected</div>",
        unsafe_allow_html=True,
    )

    for i, s in enumerate(sources):
        title = s.get("title", "Untitled")
        url = s.get("url", "")
        summary = s.get("summary", "")[:200]

        st.markdown(
            f"""
            <div class="source-card" style="animation-delay:{i*0.06}s">
              <div style="display:flex;align-items:flex-start;gap:10px">
                <span style="color:#a78bfa;font-weight:700;font-size:0.9rem;margin-top:1px">{i+1}.</span>
                <div>
                  <a href="{url}" target="_blank">{title}</a>
                  {f'<p>{summary}</p>' if summary else ''}
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ── Tab: Timeline ─────────────────────────────────────────────────────────────

def _tab_timeline(report: dict) -> None:
    timeline = report.get("timeline", [])
    meta = report.get("meta", {})

    if not timeline:
        st.info("No timeline events available.")
        return

    st.markdown(
        f"<div style='color:#9ca3af;margin-bottom:1rem;animation:fadeIn 0.5s'>"
        f"<strong style='color:#d1d5db'>{len(timeline)}</strong> events captured</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    colors = ["#34d399", "#a78bfa", "#fbbf24", "#fb923c", "#60a5fa", "#f472b6"]
    for i, event in enumerate(timeline):
        col_dot, col_content = st.columns([0.06, 0.94])
        c = colors[i % len(colors)]
        with col_dot:
            st.markdown(
                f"<div class='tl-dot' style='background:{c};animation-delay:{i*0.15}s'></div>",
                unsafe_allow_html=True,
            )
        with col_content:
            url = event.get("url", "")
            title = event.get("title", url)
            st.markdown(
                f"<div class='ci-card' style='padding:0.6rem 1rem;animation-delay:{i*0.08}s'>"
                f"<a href='{url}' target='_blank' style='color:#6ee7b7;text-decoration:none;font-weight:600'>{title}</a>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.divider()
    st.markdown(
        f"<div style='color:#6b7280;font-size:0.8rem;animation:fadeIn 0.8s'>"
        f"Report generated: {meta.get('generated_at','')[:19]} UTC</div>",
        unsafe_allow_html=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    sidebar_topic = _sidebar()
    _hero_header()

    input_topic = _search_bar()
    topic_to_run = input_topic or sidebar_topic

    if topic_to_run and not st.session_state.is_loading:
        st.session_state.is_loading = True
        st.session_state.error = None

        if topic_to_run not in st.session_state.topic_history:
            st.session_state.topic_history.append(topic_to_run)

        with st.spinner(f"Researching **{topic_to_run}** — this may take 15–30 seconds..."):
            t0 = time.perf_counter()
            try:
                orch = ResearchOrchestrator()
                report = run_async(orch.run(topic_to_run))
                st.session_state.report = report
                st.session_state.elapsed = round(time.perf_counter() - t0, 1)
            except Exception as e:
                st.session_state.error = str(e)
                st.session_state.report = None
            finally:
                st.session_state.is_loading = False

        st.rerun()

    if st.session_state.error:
        st.error(f"Research failed: {st.session_state.error}")

    report = st.session_state.report
    if report:
        meta = report.get("meta", {})
        elapsed = st.session_state.elapsed

        st.markdown(
            f"<div class='report-banner'>"
            f"<span style='color:#6ee7b7;font-weight:700;font-size:1.1rem'>"
            f"📊 {meta.get('topic','')}</span>"
            f"<span style='color:#6b7280;font-size:0.85rem'>"
            f"Generated {meta.get('generated_at','')[:10]}"
            f"{f' · {elapsed}s' if elapsed else ''}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        tab_brief, tab_gh, tab_src, tab_tl = st.tabs(
            ["📋 Briefing", "🐙 GitHub Trends", "📰 Raw Sources", "🕐 Timeline"]
        )

        with tab_brief:
            _tab_briefing(report)
        with tab_gh:
            _tab_github(report)
        with tab_src:
            _tab_sources(report)
        with tab_tl:
            _tab_timeline(report)

        # Downloads
        st.divider()
        col_dl1, col_dl2, col_dl3 = st.columns([1, 1, 4])
        with col_dl1:
            st.download_button(
                "⬇ Download JSON",
                data=json.dumps(report, indent=2, ensure_ascii=False),
                file_name=f"report_{meta.get('topic','')[:20].replace(' ','_')}.json",
                mime="application/json",
            )
        with col_dl2:
            md_path = report.get("_file_paths", {}).get("markdown")
            if md_path:
                from pathlib import Path
                try:
                    md_content = Path(md_path).read_text(encoding="utf-8")
                    st.download_button(
                        "⬇ Download Markdown",
                        data=md_content,
                        file_name=f"report_{meta.get('topic','')[:20].replace(' ','_')}.md",
                        mime="text/markdown",
                    )
                except Exception:
                    pass
    else:
        st.markdown(
            """
            <div style="text-align:center;padding:4rem 1rem;animation:fadeInUp 0.8s ease-out">
              <div style="font-size:4.5rem;margin-bottom:0.5rem;animation:pulse 3s infinite">🔍</div>
              <h3 style="color:#6ee7b7;margin:0.5rem 0;font-weight:700">Enter a topic above to begin</h3>
              <p style="color:#6b7280;font-size:0.9rem">
                Try: "OpenAI competitors" · "AI agent frameworks" · "HR tech market"
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
