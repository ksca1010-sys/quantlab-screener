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

---

## 심층 기술 검토 (2026-04-29)

### 검토 목적
"지금 들어갈만한 종목을 찾자" — 스크리너 출력 결과를 신뢰할 수 있는지 수치·계산·파이프라인 전반을 점검.

---

### 발견된 버그 및 수정 상태

| # | 위치 | 버그 내용 | 심각도 | 상태 |
|---|------|----------|-------|------|
| 1 | `src/main.py:204` | CLI 가격 fetch 윈도우 1년(≈244거래일) → 모멘텀 가드 252일 미달, 전 종목 모멘텀 0점 | 치명 | ✅ 수정 (380일) |
| 2 | `dashboard/app.py:639` | 대시보드 동일 문제 | 치명 | ✅ 이전 세션 수정 |
| 3 | `src/backtest.py:115` | 백테스트 IC 산출 시 동일 윈도우 부족 → IC 결과 신뢰 불가 | 치명 | ✅ 수정 (380일) |
| 4 | `src/scorers/risk.py:48` | KOSPI 데이터 없을 때 `range(len(codes))` 정수 인덱스 → s1+s2+s3 NaN | 중요 | ✅ 수정 |
| 5 | `src/scorers/quality.py` | ROE·영업이익률 절댓값 minmax → IT vs 유통 섹터 간 불공정 비교 | 중요 | ✅ 수정 (섹터 분위수) |
| 6 | `src/scorers/value.py` | PEG 절대 임계값(PEG<1=만점) → 성장 섹터 구조적 불이익 | 중요 | ✅ 수정 (섹터 분위수) |
| 7 | `src/scorers/value.py` | PEG 커버리지 임계값 30% → 너무 낮아 부정확한 PEG 반영 | 보통 | ✅ 수정 (50%로 상향) |
| 8 | `src/universe.py` | ETF·스팩·우선주 필터 없음 → 시총 상위에 KODEX 200 등 포함 가능 | 중요 | ✅ 수정 |
| 9 | `dashboard/app.py` | Plotly 6.x `annotations=[]` 덮어쓰기 → 52H/52L 라벨 소멸 | 보통 | ✅ 이전 세션 수정 |

---

### 각 스코어러 신뢰도 평가

#### Growth (성장) — 신뢰도 ★★★★☆
- **매출 YoY·영업이익 YoY**: DART `thstrm_amount` 실데이터 기반. 신뢰 가능.
- **EPS CAGR**: 시작/끝 EPS 모두 양수일 때만 계산 (보수적). 적자→흑자 전환 종목은 NaN → 0점 처리. 실제로는 긍정 신호이나 안전을 위한 보수적 설계.
- **45일 공시 시차 룰**: `get_financial_data`에서 cutoff_ts - 45일 적용 → look-ahead bias 없음. ✓
- **제약**: DART 데이터 커버리지에 의존. API 키 없으면 Growth=0.

#### Value (가치) — 신뢰도 ★★★☆☆
- **PER·PBR**: Naver Finance 실시간 스크래핑. 섹터 분위수. 신뢰 가능.
- **배당수익률**: Naver Finance 스크래핑. 섹터 분위수로 정규화.
- **PEG**: PER ÷ EPS CAGR(%) — DART 실데이터 + Naver PER 조합. 이번 검토에서 섹터 분위수로 전환. 개선됨.
- **제약**: Naver HTML 구조 변경 시 PER/PBR 스크래핑 실패 가능. 정기 검증 필요.

#### Quality (펀더멘털) — 신뢰도 ★★★★☆ (수정 후)
- **ROE·영업이익률**: 이번 검토에서 절댓값 → 섹터 분위수로 전환. CLAUDE.md 헌법 준수.
- **부채비율**: 낮을수록 유리한 섹터 분위수. 금융업·제조업 레버리지 구조 차이를 반영.
- **이자보상배율**: 영업이익/금융비용. 무차입(금융비용=0) 시 100으로 cap 후 섹터 분위수.
- **자본잠식 처리**: equity≤0 시 ROE·부채비율 NaN. 정확.

#### Trend (추세) — 신뢰도 ★★★★☆ (수정 후)
- **MA 정배열 강도**: MA20/60/120 갭 합산 → 연속 강도. 이진 신호 대비 정보량 풍부.
- **52주 위치**: 현재가/52주고가. 직관적, 신뢰 가능.
- **거래량 추세**: 최근 20일 / 과거 60일 평균 비율. 타당.
- **12-1개월 모멘텀**: Carhart(1997) 표준. 수정 전 fetch 윈도우 부족으로 항상 0점이었음 → 수정 완료.

#### Risk (리스크) — 신뢰도 ★★★★☆ (수정 후)
- **베타**: KOSPI 대비 52주 공분산/분산. 표준 계산. 수정 전 KOSPI 없을 때 인덱스 버그 → 수정 완료.
- **연환산 변동성**: 일간 수익률 표준편차 × √252. 표준.
- **MDD**: rolling cummax 기반. 정확.
- **주의**: 리스크가 낮은 종목(저변동, 저베타)에 높은 점수 → 방어주 편향. 2026-05-06부터 종합점수에서는 제외하고 보조지표로만 표시.

---

### Look-ahead Bias 점검

| 항목 | 적용 방식 | 결과 |
|------|----------|------|
| DART 연간보고서 | t-45일 이전 공시만 사용 (`cutoff_ts = t - 45d`) | ✅ 없음 |
| Naver PER/PBR | 실시간 스크래핑 (분석 시점) | ✅ 없음 |
| 애널리스트 컨센서스 | 실시간 조회 (WiseReport) | ✅ 없음 |
| 가격 데이터 | `end=as_of_date`로 엄격 제한 | ✅ 없음 |
| 백테스트 | 분기 기준점 이전 380일 슬라이싱 | ✅ 없음 |

---

### 지금 들어갈만한 종목을 찾으려면?

**가장 신뢰할 수 있는 점수 조합:**

1. **Trend ≥ 60 + Growth ≥ 50**: 이미 가격 모멘텀이 붙은 성장주. 추세 추종 전략.
2. **Quality ≥ 60 + Value ≥ 50**: 건전한 재무 + 저평가. 가치주 전략.
3. **Total ≥ 55 + data_grade = A or B**: 데이터 커버리지가 높은 종목만 신뢰.

**스코어 한계점 인식:**
- **Growth/Quality는 DART 데이터 의존**: API 키 없으면 전부 0점 → Total 점수 왜곡. `data_grade=A/B`만 필터링할 것.
- **Naver 스크래핑 불안정**: PER/PBR이 NaN이면 Value도 낮게 나옴. 직접 확인 권장.
- **섹터 '기타' 종목 주의**: pykrx 섹터 조회 실패 시 모든 종목이 '기타'로 묶여 섹터 분위수가 전체 순위와 동일해짐.
- **스크리너 결과는 후보 압축 도구**: 최종 매수 결정은 반드시 공시(DART), 뉴스, 실적 확인 후 판단.

---

### 추가 개선 여지 (향후 과제)

- [x] 종합점수 공식 4축 균등 가중으로 복귀: `Risk`는 방어 성격 보조지표로 유지하되 `Total`에는 미반영.
- [x] Growth·Value 배당·Quality 부채/이자보상·Trend 내부 지표를 섹터 분위수 기준으로 통일.
- [x] 소규모 섹터의 전체 유니버스 fallback 제거: 섹터 간 절대 비교 금지 원칙을 우선.
- [ ] 적자→흑자 전환 종목 EPS CAGR 예외 처리 (현재 NaN → 0점, 실제는 강한 성장 신호)
- [ ] `_PREFERRED_PARENT` 매핑 확장 (현재 7개, 한국 시장 우선주 전체 커버 필요)
- [ ] 섹터 '기타' 비율 모니터링 + pykrx 실패 시 KRX 대체 소스 연동
