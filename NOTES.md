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

### 알려진 제한사항
- pykrx KRX API 응답 불능 → universe/시장데이터 fdr 대체 사용
  → Value(PER/PBR), Quality 중립값 37.5/50 고정
- DART finstate_all: 일부 종목 연결재무제표 없음 → Growth=0 처리
- 섹터 분류: pykrx 불능으로 전체 '기타' (fdr Dept 미제공)

### Phase 진행 상태
- [x] Phase 1: 골격 생성
- [x] Phase 2: 비즈니스 로직
- [x] Phase 3: 테스트 통과 (10/10)
- [x] Phase 4: 파이프라인 실행 완료 (output/stocks_top100.csv 생성)
- [x] Phase 5: 대시보드 20개 개선 완료 (2026-04-25)

---

## Day 1 (2026-04-25) - 대시보드 20개 개선 + 벤치마크 조사

### 구현된 20개 개선사항
**사용성 (1-7)**
1. 종목명/코드 텍스트 검색창 (Tab1 사이드바)
2. 투자등급 라벨 Strong Buy/Buy/Hold/Watch (Tab1 테이블 + Tab2 배지)
3. 레이더 차트 2종목 비교 (Tab2, 두 번째 종목 선택 시 오버레이)
4. 점수 셀 조건부 색상 이모지 (🟢🔵🟡🔴)
5. 기본 종합점수 내림차순 정렬 + 컬럼 정렬 안내 캡션
6. 섹터별 TOP 종목 하이라이트 카드 (Tab1 하단 expander)
7. 4축 기여도 % 텍스트 (종합점수 구성비, Tab2)

**안정성 (8-13)**
8. CSV 없을 때 실행 명령어 코드블록 안내
9. 빈 필터 결과 시 각 탭 안내 메시지
10. Tab3 4개 차트 모두 try/except 래핑
11. 숫자 컬럼 pd.to_numeric(errors='coerce').fillna(0) 타입 안전처리
12. 필수 컬럼 누락 시 어떤 컬럼인지 명시하여 에러 표시
13. 세션 상태 초기화 블록 (search_query, selected_compare)

**편의성 (14-20)**
14. CSV 다운로드 버튼 (quantlab_screener_YYYYMMDD.csv)
15. CSV 파일 마지막 수정 시간 표시 (사이드바)
16. 4축 각각 측정기준 툴팁/캡션 표시
17. 사이드바 유니버스 통계 카드 (최고/최저/중앙값/섹터수)
18. Tab4 시장 코멘트 섹션 (2026-04-25 기준)
19. explainer.py 근거 텍스트 상세화 + summary 키 추가
20. 벤치마크 10곳 기록 (이 섹션)

---

## 벤치마크 플랫폼 10곳

한국 주식 스크리너/퀀트 분석 플랫폼 및 글로벌 참고 서비스 조사 (2026-04-25 기준)

### 1. FnGuide (fnguide.com)
- **주요 특징**: 기관 투자자 전용 재무 데이터, 애널리스트 컨센서스(EPS/TP 추정치), 퀀트 팩터 라이브러리
- **QuantLab 대비**: 데이터 품질 최상위지만 유료(기관 전용). QuantLab은 무료 API로 유사 분석 제공.

### 2. KRX 정보데이터시스템 (data.krx.co.kr)
- **주요 특징**: 거래소 공식 시장/재무 데이터, 지수 구성종목, 업종 분류 무료 제공
- **QuantLab 대비**: 원시 데이터 제공만, 스크리닝·스코어링 기능 없음. QuantLab은 이를 자동화.

### 3. 증권플러스 - 두나무 (stockplus.com)
- **주요 특징**: 개인 투자자용 퀀트 스크리너, 조건 저장/공유, 모바일 앱 연동
- **QuantLab 대비**: UI/UX 우수, 종목 조건 커스텀 저장 가능. QuantLab은 4축 고정 방법론으로 일관성 제공.

### 4. 에프앤가이드 FISIS (fnguide.com/fisis)
- **주요 특징**: 종목 평가 스코어카드, 재무 품질 등급(A~F), 개인용 저가 요금제
- **QuantLab 대비**: 스코어 산출 방법론 비공개. QuantLab은 오픈소스로 산출 근거 완전 투명.

### 5. 씽크풀 (thinkpool.com)
- **주요 특징**: 퀀트 분석 + 주식 커뮤니티 통합, 기술적 분석 도구, 주도주 스캐너
- **QuantLab 대비**: 커뮤니티 기반 정보 풍부. QuantLab은 정량적 4축 스코어에 집중.

### 6. 토스증권 스탁스크리너 (tossinvest.com)
- **주요 특징**: 간편 필터 UI, 모바일 최적화, 대중 친화적 지표 설명
- **QuantLab 대비**: 지표 설명 쉽지만 심층 분석 부족. QuantLab은 DART 기반 상세 근거 제공.

### 7. Wisefn (wisefn.com)
- **주요 특징**: FnGuide 계열 개인용, 재무비율 멀티팩터 스크리닝, 시계열 재무 차트
- **QuantLab 대비**: 히스토리 재무 데이터 강점. QuantLab은 현재 시점 4축 종합 스코어에 특화.

### 8. Simplywall.st (simplywall.st)
- **주요 특징**: 글로벌 스노우플레이크 레이더 차트, 5축 시각화(Value/Future/Past/Health/Dividend), 직관적 UX
- **QuantLab 대비**: 글로벌 주식 지원, UX 최고 수준. QuantLab은 한국 시장 특화 + DART 직연동.

### 9. Finviz (finviz.com)
- **주요 특징**: 멀티팩터 스크리너 글로벌 표준, 히트맵 시각화, 수백 개 필터 조건
- **QuantLab 대비**: 미국 주식 전용. QuantLab은 KOSPI/KOSDAQ 특화, 한국 공시 기반.

### 10. Stock Analysis (stockanalysis.com)
- **주요 특징**: 깔끔한 재무 테이블, AI 요약 코멘트, 실적 캘린더, 무료 기본 기능
- **QuantLab 대비**: 미국 주식 중심, AI 코멘트 자동 생성. QuantLab은 동일 개념을 국내 주식에 적용.

### 벤치마크 인사이트
- **레이더 차트 표준**: Simplywall.st가 업계 표준으로 인정받음 → QuantLab 레이더 차트 방향성 일치
- **투명한 방법론**: 대부분 플랫폼이 스코어 산출 방법론 비공개 → QuantLab 오픈소스 강점
- **한국 시장 특화**: 국내 플랫폼 중 DART 직연동 + 4축 종합 스코어 제공은 QuantLab이 차별점
- **모바일 UX**: 토스증권, 증권플러스 대비 QuantLab은 Streamlit 기반으로 개선 여지 있음
