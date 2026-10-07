# 검증 결과 · 2026-10-07

대상 `Phjrab/mediflow-kiosk-core`, baseline `bfab34c79381d1603a5ada1e8a96bee7babcc284`.
구현 source revision과 최종 캡처 SHA는 FINAL_REPORT와 capture manifest에 기록한다.
검증은 운영 파일 없는 임시 checkout과 loopback 합성 fixture에서 수행했다.
이는 운영 서버 E2E, 의료 정확도, 실제 장치 검증이 아니다.

## 명령과 결과

| 검사 | 작업 위치·명령 | 결과·증거 |
|---|---|---|
| 기존 baseline suite | `/private/tmp/mediflow-ui-baseline-bfab34c`, `python3 -m unittest discover -s tests -v` | exit 1: 242개 중 239 PASS, 1 skip, 2 import errors; [로그](logs/baseline-unittest.txt) |
| 최종 suite | `/private/tmp/mediflow-ui-final-isolated`, 같은 명령 | exit 1: 247개 중 244 PASS, 1 skip, 같은 2 import errors; [로그](logs/final-unittest.txt) |
| 실제 Chromium interaction | 저장소 root, `MEDIFLOW_PLAYWRIGHT_MODULE=<bundled playwright path> node scripts/ui_validate.cjs` | 22 시나리오 PASS, exit 0; [JSON](logs/validation-browser.json), [실행 로그](logs/browser-run.txt) |
| 실제 template render·JS | `scripts.ui_preview.create_app().test_client()` + 각 인라인 script의 `node --check` | 23 화면 렌더·인라인 JS PASS; [로그](logs/template-render.json) |
| Jinja compile | `Environment(FileSystemLoader('web/templates')).get_template(...)` | 26 template PASS; [로그](logs/template-compile.json) |
| Python·JS 문법 | `python3 -m py_compile eye_server.py scripts/ui_preview.py utils/uvc_camera.py`, `node --check` 새 JS/scripts | PASS, exit 0 |
| 기존 DOM ID | baseline template vs 변경 template 비교 | 기존 ID 누락 0; [표](logs/dom-contract.json) |
| diff·비밀/데이터 점검 | `git diff --check`, 변경 text 패턴/경로·크기 검사 | PASS; [감사](logs/change-audit.json) |
| 동일 조건 before/after | `node scripts/ui_capture.cjs before` / `after` | 각 9 PNG; [manifest](captures/CAPTURE_MANIFEST.csv), [before](logs/before-browser.json), [after](logs/after-browser.json) |

전체 unittest suite는 **FAIL / 환경 의존성**이다. `pytorch_grad_cam`, `qrcode`가 없어
두 test module이 import되지 않는다. 동일한 실패를 baseline에서도 확인했으므로 새 회귀로
분류하지 않는다. 나머지 기존 assertion을 삭제하지 않았다. 새 5개 테스트도 통과했다. 최종 모바일 mesh=0 수정은 `MEDIFLOW_UI_TEST_FILTER='remaining active routes'`로 해당 시나리오만 재확인했다([추가 로그](logs/remaining-browser.json)); 최종 JSON은 이 확인 결과를 해당 행에 반영한다.
최초 sandbox 실행의 loopback bind 거부는 개발 실행 권한으로 재실행해 해결했다.
`pytest`는 이 환경에 없어 실행하지 않았다. 무거운 모델·의존성을 설치하지 않았다.

## 브라우저 시나리오와 보존 계약

| 항목 | 판정 | 근거 |
|---|---|---|
| 식별·동의 순서, modal keyboard focus | PASS | identity / consent; 동일 식별 handler·동의 DOM |
| ready만 선택·부분 전체선택, 피부·두피 disabled | PASS | capability / all; 미설정 direct path는 분석 불가를 유지 |
| 서버 오류와 stale capability cache | PASS | 503 fixture, 기존 ready cache가 있어도 진행 disabled, retry |
| 조건부 문진·payload·back·중복 submit | PASS | 정확한 common + eye/skin/scalp key, 선택된 eye payload, session draft, 1 POST |
| camera missing / permission / stale / reconnect | PASS (mock) | detect_status 관측 fixture, button 상태·문구 검사 |
| 느린 polling / route 전환 | PASS | 650ms 응답에도 동시 요청 최대 1, 전환 후 새 poll 없음 |
| invalid upload·합성 analyze·result | PASS (mock) | 생성한 PNG, 결과 73% 모델 점수, 잘못된 파일 거절 |
| 모바일 upload-only / PIN / dashboard | PASS (mock) | iPhone UA, 390×844, UVC 시작·poll 없음, 실패 PIN·합성 PIN 검증 |
| 결과 empty·종료·민감 임시 정보 정리 | PASS | empty를 분석 데이터 없음으로 표시, session 및 기존 local mirror 제거, theme 유지 |
| provider unavailable / no fallback | PASS (mock + 기존 suite) | input/send disabled, `/api/chat` POST 없음; provider routing source 미변경 |
| 이력·PDF·공유 | PASS (fixture) | 합성 history 73.0%, `send_kakao:false`, 실제 report_pdf HTML을 Chromium PDF로 임시 출력 |
| 관리자 auth·CSRF | PASS | fixture 401/403 + 원본 backend AST 함수 테스트의 미인증 403, CSRF missing/mismatch/valid |
| draft→plan→deny→mock Apply | PASS (mock) | diff·blocking_reasons 표시, 기본 Apply disabled, confirm 전 요청 0, 브라우저 intercept에만 1 POST |
| 연구 capability / empty / 운영 분리 | PASS | ROI/compare disabled, Research 표시, 운영 판정/기록 endpoint source 미변경 |
| 나머지 활성 화면·dormant 모바일 | PASS | legacy survey/training, screening capture/result/summary, 6 dormant templates 실제 render/JS |
| viewport / 긴 문진 / focus | PASS | 1920×1080, 1366×768, 1024×768, 390×844; 683×384 확대 등가·390×420 키보드 등가; horizontal overflow 없음 |
| 2배 확대·언어·dark | PASS | CSS zoom=2 실제 browser + 6 기존 언어 ko/en/zh/vi/ru/ja, preference와 stepper 유지 |
| 주요 palette 대비·touch | PASS (부분) | primary/text/muted/dark 조합 ≥4.5:1, 주요 버튼 ≥56px; 전체 legacy inline palette의 자동 접근성 인증은 아님 |
| before/after 직접 시각 확인 | PASS | 원본 PNG와 검토용 contact sheet로 확인; 가림/빈 이미지/상태 덮임/overflow 수정 후 재캡처 |

새 shell heading은 6개 dictionary를 사용한다. 기존 한국어 전용 통합 문진의 전체 문구를
새로 6개 언어로 번역했다는 뜻은 아니다. 키보드 검사는 실제 OS 소프트 키보드를 띄운 것이
아니며 줄어든 viewport로 검사했다. 확대 검사는 CSS zoom 및 viewport 등가이며 브라우저
메뉴의 확대 단축키·보조공학 인증까지 검증한 것은 아니다.

## 미실행과 실제 장치 확인

| 항목 | 판정 | 이유 |
|---|---|---|
| USB UVC / 현미경 / 실제 프레임·권한·재연결 | NEEDS_HARDWARE | 합성 응답과 mock unit만 사용 |
| 안구 실제 inference / Grad-CAM / 의료 정확도 | NOT_RUN | 환자 데이터·모델 실행 금지, missing dependency도 있음 |
| 실제 서버 PDF·QR 생성과 QR scan | NOT_RUN | backend `qrcode` 없음; fixture QR URL은 생성한 도형 PNG이며 스캔 가능한 QR이라고 주장하지 않음 |
| 운영 Apply·모델 변경·restart/shutdown | NOT_RUN | 사용자 제한; 브라우저 mock Apply는 운영 요청을 수신하지 않음 |
| 외부 LLM·카카오·메시지 발송 | NOT_RUN | 모든 원격 browser 요청 차단; 카카오 true 경로 사용 안 함 |
| 실제 운영 DB·공유 접근 E2E | NOT_RUN | 원본 auth/access code 보존, fixture store와 기존 isolated tests만 사용 |
| 실제 mobile OS camera·PIN/QR 장치 연동 | NEEDS_HARDWARE | 합성 PIN과 UA, 실제 기기 미사용 |

## 격리와 재현

`scripts/ui_preview.py`는 `eye_server`, deployment config, database.app을 import하지 않는다.
TemporaryDirectory SQLite는 합성 문진 payload만 저장하며 모델/외부 API는 없다.
preview label은 adapter가 삽입하므로 운영 template에는 나타나지 않는다.
위험·미구현 fixture 쓰기는 기본 403이다. mock Apply는 Playwright route.fulfill 내부에서
완료되고 preview에도 전달되지 않는다. baseline/current 모두 같은 fixture adapter를 사용했다.

재현: 제품의 기존 개발 의존성이 있는 환경에서 별도 terminal에
`python3 scripts/ui_preview.py --port 5097`을 실행하고 `node scripts/ui_validate.cjs`를 실행한다.
Playwright가 일반 Node 경로에 없으면 `MEDIFLOW_PLAYWRIGHT_MODULE`을 지정한다.
현재 사용한 경로는 Codex bundled runtime의 `dependencies/node/node_modules/playwright`였다.
브라우저 PDF는 `/private/tmp/mediflow-ui-synthetic-browser.pdf`에 생성하며 저장소 산출물이 아니다. 이번 검증 후 임시 checkout/PDF/검토용 contact sheet와 두 preview 서버를 정리했다.
운영 서버를 실행하는 명령으로 이 fixture 검증을 대체하지 않는다.

## 팩 인수 기준 판정

| 기준 | 판정 | 증거·범위 |
|---|---|---|
| 환자 안내형 / 관리자 shell·권한 분리 | PASS | 두 header/CSS, 관리자 auth 시나리오, after Start/Operations/Research |
| 식별·동의·조건부 문진·검증·이력 보존 | PASS | INVENTORY, payload/consent/history 시나리오; 실제 DB E2E는 NOT_RUN |
| 미설정 모델·전체 검사 제한 | PASS | capability/all/error/direct path 시나리오, after Selection |
| 의료 판정·수치·경계 | PASS (source/UI) | classifier/threshold 미변경, 기존 측정 threshold 유지, 연구 경계; 임상 검증은 NOT_RUN |
| provider / 연구 VLM 운영 분리 | PASS | provider unavailable/research 시나리오, 기존 routing/isolated suite |
| 실제 데이터·DB·공유 목적지·외부 API 미사용 | PASS | preview/capture/validate 네트워크 정책, 합성 이미지·JSON·manifest |
| checkout·지침·baseline 확인 | PASS | INVENTORY, BASELINE, baseline 로그 |
| 기존 기능에 접근 경로 유지 | PASS (source + fixture) | INVENTORY, ID 누락 0; 위험 운영 액션은 NOT_RUN |
| 실제 앱 구현 | PASS | 구현 source commit, 실제 Jinja/browser/captures |
| 핵심 loading/empty/error/stale/disabled | PASS | browser 상태 시나리오·화면·대응 코드 |
| 키보드·focus·대비·긴 텍스트·모바일·확대 | PASS (명시 범위) | 위 viewport/theme/focus 표; 전체 접근성 인증·실제 OS 키보드는 미검증 |
| 결과와 미실행/장비 한계 구분 | PASS | suite 전체 FAIL, NOT_RUN/NEEDS_HARDWARE 별도 표 |
| 실제 PNG 확인·출처 | PASS | 18 PNG, 동일 fixture/viewport/route manifest, 직접 이미지 검토 |
| 비밀·데이터·운영 프로세스 보호 | PASS | change-audit, 원본 DB/설정 diff 없음, 생성한 preview만 종료 |
| 코드·테스트·문서·rollback·local commit | PASS | FINAL_REPORT/ROLLBACK/HANDOFF, branch의 두 로컬 커밋 |
| 요청하지 않은 원격 작업 없음 | PASS | push/PR/merge/release/deploy 미실행 |
