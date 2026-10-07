# UI·SUIT 운영 배포 완료 · 2026-10-07

사용자가 후속 메시지로 푸시와 운영 배포를 승인했다. 초기 UI/typography 검증의 운영 미실행 기록은 당시 사실로 유지한다.

## 소스·배포 이력

| 항목 | 결과 |
|---|---|
| 대상 | Phjrab/mediflow-kiosk-core, 기존 Jetson A |
| 운영 URL | http://192.168.50.10:5000/ |
| 소스 | `codex/ui-mediflow-guided-screening`, `625f1d468682bdb9f2590bd59ca56c5111147e93` 푸시 확인 |
| 운영 이전 | `codex/admin-control-a-deploy`, `69f9e52ffa5a18cb8425f09fa7920476c3e84232`, clean |
| 운영 적용 | `4b87d9e6a1a763a4117499f6cea34fb3453ae1c3`, 기존 운영 브랜치에 커밋·푸시 완료 |
| 복구 브랜치 | A의 `backup/ui-before-625f1d4-20261007` → `69f9e52` |
| 현재 웹 | 정확한 소유권을 확인한 웹 PID 856731 → 3506090. `/status` HTTP200/running, 기존 안구 모델 loaded 유지 |
| 변경 범위 | UI 39개 경로 + eye_server.py의 카메라 freshness 표시 + 기존 합성 테스트 1개, 총 41개 경로 |

SSH 설정의 이전 주소 192.168.0.26은 접속되지 않았다. 같은 프로젝트의 9월 28일 읽기 전용 캡처 기록에서
192.168.50.10을 찾고 hostname/user/architecture/project 경로/branch/SHA를 직접 확인했다.
기존 A backend는 로컬 UI baseline bfab34c와 동일했다. 전체 UI 패치는 `git apply --check`를 통과했고,
기존 운영 템플릿 DOM ID 누락은 0이었다. 기존 A 전용 코드와 운영 branch를 유지했다.
main 병합·다른 프로젝트·B 배포는 수행하지 않았다.

## 적용 전후 검증

- **PASS: 후보 Python 197/197**, A 기존 venv를 사용하되 프로젝트 밖 후보에 환경·운영 DB·실제 모델 가중치를 복사하지 않았다.
  TORCH_DEVICE=cpu와 합성 HASH_PEPPER를 사용했다. [unit-tests.txt](unit-tests.txt).
  처음 후보에서 누락된 기존 소스 모듈/runbook을 보완한 뒤 전체 suite가 통과했다. 운영 source 오류를 숨기거나 테스트를 제외하지 않았다.
- **PASS: 후보 Chromium 22/22**, Jetson loopback 합성 fixture + SSH tunnel.
  식별/동의, exact 문진 payload, 촬영/업로드 mock, 결과/이력 mock, provider 미준비, 연구 분리, auth/CSRF,
  not_configured, 다국어·viewport. Apply는 브라우저 interception의 mock만 사용했다. [candidate-browser.json](candidate-browser.json).
- **PASS: 실제 운영 공개 화면 4개 + auth/font asset 1개**, [live-smoke.json](live-smoke.json), [재현 probe](live-smoke.cjs).
  시작 1920×1080, 시작 모바일 390×844, 검사 선택, 빈 식별 화면을 새 익명 브라우저에서 GET으로만 확인했다.
  브랜드·한글 제목의 CDP Rendered Fonts와 FontFaceSet에서 local SUIT를 확인했다.
  WOFF2 HTTP200과 공식 파일 SHA256 `aa894a204d5a6fbae259dac6868d350cbd373a390caee0313f92946af741df23` 일치.
- **PASS: 실제 관리자 보호**, HTML은 익명 접근 시 **302 → /login**, API config/capabilities는 **403**.
  실제 서버의 기존 계약이다. 합성 fixture의 HTML/API 401과 구분한다. live admin 로그인이나 설정 저장은 하지 않았다.
- **PASS: 피부·두피 비활성**, 실제 /screening에서 not_configured 버튼 disabled를 확인했다.
- **PASS: 운영 보존**, `.env`, config.local.json, database/database.db의 배포 전후 및 live probe 이후 SHA256이 일치한다.
  파일 내용·실제 환자 기록을 검증 입력/캡처에 사용하지 않았다. 보존 해시는 로컬 기록에만 두고 이 공개 증거에서는 제외했다.
- **PASS: 서비스 범위**, 기존 웹 실행 환경을 메모리에서 보존하고 기존 manager의 소유권 검증·lock 하에서 웹 하나만 재시작했다.
  카카오 서비스는 계속 stopped, B controller/LLM/VLM/model selection·설정 변경·운영 Apply·외부 생성·발송 없음.
- **PASS: clean**, A 작업트리 clean이며 source/운영 branch의 원격 SHA도 확인했다.

실제 운영 PNG는 [시작](live-start.png), [모바일](live-mobile.png), [검사 선택](live-selection.png), [빈 식별](live-identity.png).
이는 실제 배포 응답이며 합성 fixture badge가 없는 것을 확인했다. 환자 식별자·동의·문진·사진을 입력하지 않았다.
수정 전후의 합성 42쌍과 scope 토큰/폰트 라이선스는 [typography 보고서](../typography/README.md)에 보존한다.

## 남은 범위

실제 환자를 이용한 검사·촬영·의료 성능·발송·provider 생성·운영 Apply·연구 job·모델 전환은 하지 않았다.
카메라는 현재 연결되지 않은 상태이며, 실제 장비 카메라/키보드/OS 확대 검증 완료를 주장하지 않는다.
서버 ReportLab PDF는 기존 Helvetica 경로를 유지한다. 웹 SUIT 배포로 서버 PDF까지 바뀌었다는 주장은 하지 않는다.
기존 모바일 floating theme/language/chat 배치의 겹침 한계는 typography 보고서에 기록한 대로 유지한다.
이번에 만든 후보 fixture와 SSH 터널만 종료했다. 운영 웹은 실행 상태로 유지했다.

## 원복

현재 사용자 변경을 확인하고, A의 기존 운영 branch에서 이번 source commit만 되돌린다.

```sh
git revert 4b87d9e6a1a763a4117499f6cea34fb3453ae1c3
```

그 다음 **새로 확인한** 웹 PID/boot/start-tick/UID/argv/cwd와 manager 소유권을 검증하고,
현재 웹 환경을 보존한 상태에서 기존 manager의 **eye_server spec 하나만** 재시작한다.
기본 `mediflow-kiosk restart`는 카카오까지 시작하므로 이번 배포 원복에 그대로 사용하지 않는다.
이번 one-window cutover 스크립트의 과거 PID/SHA를 재사용하지 않는다.
DB·환경·모델 원복이나 reset/clean/force push는 필요하지 않다.
원복 smoke는 공개 페이지·SUIT/static 파일·/status와 익명 관리자 거부만 검사하고 실제 환자/분석/발송은 사용하지 않는다.
