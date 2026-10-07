# SUIT 타이포그래피 구현·검증 · 2026-10-07

## 기준과 범위

- 저장소: Phjrab/mediflow-kiosk-core. 기존 branch `codex/ui-mediflow-guided-screening` 유지.
- Before: `899affd6572affb56156f7c40774efda56df7a8d` (드롭다운 높이 조정까지 포함).
- After 구현: `54cedc308a67b8a91517919870bc04bd22da16e1`.
- 시작 작업트리 clean. 현재 UI 구조를 유지하고 폰트·크기·굵기·자간·행간만 정리했다.
  위젯 제목의 여러 줄 표시에는 기존 헤더의 높이/padding만 보완했다.
- 적용되는 상위/repo AGENTS.md는 없었다. 기존 DESIGN_SPEC/DECISIONS/HANDOFF/INVENTORY/VALIDATION을 확인했다.
  repo 루트에는 prompt pack이 없어서 사용자 첨부 경로의 MediFlow START_HERE/MASTER_PROMPT를 읽었다.
  이번 사용자 요청의 타이포그래피 범위를 우선하며 초기 리디자인 01~06 작업을 재설계하지 않았다.
- 이전 리디자인 캡처·로그는 보존했다. 이번 증거는 이 디렉터리에 분리했다.

## 01 조사 → 02 토큰 → 03 핵심 → 04 나머지 화면

| 적용 위치 | 조사·수정 |
|---|---|
| mediflow-tokens.css | 실제 로드되는 공통 @font-face와 세 family 역할 |
| guided-screening.css | 환자 scope, 제목·본문·질문·행동·주의문구·숫자·브랜드 |
| clinical-operations.css | 관리자 scope, 폼·표·보조 정보·섹션·제목 |
| 23 제품 템플릿 | body의 Pretendard/SF Pro/system 우선 선언을 공통 UI 토큰으로 연결. 무거운 800/900·음수 자간 및 고정된 작은 rem 보조 문구 정리 |
| survey.html | 기존 지역 typography !important를 제거하고 토큰 연결. 비타이포그래피 기존 선언 유지 |
| chat-widget.css | 결과 설명 위젯·입력·버튼 SUIT, 본문 1.6, 긴 제목 헤더 여유 |
| timeout.js | 기존 모달 inline typography만 scope 토큰 연결. 경고·연장·타이머·세션 정리 유지 |
| report_pdf.html | HTML/브라우저 인쇄 SUIT. 기존 인쇄 pt 크기·페이지 구조 유지 |
| 관리자 pre/code 출력 | 기존 고정폭 유지. 일반 폼·설명은 SUIT |
| test_i18n.html / templates_unfinished | 제품 shell에 포함되지 않는 개발 테스트/보관본. 변경하지 않음 |

전체 변경 파일: [CHANGED_FILES.txt](CHANGED_FILES.txt).
DOM·문구·URL·폼·의료 수치·분석·payload·auth/CSRF는 typography 선언을 제외한 비교로 확인했다.
이미지·벡터 로고와 기존 SVG 이미지 내부 문자, emoji glyph는 변경하지 않았다.

## 공식 폰트

공식 [SUIT](https://github.com/sun-typeface/SUIT)의 [v2.0.5](https://github.com/sun-typeface/SUIT/releases/tag/v2.0.5)
Variable WOFF2를 수정 없이 로컬 제공한다. 내부 name table 버전은 **2.040**이다.
라이선스는 **SIL OFL 1.1**, SUNN copyright / Reserved Font Name SUIT이며 LICENSE와 upstream CSS를 함께 보존했다.
자산 출처·SHA-256·등록 상세: [fonts/suit/README](../../../web/static/fonts/suit/README.md), [font-metadata.json](font-metadata.json).

등록 이름 `SUIT Variable`, normal, weight 100–900, `font-display: swap`.
공식 full 파일/CSS에는 unicode-range가 없으며 subset·재인코딩·추가 preload·외부 font CDN·가짜 굵기·전역 !important를 추가하지 않았다.
font-ui → SUIT Variable → 기존 시스템 대체 글꼴. font-display/font-numeric은 font-ui와 동일하다.
CDP의 `SUIT Variable Thin`은 원본 default-instance family 이름이다. 실제 Regular/Medium/SemiBold/Bold instance를 확인했다.

## 화면별 토큰 (px)

| 역할 | 환자 키오스크 | 환자 모바일 ≤900px | 관리자 |
|---|---:|---:|---:|
| body | 20 | 18 | 15 |
| lead | 22 | 18 | 기존 일반 설명 14~15 |
| action | 22 | 19 | 15 |
| title | clamp 32~40 | 28 | 28 |
| section | 24 | 22 | 20 (서비스 제어 18) |
| support | 18 | 16 | 14 |
| meta | 16 | 16 | 13 |
| body leading | 1.6 | 1.6 | 1.55 |
| title / control leading | 1.3 / 1.4 | 1.3 / 1.4 | 1.3 / 1.4 |

본문 400/500, 문진 label·선택·버튼 500/600, 환자 제목 600/700, 관리자 일반 400/500/600.
자간 0이 기본. PIN 숫자의 의도된 tracking과 영문 인쇄 kicker의 tracking은 지역 역할로 유지한다.
큰 버튼 토큰은 주요 행동에만 적용한다. 작은 아이콘·단계·인쇄 표에 동일 px 크기를 강제하지 않았다.
한글 문단은 keep-all + overflow-wrap:anywhere, 긴 이메일·URL·식별자는 줄바꿈 가능하다.
번역 문자열·문진 내용을 줄이거나 br를 추가하지 않았다.
입력/select single line 높이: 환자 **56px**, 관리자 **44px**. textarea·다중 select·checkbox/radio/range/file은 제외한다.

## 05 검증 결과

| 검증 | 결과·증거 |
|---|---|
| 실제 Chromium before/after | **41/41 PASS** 각 phase. [before](before-browser.json), [after](after-browser.json) |
| viewport | 1920×1080, 390×844, 1440×900, 1080×1920. 추가 200% 대응 960×540 CSS viewport + DPR2, 키보드 대응 390×420 |
| 화면·상태 | 시작·식별/동의·검사 선택·문진·촬영·분석 대기·결과·이력·관리자·연구·오류·모달·타임아웃·위젯·HTML 보고서·모바일 및 보관 중인 mobile templates |
| font network / FontFaceSet | 모든 after 페이지 로컬 WOFF2 HTTP200, loaded, 400/500/600/700 check. UI family 우선순위 검사 |
| 실제 Rendered Fonts | CDP CSS.getPlatformFontsForNode로 브랜드·제목·질문·버튼·select·위젯과 7개 표본 검사. 한글/영문/2026.10.07 모두 custom SUIT |
| controls / overflow | input-select 높이 검사, 수평 overflow 없음, 보이는 컨트롤 scrollHeight 잘림 없음. 긴 합성 문진과 submit focus/scroll 검사 |
| 기능 회귀 | **22/22 PASS** [regression-browser.json](regression-browser.json). 문진 exact payload, 동의·키보드, 촬영/업로드/합성 분석, not_configured, 이력, 인증/CSRF, provider 미준비, 연구 분리, 세션 종료, theme/6언어 |
| 템플릿 의미 보존 | **27/27 PASS** [semantics-audit.json](semantics-audit.json): 26 템플릿(공통 partial/개발 테스트 포함) + timeout.js 비교 |
| 기존 반응형 unit test | **5/5 PASS** [unittest.txt](unittest.txt) |
| diff whitespace | git diff --check PASS |

확대 검사는 1920×1080 화면의 브라우저 200%에 대응하는 CSS viewport/DPR 조건이다.
실제 OS 확대·모바일 가상 키보드 장치 실행을 했다는 의미는 아니다.
기존 회귀의 Apply 단계는 브라우저 interception으로만 응답하는 mock이다. 운영 Apply/모델 변경/서비스 제어를 호출하지 않았다.

캡처는 [captures](captures/)의 **42쌍**(41 상태 + 표본)이다.
[before-manifest](before-manifest.json), [after-manifest](after-manifest.json)에 commit·viewport·fixture·출처·SHA256을 기록했다.
폰트 로딩 후 동일 스크립트·합성 fixture·light theme·언어·viewport에서 촬영했다. 직접 시작/문진/촬영/분석/결과/모바일/관리자/보고서/모달 등 대표 PNG를 열어 검토했다.
실제 환자·사진은 없으며 fixture의 기하 도형과 `synthetic@example.invalid`, 고정 JSON만 사용했다.

## 다국어·그래픽·PDF 경계

- SUIT의 2,933 Unicode mappings는 모든 Unicode를 덮지 않는다. 요청된 한글·Latin·숫자 표본은 모두 포함한다.
  실제 일본어 제목은 Hiragino, 중국어 제목은 PingFang, 베트남어 일부는 SF fallback으로 렌더됨을 CDP로 확인했다.
  시스템 fallback은 기존 다국어 지원을 위한 것이며 새 서체를 배포하거나 문자열을 수정하지 않았다.
- 기존 SVG placeholder 이미지 내부 `No image data`와 emoji는 HTML 텍스트의 폰트 상속 대상이 아니다.
  기존 이미지 내부 서체까지 SUIT로 교체했다는 주장은 하지 않는다. 로고·기존 이미지 자산은 보존했다.
- HTML 보고서에서 SUIT 로딩과 브라우저 A4 PDF 생성을 확인했다. 임시 Chromium PDF의 FontName에
  SUIT Regular/SemiBold/Bold embedding이 존재한다: [browser-pdf-fonts.json](browser-pdf-fonts.json).
  시스템 미지원 glyph와 기존 SVG 문자 때문에 다른 font도 포함된다. PDF 자체는 /private/tmp의 합성 검증용이다.
- **서버 PDF NOT_RUN / SUIT 미적용**: database/app.py generate_pdf_report는 ReportLab Helvetica/Helvetica-Bold를 사용한다.
  이번 CSS 변경으로 해당 엔진에 SUIT가 적용되지 않는다. 서버 DB 경로를 실행하지 않았고 PDF 엔진 교체는 하지 않았다.
- **NEEDS_HARDWARE**: 실제 키오스크·세로형 장비·카메라·OS 확대·모바일 키보드·실장비 PDF 출력 품질.
- **NOT_RUN**: 운영 DB, 실제 의료 추론/환자, 외부 LLM, 카카오/메시지 발송, 운영 Apply, 모델 전환, 운영 서비스 재시작/배포.
  backend 전체 suite는 이번 typography 작업에서 다시 실행하지 않았다. 이전 VALIDATION의 dependency 오류를 새 PASS로 취급하지 않는다.
- 모바일 결과의 기존 floating 설명 버튼이 스크롤 중 이미지 선택 영역에 겹칠 수 있는 배치는 before에도 존재한다.
  이번 폰트 범위에서 shell을 재설계하지 않았다. 폼 완료 버튼은 기존 문서 flow/scroll로 접근 가능하다.

## 06 재현·rollback·커밋

```sh
python3 scripts/ui_preview.py --port 5097
# 별도 terminal; Playwright 설치 경로를 MEDIFLOW_PLAYWRIGHT_MODULE로 지정 가능
MEDIFLOW_CAPTURE_SHA=54cedc308a67b8a91517919870bc04bd22da16e1 node scripts/ui_typography.cjs after
MEDIFLOW_UI_VALIDATION_OUTPUT=docs/ui-redesign/typography/regression-browser.json node scripts/ui_validate.cjs
python3 scripts/ui_typography_audit.py --baseline 899affd
python3 -m unittest discover -s tests -p test_kiosk_responsive_templates.py
```

before는 `git archive 899affd`로 만든 별도 임시 source를 `ui_preview.py --source <source> --port 5098`로 제공하고,
MEDIFLOW_UI_BASE=http://127.0.0.1:5098, MEDIFLOW_CAPTURE_SHA=899affd의 전체 SHA로 `ui_typography.cjs before`를 실행한다.
운영 서버는 실행하지 않는다. 테스트 완료 후 자신이 실행한 두 preview terminal만 Ctrl-C로 종료했다.

원복은 사용자 작업트리 확인 후 **이 typography source만** `git revert 54cedc308a67b8a91517919870bc04bd22da16e1`한다.
증거·문서도 원복하려면 이 README를 포함한 evidence commit을 먼저 revert한다.
초기 리디자인·드롭다운 높이 커밋은 유지한다. DB/model/config·브라우저 저장값 migration이 없으므로 운영 원복 작업은 필요하지 않다.
로컬 커밋만 생성하며 push·PR·배포는 수행하지 않았다.
