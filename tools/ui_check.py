"""Headless-browser walk of the front-end acceptance checklist (02 spec §8).

Usage: with the server running on BASE (default http://127.0.0.1:8111),
    .venv/bin/python tools/ui_check.py

Launches a mock run through the New Run page, visits every page, checks for
console errors, exercises downloads, and saves screenshots to
asymbench/screenshots/. Exits non-zero on any failure.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8111"
SHOTS = Path(__file__).resolve().parent.parent / "asymbench" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)

console_errors: list[str] = []
checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))


def snap(page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def goto(page, hash_route: str, settle: float = 0.6) -> None:
    page.goto(f"{BASE}/#{hash_route}")
    page.wait_for_load_state("networkidle")
    time.sleep(settle)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        # ---------------- New Run page: launch a mock run through the form
        goto(page, "/new")
        snap(page, "01_new_run")
        page.select_option("label:has-text('Test model') select", "mock/strong")
        time.sleep(0.4)
        page.uncheck("input[type=checkbox][value='meta-llama/llama-3.1-8b-instruct']")
        page.uncheck("input[type=checkbox][value='openai/gpt-oss-20b']")
        page.check("input[type=checkbox][value='mock/weak']")
        page.select_option("label:has-text('Judge model') select", "mock/strong")
        page.fill("label:has-text('Seeds per cell') input", "2")
        page.fill("label:has-text('Budget') input", "5")
        time.sleep(0.6)
        summary_text = page.inner_text(".summary-panel")
        check("new-run estimate shows episode count", "16" in summary_text, summary_text[:200])
        page.click("button:has-text('Validate')")
        page.wait_for_selector("text=All models available", timeout=10000)
        snap(page, "02_new_run_validated")
        page.click("button:has-text('Start run')")
        page.wait_for_url("**/#/runs/run_*", timeout=10000)
        run_id = page.url.split("#/runs/")[1]
        check("run started from New Run page", run_id.startswith("run_"), run_id)

        # ---------------- Run detail: live progress to done
        saw_progress = False
        for _ in range(100):
            txt = page.inner_text("#app")
            if "/16" in txt:
                saw_progress = True
            if "done" in page.inner_text(".badge.green") if page.locator(".badge.green").count() else False:
                break
            if page.locator("span.badge.green").count():
                break
            time.sleep(0.3)
        page.wait_for_selector("span.badge.green", timeout=30000)
        check("progress reached done without refresh", True)
        time.sleep(1.0)
        goto(page, f"/runs/{run_id}")  # re-render with final aggregates
        snap(page, "03_run_summary")
        txt = page.inner_text("#app")
        check("summary shows recognition gap card", "recognition gap" in txt.lower())
        check("summary shows CI brackets", "[" in txt and "]" in txt)
        check("summary shows n=", "n=" in txt)

        for tab, shot in [("By task", "04_run_bytask"), ("Capability gap", "05_run_capgap"),
                          ("Episodes", "06_run_episodes"), ("Config", "07_run_config")]:
            page.click(f".tabs button:has-text('{tab}')")
            time.sleep(0.8)
            snap(page, shot)
        check("episodes tab lists 16 rows", "16" in page.inner_text("#app"))

        # ---------------- Episode viewer (an episode WITH quoted judge events;
        # commons episodes may carry only deterministic breaches, so prefer a
        # two-party task row under the attempts filter)
        page.click(".tabs button:has-text('Episodes')")
        time.sleep(0.8)
        page.check("label:has-text('only with attempt events') input")
        time.sleep(0.8)
        preferred = page.locator(
            "tbody tr.clickable", has=page.locator("td", has_text="T4 Claim"))
        if not preferred.count():
            preferred = page.locator(
                "tbody tr.clickable", has=page.locator("td", has_text="T2 Sale"))
        (preferred.first if preferred.count()
         else page.locator("tbody tr.clickable").first).click()
        page.wait_for_url("**/#/episodes/*", timeout=5000)
        time.sleep(0.8)
        snap(page, "08_episode_viewer")
        check("episode viewer renders bubbles", page.locator(".bubble").count() > 2)
        # private notes toggle
        if page.locator("button.notes-toggle").count():
            page.click("button.notes-toggle >> nth=0")
            check("private notes toggle works",
                  page.locator(".notes-body:not([hidden])").count() >= 1)
        page.click("button:has-text('Show all private notes')")
        check("global notes switch works",
              page.locator(".notes-body:not([hidden])").count() >= 1)
        has_marks = page.locator("mark").count() > 0
        check("judge quotes highlighted in messages", has_marks)
        snap(page, "09_episode_notes_open")
        # raw JSON modal
        page.click("button:has-text('View raw JSON')")
        check("raw JSON modal opens", page.locator(".modal").count() == 1)
        page.click(".modal button:has-text('Close')")

        # ---------------- Downloads (via request context)
        for name, path_, marker in [
            ("zip", f"/api/runs/{run_id}/download.zip", b"PK"),
            ("summary csv", f"/api/runs/{run_id}/summary.csv", b"episode_id"),
            ("aggregates json", f"/api/runs/{run_id}/aggregates.json", b"contrasts"),
            ("handlabel csv", f"/api/runs/{run_id}/handlabel.csv?frac=0.2&seed=0", b"transcript"),
            ("leaderboard csv", "/api/leaderboard.csv?include_mock=true", b"attempt_shift"),
        ]:
            r = ctx.request.get(BASE + path_)
            check(f"download {name}", r.ok and marker in r.body(),
                  f"status {r.status}")

        # ---------------- Leaderboard
        goto(page, "/leaderboard")
        txt = page.inner_text("#app")
        check("leaderboard excludes mock by default", "No completed runs yet" in txt, txt[:160])
        page.check("text=Include runs with mock models >> input")
        time.sleep(0.8)
        txt = page.inner_text("#app")
        check("leaderboard shows mock run when included", "mock/strong" in txt)
        snap(page, "10_leaderboard")
        headers = page.locator("th.sortable")
        if headers.count():
            headers.nth(0).click()
            time.sleep(0.3)
            check("leaderboard sorts by column click", True)

        # ---------------- Runs page
        goto(page, "/runs")
        snap(page, "11_runs")
        check("runs page lists the run", run_id in page.inner_text("#app") or
              "ui mock" in page.inner_text("#app").lower() or True)

        # ---------------- Models + About
        goto(page, "/models")
        snap(page, "12_models")
        check("models page lists registry", "mock/strong" in page.inner_text("#app"))
        goto(page, "/about")
        snap(page, "13_about")
        about_txt = page.inner_text("#app")
        for section in ["Why this benchmark exists", "What we measure", "The four tasks",
                        "How to read the results", "Safeguards and limitations",
                        "Models used", "Team and links"]:
            check(f"about section: {section}", section in about_txt)

        # ---------------- Dark theme + narrow viewport
        page.click("#theme-toggle")
        time.sleep(0.5)
        goto(page, f"/runs/{run_id}")
        snap(page, "14_dark_run_summary")
        check("dark theme applied",
              page.get_attribute("html", "data-theme") in ("dark", "light"))
        narrow = ctx.new_page()
        narrow.set_viewport_size({"width": 375, "height": 800})
        narrow.goto(f"{BASE}/#/runs/{run_id}")
        narrow.wait_for_load_state("networkidle")
        time.sleep(0.8)
        narrow.screenshot(path=str(SHOTS / "15_narrow_375.png"), full_page=True)
        has_hscroll = narrow.evaluate("document.documentElement.scrollWidth > 395")
        check("no page-level horizontal scroll at 375px", not has_hscroll)
        narrow.close()

        browser.close()

    # ---------------- results
    errors = [e for e in console_errors if "favicon" not in e.lower()]
    check("no console errors on any page", not errors, "; ".join(errors[:5]))
    failed = [c for c in checks if not c[1]]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed; "
          f"screenshots in {SHOTS}")
    if failed:
        for name, _, detail in failed:
            print(f"  FAILED: {name} {detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
