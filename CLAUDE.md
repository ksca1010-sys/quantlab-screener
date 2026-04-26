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
- **[헌법] 가상수치·허수 계산 절대 금지**: 데이터 미확보 시 해당 항목은 반드시 NaN 또는 0점 처리. fillna(중간값·임의값) 금지. 스케일링 전 fillna(0) 금지 — 반드시 스케일링 후 fillna(0) 적용하여 결측이 동료 순위에 영향을 주지 않도록 함. 실데이터가 없는 항목은 점수에 기여하지 않는다.

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
