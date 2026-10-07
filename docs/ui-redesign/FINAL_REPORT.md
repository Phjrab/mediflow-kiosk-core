# 최종 변경 보고서 · 2026-10-07

- 프로젝트: `Phjrab/mediflow-kiosk-core`
- Branch: `codex/ui-mediflow-guided-screening`
- Baseline: `bfab34c79381d1603a5ada1e8a96bee7babcc284`
- 구현 commit: `0c7fbf0f598ea65f952e8bd61dd61842cb8ef331`
- 캡처·검증·문서 commit: 이 보고서를 포함하는 branch HEAD. `git log -2 --oneline`으로 확인.
- 원격 push·PR·merge·배포 없음. 운영 설정·DB·모델·서비스 변경 없음.

## 완료한 01~06

1. 실제 router/DOM/API와 부작용을 조사하고 INVENTORY·PLAN·baseline/합성 before를 작성했다.
2. 단일 색 토큰·Guided Screening shell·시작/식별/선택을 적용했다.
3. ready capability 제한, 정확한 문진 payload, draft/back/중복 방지, 실제 관측에 기반한 촬영 안내를 구현했다.
4. 결과·이력·보고서·모바일과 Clinical Operations 설정/운영/Research를 정리했다.
5. 격리 suite 비교, 실제 Chromium 22 시나리오, 23 화면 렌더/JS, 동일 조건 9쌍 캡처와 PNG 시각 검토를 완료했다.
6. 기능표·검증·rollback·handoff·README, diff/비밀/데이터 점검과 feature branch 로컬 커밋을 완료했다.

## 바뀐 화면과 핵심 파일

| 범위 | 실제 변경 |
|---|---|
| 공통 | `web/static/css/mediflow-tokens.css`, `guided-screening.css`, `clinical-operations.css`; `_guided_header.html`, `_clinical_header.html`, `ui-shell.js` |
| 시작·선택·문진 | index/login/screening_select/screening_survey 및 legacy survey; start-screening.js, screening-flow.js, translations.js |
| 촬영 | capture/screening_capture/m_capture; 큰 영상·인접 안내, upload/USB 차이, permission/missing/stale, debug 정보는 관리자 관측 상세 |
| 결과 | result/screening_result/screening_summary/m_result; 연구 경계, 모델 점수 미제공, 재촬영·다음 검사·종료, 기존 Q&A widget 연결 |
| 이력·모바일·보고서 | report/report_pdf/m_report, m_login/m_dashboard, dormant m_index/m_login_start/m_survey; 빈 이미지·긴 문장·스크롤·확대 |
| 관리자 | admin_config/admin_ai_experiments; 설정/provider/운영 section, 관측 상태 목록, draft→plan diff→Apply, 서비스 제어 별도 영역, Research 비활성 이유·empty |
| 관측 backend | eye_server.py monotonic frame age/state 추가; utils/uvc_camera.py permission 오류 구별. 의료 inference/classifier/threshold 미변경 |
| 검증 | scripts/ui_preview.py, ui_capture.cjs, ui_validate.cjs; tests/test_ui_admin_auth_contract.py, test_ui_camera_observation.py, UVC mock 테스트 |

색은 warm white/teal, 환자 주요 버튼 56px와 단계 안내, 운영 UI는 navy와 조밀한 목록을 쓴다.
고정 높이와 문진 footer 가림을 없애고 작은 화면에서는 scroll·단일 열을 사용한다.
새 SPA/framework/제품 dependency는 추가하지 않았다. 타사 이름·로고·디자인 코드를 도입하지 않았다.

## 기능 보존과 제한

[INVENTORY](INVENTORY.md)에 기존 route·DOM·event·API→화면→검증을 매핑했다.
기존 template ID 누락 0. 식별·동의, payload key/enum, 모델 판정·threshold·보고서 계산,
인증·CSRF, provider 선택, 연구 VLM과 운영의 분리, 서비스 confirm/plan gates를 보존했다.
ready가 아닌 피부·두피는 선택·전체 검사에서 제외한다. 직접 촬영 구조는 남지만 분석 불가를
표시한다. 모델이 없는 상태에서 검사 성공·의료 결과를 생성하지 않는다.

기존 3분 idle + 30초 경고/연장은 유지한다. 문진 draft는 identity별 sessionStorage에만
저장하고 화면 종료 시 session과 기존 민감 local mirror를 정리한다. 언어/theme preference는
유지한다. 신규 장기 환자 저장을 추가하지 않았다.

원본 dormant m_index의 orphan script와 m_result의 번역이 측정 DOM을 지우던 오류도
실제 브라우저에서 발견해 수정했다. 이 template들에 새 운영 route를 만들지는 않았다.

## 검증 요약

- Chromium: 22/22 PASS, uncaught errors 없음, 외부 네트워크 차단.
- 전체 suite: 247개 중 244 PASS, 1 skip, 2 import errors. baseline은 242개 중 239 PASS,
  1 skip, 같은 2 import errors. `pytorch_grad_cam`·`qrcode` 누락으로 suite 전체는 FAIL.
- 실제 Jinja render/인라인 JS 23 화면, Jinja compile 26 template, Python/새 JS 문법 PASS.
- 관리자 mock Apply는 브라우저 intercept에서만 실행. 운영 Apply·restart·모델 변경 없음.
- synthetic report PDF는 Chromium에서 임시 출력. 실제 서버 PDF·QR 생성과 scan은 NOT_RUN.
- 실제 USB/현미경·모바일 장치 연결은 NEEDS_HARDWARE; 실제 inference·임상 평가는 NOT_RUN.

명령·exit code·acceptance 상태·환경 제한은 [VALIDATION](VALIDATION.md), 실행 출력은 `logs/`에 있다.
핵심 검증 실패를 baseline과 분리했으며 기존 assertion을 삭제하거나 전체 suite를 PASS로 쓰지 않았다.

## 캡처와 데이터 출처

[CAPTURE_MANIFEST](captures/CAPTURE_MANIFEST.csv)에 SHA·시각·viewport·route·fixture·live action을 남겼다.
Start, Selection, Survey, Capture, Result, Operations, Research, Mobile, History의 before/after 각 9개다.
실제 template을 실제 Chromium으로 촬영했으며 이미지 편집으로 결과를 바꾸지 않았다.
각 PNG에는 `UI DEMO / SYNTHETIC FIXTURE / 성능·임상·실장비 검증 아님` 표시가 있다.

사진은 Pillow로 만든 기하 도형, 결과는 결정론적 합성 JSON(73%는 성능 수치 아님),
identity는 `synthetic@example.invalid`, 운영 노드는 synthetic-node다. QR fixture는 도형 이미지이며
외부 공유 목적지가 없다. TemporaryDirectory SQLite 외 운영 DB를 쓰지 않는다.
실제 환자·비밀 키·운영 token·외부 대화·메시지 발송·외부 LLM을 사용하지 않았다.

## 실행과 인계

제품 실행 방식은 기존 Flask/Jinja를 유지한다. 안전한 UI 재현은:

```sh
python3 scripts/ui_preview.py --port 5097
```

별도 terminal에서 (Playwright가 기존 개발 환경에 있어야 함):

```sh
node scripts/ui_validate.cjs
node scripts/ui_capture.cjs after
```

Codex bundled module을 사용하면 `MEDIFLOW_PLAYWRIGHT_MODULE`에 해당 Playwright 경로를 지정한다.
before는 baseline archive를 별도 포트의 preview `--source`로 열고 `MEDIFLOW_UI_BASE`와
`MEDIFLOW_CAPTURE_SHA`를 baseline으로 지정한다. fixture는 운영 inference server가 아니다.

원복은 [ROLLBACK](ROLLBACK.md), 최종 이어가기 경계는 [HANDOFF](HANDOFF.md)에 있다.
운영 적용 전에 필요한 항목은 VALIDATION의 NOT_RUN/NEEDS_HARDWARE 표이며 이번 범위의
추가 구현 blocker는 없다. 의존성 누락과 실제 장치 검증은 해소됐다고 주장하지 않는다.
