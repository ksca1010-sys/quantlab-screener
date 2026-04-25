# QuantLab Screener

KOSPI + KOSDAQ 통합 시총 상위 100개를 4축(성장·가치·펀더멘털·추세)으로 스코어링하는 분석 도구.

> **분석 전용** — 매매 기능 없음.

## 실행법

```bash
# 환경 설정
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# .env 설정
cp .env.example .env
# .env 파일에 DART_API_KEY 입력

# 실행
python -m src.main

# 유니버스 갱신 후 실행
python -m src.main --refresh-universe

# 특정 시점 분석
python -m src.main --as-of-date 2026-01-15
```

## 4축 스코어링 정의 (각 축 0~100점)

### Growth (성장)
| 항목 | 배점 |
|------|------|
| 매출 YoY 성장률 (최근 분기) | 25점 |
| 영업이익 YoY 성장률 | 25점 |
| EPS 3개년 CAGR | 25점 |
| 매출 성장 가속도 (최근 4분기 추세 기울기) | 25점 |

### Value (가치)
| 항목 | 배점 |
|------|------|
| PER 섹터 분위수 (낮을수록 가점) | 30점 |
| PBR 섹터 분위수 | 30점 |
| PEG (1 이하 만점) | 25점 |
| 배당수익률 | 15점 |

### Quality (펀더멘털 건전성)
| 항목 | 배점 |
|------|------|
| ROE | 30점 |
| 영업이익률 | 25점 |
| 부채비율 역수 | 25점 |
| 이자보상배율 | 20점 |

### Trend (추세)
| 항목 | 배점 |
|------|------|
| 이동평균 정배열 (20 > 60 > 120일) | 30점 |
| 52주 신고가 대비 위치 | 25점 |
| 거래량 추세 (최근 20일 / 지난 60일 평균) | 25점 |
| RSI(14) 30~70 정상 범위 | 20점 |

### 종합
```
TotalScore = 0.25 × Growth + 0.25 × Value + 0.25 × Quality + 0.25 × Trend
```

## 산출물

- `output/stocks_top100.csv`: 상위 100개 종목 스코어링 결과

## 환경변수 (.env)

| 변수 | 설명 |
|------|------|
| `DART_API_KEY` | DART 전자공시 API 키 (https://opendart.fss.or.kr) |
| `OUTPUT_DIR` | 결과 CSV 저장 경로 (기본: ./output) |
| `DATA_DIR` | 임시 데이터 저장 경로 (기본: ./data) |
| `LOG_LEVEL` | 로그 레벨 (기본: INFO) |
