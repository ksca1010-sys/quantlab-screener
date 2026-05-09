# QuantLab Screener

KOSPI 상위 200개 + KOSDAQ 상위 100개 유니버스를 4축(성장·가치·펀더멘털·추세)으로 스코어링하고, 상위 100개를 대시보드에 표시하는 분석 도구.

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

# 대시보드
streamlit run dashboard/app.py
```

## Point-in-Time 보정

- 과거 `--as-of-date` 실행에서는 현재 Naver PER/PBR을 사용하지 않습니다.
- KRX 기준일 PER/PBR/DIV 조회 성공 시 `DATA_DIR/krx_fundamentals/YYYYMMDD_ALL.csv`에 저장하고 재실행 때 캐시를 우선 사용합니다.
- 유니버스는 기준일별로 `DATA_DIR/universe/YYYYMMDD_K200_Q100.csv`에 저장합니다.
- DART 재무제표는 45일 공시 시차를 적용하고, 선택한 사업보고서 `rcept_no`와 전체 재무제표 API 응답의 `rcept_no`가 일치할 때만 사용합니다.
- 가격 데이터와 DART 재무제표도 `DATA_DIR` 아래에 캐시되어 반복 실행 시간을 줄입니다.

## 4축 스코어링 정의 (각 축 0~100점)

### Growth (성장)
| 항목 | 배점 |
|------|------|
| 매출 YoY 성장률 | 30점 |
| 영업이익 YoY 성장률 | 35점 |
| EPS CAGR | 25점 |
| 매출 성장 가속도 | 10점 |

### Value (가치)
| 항목 | 배점 |
|------|------|
| PER 섹터 분위수 (낮을수록 가점) | 30점 |
| PBR 섹터 분위수 | 30점 |
| PEG 섹터 분위수 | 25점 |
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
| 이동평균 갭 연속 강도 | 30점 |
| 52주 신고가 대비 위치 | 25점 |
| 거래량 추세 (최근 20일 / 지난 60일 평균) | 25점 |
| 12-1개월 모멘텀 | 20점 |

### 종합
```
TotalScore = 0.25 × Growth + 0.25 × Value + 0.25 × Quality + 0.25 × Trend
```

`Risk`는 시장 베타·변동성·MDD 기반 보조지표이며 종합점수에는 반영하지 않습니다.

## 산출물

- `output/stocks_universe_full.csv`: 전체 300개 유니버스 스코어링 결과
- `output/stocks_top100.csv`: 상위 100개 종목 스코어링 결과
- `output/snapshots/YYYYMMDD.csv`: 백테스트용 날짜별 스냅샷

주요 추적 컬럼:

- `rank`: 전체 랭킹
- `as_of_date`, `generated_at`: 분석 기준일과 생성 시각
- `market_data_source`: `krx_fundamental_by_date`, `krx_fundamental_cache`, `naver_current_fallback`, `unavailable_asof`
- `financial_years`, `dart_source_rcept_dt`, `dart_source_rcept_no`: 사용한 DART 재무제표 출처
- `data_grade`: PER/PBR/배당/ROE/영업이익률 커버리지 기준 데이터 등급

## 환경변수 (.env)

| 변수 | 설명 |
|------|------|
| `DART_API_KEY` | DART 전자공시 API 키 (https://opendart.fss.or.kr) |
| `OUTPUT_DIR` | 결과 CSV 저장 경로 (기본: ./output) |
| `DATA_DIR` | 임시 데이터 저장 경로 (기본: ./data) |
| `LOG_LEVEL` | 로그 레벨 (기본: INFO) |
