"""
애널리스트 컨센서스 데이터 조회 (WiseReport / Naver Finance)
출처: navercomp.wisereport.co.kr (FnGuide 제공 공개 페이지)
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_WISEREPORT_URL = (
    "https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx"
    "?cmp_cd={code}&target=cn"
)
_NAVER_RESEARCH_URL = (
    "https://m.stock.naver.com/api/research/stock/{code}?page=1&pageSize=5"
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
_REQUEST_DELAY = 0.5
_TIMEOUT = 8


@dataclass
class AnalystConsensus:
    code: str
    consensus_score: Optional[float] = None   # 1~5 scale (4.0 = 매수)
    target_price: Optional[int] = None        # 원 단위 컨센서스 목표주가
    analyst_count: Optional[int] = None       # 추정 증권사 수
    eps_consensus: Optional[float] = None
    per_consensus: Optional[float] = None
    buy_count: int = 0
    neutral_count: int = 0
    sell_count: int = 0
    recent_reports: list = field(default_factory=list)
    error: Optional[str] = None


def _parse_number(s: str) -> Optional[float]:
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def fetch_consensus(code: str) -> AnalystConsensus:
    """
    WiseReport HTML을 파싱해 애널리스트 컨센서스를 반환한다.
    네트워크 오류 시 error 필드가 채워진 빈 결과 반환.

    컨센서스 목표주가는 실시간 의견이므로 45일 공시 시차 룰 미적용.
    """
    result = AnalystConsensus(code=code)
    url = _WISEREPORT_URL.format(code=code)

    try:
        time.sleep(_REQUEST_DELAY)
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")

        # 컨센서스 요약 테이블 (인덱스 11)
        if len(tables) > 11:
            rows = tables[11].find_all("tr")
            if len(rows) > 1:
                cells = [td.get_text(strip=True) for td in rows[1].find_all("td")]
                if len(cells) >= 5:
                    result.consensus_score = _parse_number(cells[0])
                    tp = _parse_number(cells[1])
                    result.target_price = int(tp) if tp else None
                    result.eps_consensus = _parse_number(cells[2])
                    result.per_consensus = _parse_number(cells[3])
                    ac = _parse_number(cells[4])
                    result.analyst_count = int(ac) if ac else None

        # 증권사별 리포트 테이블 (인덱스 12)
        if len(tables) > 12:
            rows = tables[12].find_all("tr")
            for tr in rows[1:11]:
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(cells) >= 4:
                    opinion = cells[5] if len(cells) > 5 else cells[3]
                    result.recent_reports.append({
                        "broker": cells[0],
                        "date": cells[1],
                        "target": cells[2],
                        "opinion": opinion,
                    })

        # JS chartData3에서 의견 분포 파싱
        for name, count in re.findall(r'"name":"([^"]+)","y":(\d+\.?\d*)', html):
            n = int(float(count))
            name_lower = name.lower()
            if "매수" in name or name_lower in ("buy",):
                result.buy_count += n
            elif "중립" in name or name_lower in ("hold", "neutral"):
                result.neutral_count += n
            elif "매도" in name or name_lower in ("sell",):
                result.sell_count += n

    except requests.RequestException as e:
        result.error = str(e)
        logger.warning("애널리스트 데이터 조회 실패 [%s]: %s", code, e)
    except Exception as e:
        result.error = f"파싱 오류: {e}"
        logger.warning("애널리스트 데이터 파싱 실패 [%s]: %s", code, e)

    return result


def fetch_report_titles(code: str) -> list[dict]:
    """Naver 모바일 API에서 최근 리포트 제목·증권사 메타 조회."""
    url = _NAVER_RESEARCH_URL.format(code=code)
    try:
        time.sleep(_REQUEST_DELAY)
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return []
        data = resp.json()
        items = data if isinstance(data, list) else data.get("result", [])
        return [
            {
                "title": item.get("title", ""),
                "broker": item.get("brokerName", ""),
                "date": item.get("writeDate", "")[:10],
                "preview": item.get("previewContent", "")[:120],
            }
            for item in items[:5]
        ]
    except Exception as e:
        logger.warning("리포트 목록 조회 실패 [%s]: %s", code, e)
        return []
