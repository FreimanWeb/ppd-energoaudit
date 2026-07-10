"""Дизайн-система дашборда энергоаудита ППД.

Идентичность — «щиток КИПиА» (панель приборов), а не типовой SaaS-дашборд:
тёмная приборная плашка, показания КПИ моноширинным шрифтом (как на цифровом
табло), янтарный акцент вместо шаблонного синего градиента. Цвета ok/warn/bad
соответствуют реальной light-конвенции промышленной автоматики (зелёный/
жёлтый/красный сигнал).

Единый CSS + готовые HTML-компоненты (шапка-бирка объекта, теги-статусы,
заметки). Palette используется и в Plotly-графиках вкладок для единства стиля.
"""

from __future__ import annotations

import streamlit as st

PALETTE = {
    "primary": "#e2a63c", "accent": "#e2a63c", "ok": "#3ba272",
    "warn": "#e2a63c", "bad": "#d9534f", "ink": "#e7edf3", "muted": "#8fa0b3",
    "bg": "#0b1118", "card": "#121a24", "line": "#243040",
    "water": "#4f8fd1", "water_dark": "#2c5a8a", "throttle": "#e2a63c",
}

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

:root{
  --ink:#e7edf3; --muted:#8fa0b3; --bg:#0b1118; --panel:#121a24; --panel2:#182230;
  --line:#243040; --acc:#e2a63c; --ok:#3ba272; --warn:#e2a63c; --bad:#d9534f;
}
html, body, [class*="css"]{ font-family:'IBM Plex Sans',-apple-system,sans-serif; }
.stApp{ background:var(--bg); }
#MainMenu, header[data-testid="stHeader"], footer{ visibility:hidden; height:0; }
.block-container{ padding-top:1.1rem; padding-bottom:2.4rem; max-width:1360px; }

/* ── Бирка объекта (вместо баннера-градиента) ── */
.pp-tag{
  background:var(--panel); border:1px solid var(--line); border-top:3px solid var(--acc);
  border-radius:4px; padding:18px 24px 16px; margin-bottom:18px; position:relative;
}
.pp-tag::before{
  content:"ОБЪЕКТ"; position:absolute; top:-9px; left:20px; background:var(--bg);
  color:var(--acc); font-family:'IBM Plex Mono',monospace; font-size:.62rem;
  font-weight:600; letter-spacing:.14em; padding:0 8px;
}
.pp-tag-title{
  font-family:'IBM Plex Mono',monospace; font-size:1.55rem; font-weight:600;
  color:var(--ink); letter-spacing:.2px;
}
.pp-tag-sub{ font-size:.88rem; color:var(--muted); margin:3px 0 13px; }
.pp-badges{ display:flex; gap:8px; flex-wrap:wrap; }
.pp-badge{
  display:inline-flex; align-items:center; gap:5px; padding:4px 11px;
  border-radius:3px; font-size:.76rem; font-weight:600; font-family:'IBM Plex Mono',monospace;
  background:var(--panel2); color:var(--ink); border:1px solid var(--line);
}
.pp-badge::before{ content:"●"; font-size:.6rem; }
.pp-badge.ok{ color:var(--ok); border-color:rgba(59,162,114,.4); }
.pp-badge.ok::before{ color:var(--ok); }
.pp-badge.warn{ color:var(--warn); border-color:rgba(226,166,60,.4); }
.pp-badge.warn::before{ color:var(--warn); }
.pp-badge.bad{ color:var(--bad); border-color:rgba(217,83,79,.4); }
.pp-badge.bad::before{ color:var(--bad); }

/* ── KPI-показания (st.metric → цифровое табло) ── */
div[data-testid="stMetric"]{
  background:var(--panel); border:1px solid var(--line); border-radius:4px;
  padding:13px 16px 11px; position:relative; overflow:hidden;
}
div[data-testid="stMetric"]::before{
  content:""; position:absolute; top:0; left:0; width:3px; height:100%; background:var(--acc);
}
div[data-testid="stMetricValue"]{
  font-family:'IBM Plex Mono',monospace; font-size:1.7rem; font-weight:600;
  color:var(--ink); line-height:1.15;
}
div[data-testid="stMetricLabel"] p{
  font-size:.72rem; color:var(--muted); font-weight:600; font-family:'IBM Plex Mono',monospace;
  text-transform:uppercase; letter-spacing:.1em;
}
div[data-testid="stMetricDelta"]{ font-weight:600; font-family:'IBM Plex Mono',monospace; }

/* ── Заголовки / секции ── */
h1,h2,h3{ color:var(--ink); font-weight:700; }
h2,h3{ border-left:3px solid var(--acc); padding-left:11px; margin-top:.2rem; }
.stCaption, .st-emotion-cache p small{ color:var(--muted); }
p, li, span, label{ color:var(--ink); }

/* ── Вкладки ── */
div[data-baseweb="tab-list"]{
  gap:2px; background:transparent; padding:0; border-bottom:1px solid var(--line);
}
button[data-baseweb="tab"]{
  font-size:.86rem; font-weight:600; color:var(--muted); border-radius:0; padding:8px 14px;
}
button[data-baseweb="tab"][aria-selected="true"]{
  color:var(--acc); box-shadow:inset 0 -2px 0 var(--acc);
}

/* ── Контейнеры с рамкой ── */
div[data-testid="stVerticalBlockBorderWrapper"]{
  border-radius:4px; border-color:var(--line) !important; background:var(--panel);
}

/* ── Сайдбар ── */
section[data-testid="stSidebar"]{ background:var(--panel); border-right:1px solid var(--line); }
section[data-testid="stSidebar"] .block-container{ padding-top:1.4rem; }
section[data-testid="stSidebar"] label{ color:var(--muted); font-size:.8rem; }

/* ── Таблицы ── */
.stDataFrame{ border:1px solid var(--line); border-radius:4px; overflow:hidden; }

/* ── Инфо-плашки ── */
.pp-note{
  background:var(--panel2); border:1px solid var(--line); border-left:3px solid var(--acc);
  border-radius:3px; padding:10px 14px; color:var(--ink); font-size:.88rem;
}

/* ── Кнопки / инпуты (согласовать с плашкой доступа) ── */
.stButton>button, .stFormSubmitButton>button{
  border-radius:3px; font-weight:600; font-family:'IBM Plex Sans',sans-serif;
}
input, textarea{ font-family:'IBM Plex Mono',monospace !important; }
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def _badges_html(badges) -> str:
    return "".join(f"<span class='pp-badge {tone}'>{txt}</span>" for txt, tone in badges)


def hero(title: str, subtitle: str, badges=()) -> None:
    """Бирка объекта/агрегата: заголовок, подзаголовок, статус-теги."""
    st.markdown(
        f"<div class='pp-tag'><div class='pp-tag-title'>{title}</div>"
        f"<div class='pp-tag-sub'>{subtitle}</div>"
        f"<div class='pp-badges'>{_badges_html(badges)}</div></div>",
        unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f"<div class='pp-note'>{text}</div>", unsafe_allow_html=True)
