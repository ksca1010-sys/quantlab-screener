from __future__ import annotations

import argparse
import csv
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "output" / "stocks_top100.csv"
REQUIRED_COLS = [
    "rank",
    "name",
    "code",
    "market",
    "sector",
    "Growth",
    "Value",
    "Quality",
    "Trend",
    "Total",
]
ALLOWED_MARKET_SOURCES = {
    "krx_fundamental_by_date",
    "krx_fundamental_cache",
    "naver_current_fallback",
    "unavailable_asof",
}

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f))


def check_output_csv(path: Path = CSV_PATH) -> None:
    if not path.exists():
        raise AssertionError(f"missing output CSV: {path}")

    header = _read_header(path)
    duplicate_headers = sorted({col for col in header if header.count(col) > 1})
    if duplicate_headers:
        raise AssertionError(f"duplicate CSV columns: {duplicate_headers}")

    missing = [col for col in REQUIRED_COLS if col not in header]
    if missing:
        raise AssertionError(f"missing required CSV columns: {missing}")

    df = pd.read_csv(path, dtype={"code": str})
    if df.empty:
        raise AssertionError("output CSV is empty")

    if df["rank"].isna().any() or df["rank"].duplicated().any():
        raise AssertionError("rank column must be present, non-null, and unique")

    for col in ["Growth", "Value", "Quality", "Trend", "Total"]:
        values = pd.to_numeric(df[col], errors="coerce")
        if values.isna().any():
            raise AssertionError(f"{col} contains non-numeric values")
        if not values.between(0, 100).all():
            raise AssertionError(f"{col} must stay in the 0-100 score range")

    codes = df["code"].astype(str).str.zfill(6)
    if not codes.str.fullmatch(r"\d{6}").all():
        raise AssertionError("stock codes must be six digits after normalization")

    if "market_data_source" in df.columns:
        sources = set(df["market_data_source"].dropna().astype(str))
        unknown_sources = sorted(sources - ALLOWED_MARKET_SOURCES)
        if unknown_sources:
            raise AssertionError(f"unknown market_data_source values: {unknown_sources}")

    if {"as_of_date", "market_data_source"}.issubset(df.columns):
        as_of_values = pd.to_datetime(df["as_of_date"], errors="coerce").dropna()
        if not as_of_values.empty:
            latest_as_of = as_of_values.max().normalize()
            today = pd.Timestamp.today().normalize()
            latest_allowed = today - pd.tseries.offsets.BDay(1) if today.weekday() >= 5 else today
            is_historical = latest_as_of < (latest_allowed - pd.tseries.offsets.BDay(1))
            has_current_fallback = (df["market_data_source"] == "naver_current_fallback").any()
            if is_historical and has_current_fallback:
                raise AssertionError("historical as_of_date must not use current Naver fallback")


def check_export_idempotency() -> None:
    from src.aggregator import to_csv

    sample = pd.DataFrame(
        {
            "rank": [99, 100],
            "code": ["000001", "000002"],
            "name": ["A", "B"],
            "market": ["KOSPI", "KOSPI"],
            "sector": ["Tech", "Tech"],
            "Growth": [80.0, 40.0],
            "Value": [70.0, 30.0],
            "Quality": [60.0, 20.0],
            "Trend": [50.0, 10.0],
            "Risk": [40.0, 30.0],
            "Total": [65.0, 25.0],
        }
    )

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "stocks_top100.csv"
        to_csv(sample, str(out))
        header = _read_header(out)
        if header.count("rank") != 1:
            raise AssertionError("to_csv wrote duplicate rank columns")
        saved = pd.read_csv(out)
        if saved["rank"].tolist() != [1, 2]:
            raise AssertionError("to_csv did not rewrite rank deterministically")


def check_dashboard_helpers() -> None:
    from dashboard import app

    df = pd.DataFrame(
        {
            "rank": [1],
            "sector": ["Tech"],
            "name": ["A"],
            "Trend": [75.0],
        }
    ).set_index(pd.Index([1], name="rank"))
    plain = app._plain_df(df)
    if plain.index.name is not None or plain.columns.tolist().count("rank") != 1:
        raise AssertionError("dashboard plain DataFrame must drop rank index only")

    sector_info = app._derive_sector_strength_from_scores(
        pd.DataFrame(
            {
                "sector": ["Tech", "Bank"],
                "name": ["A", "B"],
                "Trend": [75.0, 55.0],
            }
        )
    )
    if not app._is_bull_pick("Tech", 75.0, set(sector_info["bull_sectors"])):
        raise AssertionError("bull-sector fallback did not mark a strong trend pick")


def check_streamlit_health(timeout: float = 20.0) -> None:
    port = _free_port()
    log_path = Path(tempfile.gettempdir()) / f"quantlab_streamlit_{port}.log"
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "dashboard/app.py",
        "--server.headless",
        "true",
        "--server.port",
        str(port),
        "--server.address",
        "127.0.0.1",
    ]

    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + timeout
        last_error: Exception | None = None
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            try:
                with urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1) as resp:
                    body = resp.read().decode("utf-8", errors="replace").strip()
                if body == "ok":
                    check_streamlit_shell(f"http://127.0.0.1:{port}")
                    return
                last_error = AssertionError(f"unexpected health response: {body!r}")
            except Exception as exc:
                last_error = exc
                time.sleep(0.5)

        log_tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:])
        raise AssertionError(f"Streamlit health check failed: {last_error}\n{log_tail}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def _read_url_text(url: str, timeout: float = 10.0) -> str:
    with urlopen(url, timeout=timeout) as resp:
        status = getattr(resp, "status", 200)
        if status >= 400:
            raise AssertionError(f"unexpected HTTP status from {url}: {status}")
        return resp.read().decode("utf-8", errors="replace")


def check_streamlit_shell(base_url: str, timeout: float = 10.0) -> None:
    html = _read_url_text(base_url.rstrip("/") + "/", timeout=timeout)
    lowered = html.lower()
    if "<html" not in lowered or "streamlit" not in lowered:
        raise AssertionError("Streamlit root did not return the expected app shell")
    blocked_terms = [
        "valueerror:",
        "traceback",
        "modulenotfounderror",
        "internal server error",
        "application error",
    ]
    found = [term for term in blocked_terms if term in lowered]
    if found:
        raise AssertionError(f"Streamlit root contains error markers: {found}")


def check_deployed_health(base_url: str, timeout: float = 10.0) -> None:
    health_url = f"{base_url.rstrip('/')}/_stcore/health"
    with urlopen(health_url, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace").strip()
    if body != "ok":
        raise AssertionError(f"unexpected deployed health response from {health_url}: {body!r}")
    check_streamlit_shell(base_url, timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser(description="QuantLab local smoke checks")
    parser.add_argument("--skip-pytest", action="store_true", help="skip the full pytest suite")
    parser.add_argument("--skip-streamlit", action="store_true", help="skip Streamlit health check")
    parser.add_argument("--url", help="optional deployed Streamlit app URL for canary health check")
    args = parser.parse_args()

    if not args.skip_pytest:
        _run([sys.executable, "-m", "pytest", "-q"])

    check_output_csv()
    check_export_idempotency()
    check_dashboard_helpers()
    if not args.skip_streamlit:
        check_streamlit_health()
    if args.url:
        check_deployed_health(args.url)

    print("smoke check passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
