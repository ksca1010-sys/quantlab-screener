#!/usr/bin/env python3
"""Mobile preview — captures Streamlit at 375px and renders inline via Kitty protocol."""
import sys
import base64
import time
import os

MOBILE_W = 375
MOBILE_H = 812
REFRESH_SEC = 15
OUT_PNG = "/tmp/quantlab_mobile.png"


def _kitty_show(path: str) -> None:
    """Send PNG to terminal via Kitty Graphics Protocol (Ghostty-compatible)."""
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode()

    chunk = 4096
    parts = [data[i : i + chunk] for i in range(0, len(data), chunk)]
    for i, part in enumerate(parts):
        more = 1 if i < len(parts) - 1 else 0
        if i == 0:
            hdr = f"a=T,f=100,m={more},q=2"
        else:
            hdr = f"m={more}"
        sys.stdout.write(f"\x1b_G{hdr};{part}\x1b\\")
        sys.stdout.flush()
    print()


def _screenshot(url: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": MOBILE_W, "height": MOBILE_H})
        page.goto(url, wait_until="networkidle", timeout=20000)
        page.wait_for_timeout(1500)
        page.screenshot(path=OUT_PNG, full_page=False)
        browser.close()


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
    attempt = 0

    while True:
        attempt += 1
        os.system("clear")
        print(f"\033[36m📱 Mobile Preview  {MOBILE_W}×{MOBILE_H}px  →  {url}\033[0m")
        print(f"\033[90m[{attempt}] Ctrl+C 로 종료 · {REFRESH_SEC}초마다 자동 새로고침\033[0m\n")

        try:
            _screenshot(url)
            _kitty_show(OUT_PNG)
        except KeyboardInterrupt:
            print("\n\033[33m미리보기 종료\033[0m")
            sys.exit(0)
        except Exception as e:
            print(f"\033[31m⚠  {e}\033[0m")
            print("\033[90mStreamlit 시작 대기 중 — 재시도합니다...\033[0m")

        print(f"\n\033[90m{REFRESH_SEC}초 후 새로고침...\033[0m")
        try:
            time.sleep(REFRESH_SEC)
        except KeyboardInterrupt:
            print("\n\033[33m미리보기 종료\033[0m")
            sys.exit(0)


if __name__ == "__main__":
    main()
