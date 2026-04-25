# QuantLab Screener - 작업 일지

## Day 0 (2026-04-25) - 초기 구축

### 작업 내용
- PROMPT.md 명세 기반으로 프로젝트 골격 생성 시작
- Phase 1: 폴더 구조, 설정 파일, 의존성 파일 생성

### 결정사항
- Python 3.11 venv 사용
- requirements.txt: finance-datareader (PyPI 패키지명은 finance-datareader, import는 FinanceDataReader), opendart-reader, pykrx, pandas, numpy, python-dotenv, pyyaml, tqdm, tabulate, pytest
- opendart-reader 패키지명: `opendart-reader` (pip install opendart-reader)
- 인메모리 캐시: functools.lru_cache 활용 (외부 의존성 없음)
- config/universe.yaml: 첫 실행 시 생성, --refresh-universe 플래그로 재생성

### 비즈니스 로직 결정
- 공시 시차 45일: as_of_date - timedelta(45) 이전 공시만 사용
- 섹터 분류: KRX 업종분류 코드 (pykrx 제공)
- 시총 상위 100개: KOSPI + KOSDAQ 통합 후 시총 내림차순 정렬

### 버그 수정
- minmax_scale에서 s_max==s_min 시 NaN 위치까지 중간값으로 채우는 버그 수정
  → series.notna() 위치에만 중간값 할당, NaN 보존

### Phase 진행 상태
- [x] Phase 1: 골격 생성
- [x] Phase 2: 비즈니스 로직
- [x] Phase 3: 테스트 통과 (9/9)
- [ ] Phase 4: 실행 (사용자 개입 필요 - DART_API_KEY)
