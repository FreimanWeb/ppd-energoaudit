"""Дизайн-система дашборда энергоаудита ППД.

Единый CSS + готовые HTML-компоненты (хедер, бейджи, секции, карточки).
Оформление намеренно строгое: плоские поверхности, волосяные линии, никаких
градиентов, теней и скруглений — так дашборд читается как инженерный документ,
а не как витрина. Цвет используется только там, где несёт смысл: статус и
серии на графиках.
"""

from __future__ import annotations

import streamlit as st


# Палитра. Цвета серий (accent, ok, water_dark, throttle) не меняются: они
# проверены на различимость и используются в графиках Altair/Plotly.
PALETTE = {
    "primary": "#1f2937",
    "accent": "#2f80ed",
    "ok": "#2e9e6b",
    "warn": "#e0a106",
    "bad": "#d9534f",
    "ink": "#111827",
    "muted": "#6b7280",
    "bg": "#ffffff",
    "card": "#ffffff",
    "line": "#e5e7eb",
    "water": "#2f80ed",
    "water_dark": "#1f4e79",
    "throttle": "#e0a106",
}

_CSS = """
<style>
:root{
  --pri:#1f2937; --acc:#2f80ed; --ok:#2e9e6b; --warn:#e0a106; --bad:#d9534f;
  --bg:#ffffff; --card:#ffffff; --line:#e5e7eb; --ink:#111827; --muted:#6b7280;
}
.stApp{ background:var(--bg); }
/* Шапка Streamlit убрана до тонкой полосы, но не скрыта: внутри неё лежит
   кнопка раскрытия свёрнутого сайдбара. Прячем только меню, Deploy и статус. */
#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"],
[data-testid="stToolbarActions"], [data-testid="stAppDeployButton"]{ display:none; }
header[data-testid="stHeader"]{
  background:transparent; box-shadow:none; height:2.6rem; min-height:0;
}
.block-container{ padding-top:.6rem; padding-bottom:2.4rem; max-width:1360px; }

/* Хедер объекта */
.pp-hero{
  border-bottom:1px solid var(--line); padding:0 0 14px; margin:0 0 18px;
}
.pp-hero-title{ font-size:1.35rem; font-weight:600; color:var(--ink); letter-spacing:0; }
.pp-hero-sub{ font-size:.85rem; color:var(--muted); margin:4px 0 10px; }
.pp-badges{ display:flex; gap:6px; flex-wrap:wrap; }
.pp-badge{
  display:inline-block; padding:3px 9px; border-radius:2px; font-size:.75rem;
  font-weight:500; background:#f3f4f6; color:var(--ink);
  border:1px solid #dfe3e8;
}
.pp-badge.ok{ background:#e6f4ec; color:#1c6b48; border-color:#c6e4d4; }
.pp-badge.warn{ background:#fdf3da; color:#7a5600; border-color:#eddcae; }
.pp-badge.bad{ background:#fbe9e8; color:#a4302c; border-color:#eec4c2; }
.pp-provenance{ display:flex; gap:6px; flex-wrap:wrap; margin:0 0 10px; }

/* KPI */
div[data-testid="stMetric"]{
  background:var(--card); border:1px solid var(--line); border-radius:2px;
  padding:12px 14px 10px;
}
div[data-testid="stMetricValue"]{
  font-size:1.5rem; font-weight:600; color:var(--ink); line-height:1.15;
  font-variant-numeric:tabular-nums;
}
div[data-testid="stMetricLabel"] p{ font-size:.72rem; color:var(--muted); font-weight:500;
  text-transform:uppercase; letter-spacing:.4px; }
div[data-testid="stMetricDelta"]{ font-weight:500; }

/* Заголовки */
h1,h2,h3{ color:var(--ink); font-weight:600; letter-spacing:0; }
h1{ font-size:1.5rem; } h2{ font-size:1.2rem; } h3{ font-size:1.02rem; }
h2,h3{ margin-top:.6rem; padding-left:0; border-left:none; }
.stCaption, .st-emotion-cache p small{ color:var(--muted); }

/* Вкладки: подчёркивание вместо плашек */
div[data-baseweb="tab-list"]{ gap:0; background:transparent; padding:0;
  border-radius:0; border-bottom:1px solid var(--line); }
button[data-baseweb="tab"]{ font-size:.88rem; font-weight:500; color:var(--muted);
  border-radius:0; padding:8px 14px; border-bottom:2px solid transparent; }
button[data-baseweb="tab"][aria-selected="true"]{ background:transparent; color:var(--ink);
  border-bottom-color:var(--ink); box-shadow:none; }

/* Контейнеры и таблицы */
div[data-testid="stVerticalBlockBorderWrapper"]{ border-radius:2px; }
.stDataFrame{ border:1px solid var(--line); border-radius:2px; overflow:hidden; }

/* Сайдбар */
section[data-testid="stSidebar"]{ background:#f7f8f9; border-right:1px solid #dfe3e8; }
section[data-testid="stSidebar"] .block-container{ padding-top:1.4rem; }
section[data-testid="stSidebar"] div[data-baseweb="select"] > div,
section[data-testid="stSidebar"] div[data-baseweb="input"]{
  background:#ffffff; border-color:#c8cdd4; border-radius:2px;
}

/* Фильтры: вместо тёмных плашек — светлые теги с контуром */
span[data-baseweb="tag"]{
  background:#ffffff !important; color:var(--ink) !important;
  border:1px solid #c8cdd4; border-radius:2px; font-weight:500;
}
span[data-baseweb="tag"] span[role="presentation"] svg{ fill:#4b5563; }

/* Врезка с пояснением */
.pp-note{ background:#fafafa; border:1px solid var(--line); border-left:2px solid var(--muted);
  border-radius:2px; padding:10px 14px; color:var(--ink); font-size:.86rem; }

</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def _badges_html(badges) -> str:
    return "".join(f"<span class='pp-badge {tone}'>{txt}</span>" for txt, tone in badges)


def hero(title: str, subtitle: str, badges=()) -> None:
    """Шапка экрана: объект и агрегат, подзаголовок, бейджи-статусы."""
    st.markdown(
        f"<div class='pp-hero'><div class='pp-hero-title'>{title}</div>"
        f"<div class='pp-hero-sub'>{subtitle}</div>"
        f"<div class='pp-badges'>{_badges_html(badges)}</div></div>",
        unsafe_allow_html=True,
    )


def provenance(*badges: tuple[str, str]) -> None:
    """Компактно показать происхождение данных или уровень модели."""
    st.markdown(f"<div class='pp-provenance'>{_badges_html(badges)}</div>", unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f"<div class='pp-note'>{text}</div>", unsafe_allow_html=True)
