"""Скриншот Streamlit-дашборда через Playwright (управляет установленным Chrome)."""

import sys

from playwright.sync_api import sync_playwright


URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/dashboard.png"
TAB = sys.argv[3] if len(sys.argv) > 3 else None  # текст вкладки для клика (опц.)
OBJECT = sys.argv[4] if len(sys.argv) > 4 else None  # подстрока объекта в селекторе (опц.)

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=2)
    page.goto(URL, wait_until="load", timeout=60000)
    # дождаться РЕАЛЬНОГО рендера метрик (не skeleton): метка KPI появляется только
    # после полного прогона скрипта (вкл. парсинг сверки)
    page.get_by_text("УРЭ факт", exact=False).first.wait_for(timeout=120000)

    def settle():
        try:
            page.wait_for_selector(
                '[data-testid="stStatusWidget"]',
                state="detached",
                timeout=30000,
            )
        except Exception:
            pass
        page.wait_for_timeout(1500)

    settle()
    if OBJECT:
        sb = page.locator('[data-testid="stSelectbox"]', has_text="Объект")
        sb.locator('[data-baseweb="select"]').click()
        page.wait_for_timeout(500)
        page.get_by_role("option", name=OBJECT).first.click()
        settle()
    if TAB:
        page.get_by_role("tab", name=TAB).click()
        page.wait_for_timeout(2500)
    page.wait_for_timeout(1000)
    page.screenshot(path=OUT, full_page=True)
    browser.close()
    print("saved", OUT)
