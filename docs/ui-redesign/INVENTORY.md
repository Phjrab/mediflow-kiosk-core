# 기능 보존표 · 2026-10-07

대상 `Phjrab/mediflow-kiosk-core`, 시작 HEAD `bfab34c79381d1603a5ada1e8a96bee7babcc284`.
시작 작업 트리는 clean, branch `codex/ui-mediflow-guided-screening`.
저장소와 상위 디렉터리에서 적용되는 AGENTS.md는 발견되지 않았다.
요청의 팩은 저장소 루트에 없었으며 첨부 경로
`../prompt/dashboard-ui-redesign/mediflow-ui-prompt-pack/`의 START_HERE,
MASTER_PROMPT 및 01~06 파일을 읽었다. 사용자 요청의 범위와 안전 제한이 우선한다.
과거 PORTFOLIO와 Admin Control의 장비 SHA는 이 checkout이나 이번 검증 SHA가 아니다.

| 기존 기능 | 실제 route / template / DOM·event | 계약·상태 출처 | 새 화면 / 검증 |
|---|---|---|---|
| 시작·언어·theme | `/`, index; .btn-start, language-selector-fab, global-theme-toggle | url_for(login), 기존 localStorage preference | Guided Screening 시작; browser start, theme/language |
| 식별·동의 | `/login`, login; loginForm, identifier, privacy-consent, handleLogin | 식별 형식 검사 → 동의 → sessionStorage user_id/user_role; admin 분기 보존 | 식별·동의 단계; browser consent/validation |
| 모바일 PIN | `/m`, m_login; `/m/dashboard`, m_dashboard | generate_pin / mobile_connected / verify_pin; server mobile_verified | 모바일 연결; fixture adapter 및 route 계약 |
| 검사 선택 | `/screening`, screening_select; modality-grid, toggle-all, continue-button | GET /api/screening/config; ready / not_configured | 준비된 검사만 선택; browser capability + failure |
| 통합 조건부 문진 | `/screening/survey`, screening_survey; age, eye/skin/scalp-section, submit-button | screening_version/types, 기존 common+eye+skin+scalp payload → POST /api/survey | 선택 문진·오류·재시도; browser payload/duplicate/back |
| 기존 문진 | `/survey`, survey; 기존 입력 ID/name/핸들러 | 동일 survey endpoint, 조건부 fieldset | 같은 토큰·scroll; template DOM 계약 |
| USB UVC·업로드·자동셔터·줌 | `/capture`, capture; video-feed, status-message, btn-capture-photo, auto-shutter-toggle, zoom-slider | camera/session/start/stop, video_feed/frame, detect_status, analyze; 기존 threshold | 큰 preview+실제 관측 안내; browser camera missing/stale/upload |
| 미설정 피부·두피 구조 | screening/capture·result | server config, screening_capture_* session keys | 준비되지 않음 명시; 선택에서는 제외, 직접 경로는 capture-only 보존 |
| 분석·결과·Grad-CAM | `/result`, result; ai-normal/conj/uveitis/cataract/eyelid, btn-cam-toggle | bilateral_analysis·eye_analysis_L/R, model scores/redness; 기존 계산 | 연구용 결과·모델 점수 경계; synthetic/empty result |
| 다음 검사·통합 결과 | `/screening/summary`, screening_summary | ScreeningFlow completion/state, no_data/not_configured | 같은 flow 상태; summary browser |
| 이력·문진 이력·삭제 | `/report`, report; history/survey lists, user-display | GET/DELETE /api/history, /api/survey; 기존 user_id 접근제어 | 읽기 쉬운 목록·상세; synthetic history |
| PDF·QR·공유·카카오 | `/report/pdf`, `/report_pdf`, report_pdf; report의 기존 버튼·모달 | generate_report, report/share, database bridge /report /open /qr /kakao/send_report | 기존 endpoint 유지; fixture 공유만, 메시지 미발송 |
| provider Q&A | chat-widget.js/css | /api/chat/status, /api/chat; 명시적 provider 선택, no fallback | 준비되지 않은 이유; browser unavailable |
| 관리자 설정·인증·CSRF | `/admin/config`, admin_config; config-grid, llm-config-grid, status, saveConfig | /api/admin/login/config/logout; X-Admin-CSRF | Clinical Operations 설정·운영; existing auth tests + fixture 401/403 |
| Admin Control | admin_config; ai-control-panel, ai-save-draft, ai-plan, ai-apply | generation /overview /drafts /plans /operations; mutation/receipt/generation gates | 단계별 검토·plan diff·Apply 영역; mock plan and deny |
| 서비스 제어 | admin_config; requestServerControl | /api/admin/server/restart/shutdown + 기존 확인 | 위험 액션 별도 영역, 확인 보존; 호출 NOT_RUN |
| 연구 비교·ROI 등록 | `/admin/ai-experiments`, admin_ai_experiments; import-button, compare-button, jobs | capabilities/jobs/compare/samples-from-history; auth·CSRF·permission·retention | Research 경계·disabled 이유; browser capability/empty |
| 기존 모바일 템플릿 | m_index/login_start/survey/capture/result/report | 현재 eye_server에 이 6개 template의 production route가 없음; 활성 모바일은 공용 responsive routes와 PIN | dormant template도 스타일 정리·fixture inspection; 새 운영 route 주장 없음 |
| training·i18n 검사 | `/training`, `/training.html`; test_i18n는 개발 template | 현재 route·기존 handler | 도움·언어 설정 경로 보존 |
| 세션 종료·timeout | timeout.js; initializeMasterSession, screensaver-cancel | 기존 3분 + 30초 경고/연장, session clear | 유지·민감 local mirror도 종료 시 정리; browser teardown |

## 위험 액션과 격리

운영 Apply, 모델 변경, 서비스 restart/shutdown, 운영 설정 저장, 연구 job 생성/ROI import,
외부 LLM, 실제 메시지/카카오 연결, 실제 DB·사용자 이미지·QR 목적지를 이번 검증에 사용하지 않는다.
preview는 eye_server/config/database.app을 import하지 않는다. actual Jinja templates +
synthetic API adapters를 별도 loopback port에서 사용한다. 문진 fixture는 TemporaryDirectory
SQLite에만 쓴다. 브라우저는 외부 네트워크를 차단한다. 이는 운영 서버 E2E나 임상 검증이 아니다.

## 확인한 실행 지점

README의 기존 명령: `python -m unittest discover -s tests -v`, `python -m pytest -q`.
이 호스트에는 python alias/pytest/MediaPipe가 없다. `python3 -m unittest discover -s tests -v`를
운영 파일이 제외된 `git archive` 임시 checkout에서 실행한다. Playwright는 앱의 기존 bundled
runtime과 설치된 Chromium을 사용한다. 신규 제품 의존성을 설치하지 않는다.

`eye_server.py` import는 FaceMesh를 생성하고 request startup은 모델/DB를 초기화하므로 직접
운영 서버를 시작하지 않는다. UI fixture adapter는 이 부작용을 피해 template/API 계약을 검사한다.
실제 backend auth/CSRF·판정 회귀는 기존 AST/isolated unit tests로 별도 검증한다.
