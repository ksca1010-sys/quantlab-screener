# QuantLab 종목 스크리너 PoC - 자동 진행 작업

너는 지금부터 아래 명세대로 PoC를 끝까지 자동으로 만든다. 중간에 사용자에게 묻지 말고 합리적 기본값으로 결정하며 진행한다. 단 아래 STOP 조건에서만 멈춘다.

## STOP 조건 (이때만 멈춰서 사용자 확인)

1. .env 파일에 DART_API_KEY가 비어있어 실제 외부 호출이 불가능할 때
2. 파괴적 명령(rm -rf, git push --force, git reset --hard 등)을 실행해야 할 때
3. requirements.txt 설치가 실패하고 OS 레벨 의존성이 필요할 때

위 외에는 모두 자동 진행. 작업 중간 결정사항은 NOTES.md에 로그로 남긴다.

## 프로젝트 정의

- 이름: quantlab-screener
- 목표: KOSPI + KOSDAQ 통합 시총 상위 100개를 4축(성장·가치·펀더멘털·추세)으로 스코어링
- 산출물: output/stocks_top100.csv
- 저장: 로컬 CSV (DB 연동 없음)
- 매매 기능 절대 포함 금지 (분석 전용)

## 기술 스택

- Python 3.11+ / venv
- 패키지: FinanceDataReader, opendart-reader, pykrx, pandas, numpy, python-dotenv, pyyaml, tqdm, tabulate, pytest
- 머신러닝/최적화 라이브러리(sklearn, scipy.optimize 등) 사용 금지
- 웹 프레임워크(Streamlit, FastAPI 등) 추가 금지

## 폴더 구조

quantlab-screener/
├── .env.example
├── .env                    (gitignore)
├── .gitignore
├── CLAUDE.md
├── NOTES.md
├── README.md
├── requirements.txt
├── config/
│   └── universe.yaml       (생성됨)
├── src/
│   ├── __init__.py
│   ├── data_loader.py
│   ├── universe.py
│   ├── scorers/
│   │   ├── __init__.py
│   │   ├── growth.py
│   │   ├── value.py
│   │   ├── quality.py
│   │   └── trend.py
│   ├── normalizer.py
│   ├── aggregator.py
│   └── main.py
├── tests/
│   └── test_growth.py
├── data/                   (gitignore)
└── output/                 (gitignore)

## 4축 스코어링 정의 (각 축 0~100점)

### Growth (성장)
- 매출 YoY 성장률 (최근 분기): 25점
- 영업이익 YoY 성장률: 25점
- EPS 3개년 CAGR: 25점
- 매출 성장 가속도 (최근 4분기 추세 기울기): 25점

### Value (가치)
- PER 섹터 분위수 (낮을수록 가점): 30점
- PBR 섹터 분위수: 30점
- PEG (1 이하 만점): 25점
- 배당수익률: 15점

### Quality (펀더멘털 건전성)
- ROE: 30점
- 영업이익률: 25점
- 부채비율 역수: 25점
- 이자보상배율: 20점

### Trend (추세)
- 이동평균 정배열 (20 > 60 > 120일): 30점
- 52주 신고가 대비 위치: 25점
- 거래량 추세 (최근 20일 평균 / 지난 60일 평균): 25점
- RSI(14) 30~70 정상 범위: 20점

### 종합
TotalScore = 0.25 × Growth + 0.25 × Value + 0.25 × Quality + 0.25 × Trend

## 비즈니스 로직 핵심 제약

1. 공시 시차 45일 룰: 분석 시점 t의 펀더멘털은 t-45일 이전 공시만 사용. data_loader.py의 재무 조회 함수에 as_of_date 파라미터로 명시적 구현. 주석으로 이유 설명.

2. 섹터 내 분위수 정규화: PER/PBR 등 절댓값 비교 금지. KRX 업종분류 기준 섹터별 분위수. normalizer.py에 sector_percentile(df, column, sector_col) 함수로 구현.

3. API 호출 레이트 제어: DART는 호출 간 sleep(0.1). 진행률 tqdm으로 표시.

4. 에러 핸들링: 종목별 데이터 누락은 NaN 처리 후 로그. 전체 파이프라인은 계속 진행. main.py 마지막에 누락 종목 수 출력.

5. 재현성: universe.yaml은 첫 실행에만 생성. 이후는 그 파일 고정 사용. main.py에 --refresh-universe 플래그로 재생성 가능.

## 환경변수 (.env)

DART_API_KEY=
OUTPUT_DIR=./output
DATA_DIR=./data
LOG_LEVEL=INFO

## 작업 순서

### Phase 1: 골격 (5분)
1. requirements.txt 작성
2. python3.11 -m venv .venv 후 의존성 설치
3. .gitignore 작성 (.env, .venv/, __pycache__/, *.pyc, .DS_Store, data/, output/)
4. .env.example 작성 후 .env로 복사 (DART_API_KEY는 빈 값)
5. CLAUDE.md 작성 (아래 CLAUDE.md 내용 섹션 참조)
6. NOTES.md 초안 작성 (Day 0 작업 일지)
7. README.md 간단히 작성 (목적, 실행법, 4축 정의)
8. 폴더 구조 모두 생성 (빈 __init__.py 포함)

### Phase 2: 비즈니스 로직 (15분)
9. src/universe.py: FinanceDataReader.StockListing('KRX') + pykrx로 시총 상위 100개. KOSPI/KOSDAQ 마켓 구분 컬럼 포함. KRX 업종분류 코드 함께 저장. config/universe.yaml에 dump.

10. src/data_loader.py:
   - get_price_data(code, start, end) → FinanceDataReader 일봉
   - get_financial_data(code, as_of_date) → OpenDartReader 분기 재무 (as_of_date - 45일 이전 공시만)
   - get_market_cap(code, date) → pykrx
   - 모두 인메모리 캐시 데코레이터 적용

11. src/scorers/ 4개 모듈 각각 구현:
   - 입력: pandas DataFrame (universe + 필요한 raw data)
   - 출력: pd.Series (종목코드 → 점수 0~100)

12. src/normalizer.py: sector_percentile, minmax_scale 함수

13. src/aggregator.py: 4축 결과 합산, 랭킹, 종합 점수

14. src/main.py: 전체 파이프라인 오케스트레이션
   - argparse로 --refresh-universe, --as-of-date 옵션
   - 진행 단계마다 logger.info
   - 마지막에 상위 10개 종목 표 형태로 콘솔 출력

### Phase 3: 테스트 & 커밋 (5분)
15. tests/test_growth.py: 가짜 입력 데이터로 growth.py 함수 1~2개 테스트
16. python -m pytest tests/ 실행해서 통과 확인
17. git init 후 첫 커밋 (.env는 .gitignore에 의해 자동 제외 확인)

### Phase 4: 실행 (사용자 개입 시점)
18. .env의 DART_API_KEY가 비어있는지 확인
19. 비어있으면 STOP 조건 발동 → 사용자에게 다음 안내 출력:
    "DART API 키 입력 필요. opendart.fss.or.kr 에서 인증키 신청 후 .env 파일의 DART_API_KEY 뒤에 40자리 키 붙여넣기. 완료되면 continue 라고 답해주세요."

20. 사용자가 continue 응답하면:
   - python -m src.main 실행
   - 진행 로그 사용자에게 보여주기
   - 완료 후 output/stocks_top100.csv 생성 확인
   - 상위 10개 종목 표 출력
   - 누락된 종목 수, 섹터 분포 요약 출력

## CLAUDE.md 내용 (이대로 작성)

# QuantLab Screener

## Context
KOSPI + KOSDAQ 통합 시총 상위 100개를 4축(성장·가치·펀더멘털·추세)으로 스코어링하는 PoC. 분석 전용, 매매 기능 없음.

## Hard Rules
- 매매 발주 코드 절대 추가 금지
- API 키 하드코딩 금지 (.env에서만 로드)
- 공시 시차 45일 룰: 분석 시점 t에서 t-45일 이전 공시만 사용
- 섹터 내 분위수 정규화 필수 (절댓값 비교 금지)
- 머신러닝/최적화 라이브러리 사용 금지 (pandas만)
- 웹 프레임워크 추가 금지 (PoC는 CLI 전용)

## Tech Stack
Python 3.11 + venv / FinanceDataReader / opendart-reader / pykrx / pandas

## Code Style
- 함수 단위 작게, 타입힌트 적용
- 비즈니스 로직 변경 시 NOTES.md에 의사결정 로그
- 공시 시차 관련 함수는 주석으로 이유 설명

## Workflow
- 작업 시작: source .venv/bin/activate
- 실행: python -m src.main
- 유니버스 갱신: python -m src.main --refresh-universe
- 특정 시점 분석: python -m src.main --as-of-date 2026-01-15

## Phase 4 완료 후 자동 출력 형식

작업 완료 시 다음 정보를 콘솔에 정리해 보여줘:

1. 처리 결과 요약
   - 총 대상: 100개
   - 성공: N개
   - 실패: M개 (사유별 집계)

2. 상위 10개 종목 표
   - 컬럼: 순위, 종목명, 종목코드, 시장(KOSPI/KOSDAQ), 섹터, Growth, Value, Quality, Trend, Total

3. 섹터 분포
   - 상위 30개의 섹터별 종목 수

4. 다음 단계 제안 (3줄 이내)

## 시작

지금 위 명세대로 작업 시작. NOTES.md에 작업 진행 로그를 실시간 남겨라. STOP 조건 외에는 사용자에게 묻지 말 것.
