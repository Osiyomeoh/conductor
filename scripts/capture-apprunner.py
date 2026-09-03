"""Capture screenshots of the live App Runner deployment for the submission.

    .venv/bin/python scripts/capture-apprunner.py

Writes docs/shots/apprunner-*.png against the permanent public URL.
"""
from __future__ import annotations

import os
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("CONDUCTOR_URL", "https://pe6euudszs.us-west-2.awsapprunner.com")
OUT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "shots")
VP = {"width": 1440, "height": 900}


def shot(page, path, full=False):
    page.screenshot(path=os.path.join(OUT, path), full_page=full)
    print("wrote", path)


def click_if(page, text):
    el = page.get_by_text(text, exact=False).first
    if el.count() if hasattr(el, "count") else True:
        try:
            el.click(timeout=3000)
            return True
        except Exception:
            return False
    return False


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context(viewport=VP, device_scale_factor=2).new_page()

        pg.goto(BASE, wait_until="networkidle", timeout=60000)
        time.sleep(1.5)
        shot(pg, "apprunner-landing.png")
        shot(pg, "apprunner-landing-full.png", full=True)

        pg.goto(BASE + "/pricing", wait_until="networkidle", timeout=60000)
        time.sleep(1.0)
        shot(pg, "apprunner-pricing.png")

        pg.goto(BASE + "/app", wait_until="networkidle", timeout=60000)
        time.sleep(1.5)
        shot(pg, "apprunner-app-home.png")

        # Drive the loop so the board fills, then capture the real screens.
        for label in ("Run six",):
            try:
                pg.get_by_text(label, exact=False).first.click(timeout=4000)
                time.sleep(2.5)
            except Exception as e:
                print("could not click", label, e)

        for nav, name in (("Board", "apprunner-app-board.png"),
                          ("Decisions", "apprunner-app-decisions.png"),
                          ("Activity", "apprunner-app-activity.png"),
                          ("Team", "apprunner-app-team.png"),
                          ("Cost & trust", "apprunner-app-cost.png")):
            try:
                pg.get_by_text(nav, exact=True).first.click(timeout=4000)
                time.sleep(1.2)
                shot(pg, name)
            except Exception as e:
                print("could not open", nav, e)

        b.close()


if __name__ == "__main__":
    main()
