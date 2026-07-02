"""Дизайн-система дашборда энергоаудита ППД.

Единый CSS + готовые HTML-компоненты (hero-хедер, бейджи, секции, карточки).
Цель — современный, читаемый, корпоративный вид без сторонних зависимостей.
"""

from __future__ import annotations

import streamlit as st

# Палитра (используется и в Plotly-графиках для единства стиля).
PALETTE = {
    "primary": "#1f4e79", "accent": "#2f80ed", "ok": "#2e9e6b",
    "warn": "#e0a106", "bad": "#d9534f", "ink": "#16283a", "muted": "#5b6b7b",
    "bg": "#eef3f9", "card": "#ffffff", "line": "#e2ebf4",
    "water": "#2f80ed", "water_dark": "#1f4e79", "throttle": "#e0a106",
}

_CSS = """
<style>
:root{
  --pri:#1f4e79; --acc:#2f80ed; --ok:#2e9e6b; --warn:#e0a106; --bad:#d9534f;
  --bg:#eef3f9; --card:#ffffff; --line:#e2ebf4; --ink:#16283a; --muted:#5b6b7b;
}
.stApp{ background:linear-gradient(180deg,#eaf1f9 0%, #eef3f9 240px, #eef3f9 100%); }
#MainMenu, header[data-testid="stHeader"], footer{ visibility:hidden; height:0; }
.block-container{ padding-top:1.0rem; padding-bottom:2.4rem; max-width:1360px; }

/* ── Hero ── */
.pp-hero{
  background:linear-gradient(120deg,#1f4e79 0%, #2f6db0 55%, #3a86d6 100%);
  color:#fff; border-radius:18px; padding:20px 26px; margin-bottom:18px;
  box-shadow:0 8px 24px rgba(31,78,121,.22);
}
.pp-hero-title{ font-size:1.7rem; font-weight:800; letter-spacing:.2px; }
.pp-hero-sub{ font-size:.95rem; opacity:.92; margin:2px 0 12px; }
.pp-badges{ display:flex; gap:8px; flex-wrap:wrap; }
.pp-badge{
  display:inline-block; padding:4px 12px; border-radius:999px; font-size:.78rem;
  font-weight:700; background:rgba(255,255,255,.18); color:#fff; border:1px solid rgba(255,255,255,.35);
}
.pp-badge.ok{ background:rgba(46,158,107,.95); border-color:transparent; }
.pp-badge.warn{ background:rgba(224,161,6,.95); border-color:transparent; }
.pp-badge.bad{ background:rgba(217,83,79,.95); border-color:transparent; }

/* ── KPI (st.metric → карточки) ── */
div[data-testid="stMetric"]{
  background:var(--card); border:1px solid var(--line); border-left:4px solid var(--acc);
  border-radius:14px; padding:14px 18px 12px; box-shadow:0 2px 8px rgba(20,40,60,.05);
}
div[data-testid="stMetricValue"]{ font-size:1.85rem; font-weight:800; color:var(--ink); line-height:1.1; }
div[data-testid="stMetricLabel"] p{ font-size:.8rem; color:var(--muted); font-weight:700;
  text-transform:uppercase; letter-spacing:.3px; }
div[data-testid="stMetricDelta"]{ font-weight:700; }

/* ── Заголовки / секции ── */
h1,h2,h3{ color:var(--pri); font-weight:800; }
h2,h3{ border-left:4px solid var(--acc); padding-left:10px; margin-top:.2rem; }
.stCaption, .st-emotion-cache p small{ color:var(--muted); }

/* ── Вкладки ── */
div[data-baseweb="tab-list"]{ gap:3px; background:#e3ecf7; padding:5px; border-radius:14px;
  border:1px solid var(--line); }
button[data-baseweb="tab"]{ font-size:.92rem; font-weight:700; color:var(--muted);
  border-radius:10px; padding:7px 13px; }
button[data-baseweb="tab"][aria-selected="true"]{ background:var(--card); color:var(--pri);
  box-shadow:0 1px 4px rgba(20,40,60,.10); }

/* ── Контейнеры с рамкой (st.container(border=True)) ── */
div[data-testid="stVerticalBlockBorderWrapper"]{ border-radius:14px; }

/* ── Сайдбар ── */
section[data-testid="stSidebar"]{ background:#e7eef8; border-right:1px solid var(--line); }
section[data-testid="stSidebar"] .block-container{ padding-top:1.4rem; }

/* ── Таблицы ── */
.stDataFrame{ border:1px solid var(--line); border-radius:12px; overflow:hidden; }

/* ── Инфо-плашки ── */
.pp-note{ background:#f3f8ff; border:1px solid #d7e6fb; border-left:4px solid var(--acc);
  border-radius:10px; padding:10px 14px; color:var(--ink); font-size:.9rem; }
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def _badges_html(badges) -> str:
    return "".join(f"<span class='pp-badge {tone}'>{txt}</span>" for txt, tone in badges)


def hero(title: str, subtitle: str, badges=()) -> None:
    """Верхний баннер: название объекта/агрегата, подзаголовок, бейджи-статусы."""
    st.markdown(
        f"<div class='pp-hero'><div class='pp-hero-title'>{title}</div>"
        f"<div class='pp-hero-sub'>{subtitle}</div>"
        f"<div class='pp-badges'>{_badges_html(badges)}</div></div>",
        unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f"<div class='pp-note'>{text}</div>", unsafe_allow_html=True)
