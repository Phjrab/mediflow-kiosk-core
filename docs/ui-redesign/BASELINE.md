# Baseline · 01 완료

시작 HEAD `bfab34c79381d1603a5ada1e8a96bee7babcc284`. 기능 조사: INVENTORY.md.
9개 actual-template synthetic 화면을 Chromium으로 열어 before PNG를 생성했다.
viewport·route·fixture는 captures/CAPTURE_MANIFEST.csv에 기록했다.
대표 before-start/before-operations PNG를 직접 열어 기존 배치와 clipping을 확인했다.

기존 suite: 운영 파일 없는 `/private/tmp/mediflow-ui-baseline-bfab34c`에서
`python3 -m unittest discover -s tests -v`, exit 1. 242 tests, errors 2, skipped 1.
`test_classifier_offline_init`: pytorch_grad_cam 미설치, `test_database_app_environment`: qrcode 미설치.
로그: logs/baseline-unittest.txt. 별도 config/responsive 10 tests는 통과했다.
처음 사용한 python alias는 없음(exit 127), tests는 Python package가 아니므로
module-name 실행은 import 실패했으며 discover 명령으로 바로잡았다.

브라우저: scripts/ui_capture.cjs before, exit 0. 9개 화면 page/console error 0.
QR CDN 및 history의 기존 외부 script/font 요청은 차단 응답했고 외부 서비스에 접속하지 않았다.
로그: logs/before-browser.json. baseline admin 설정의 아래 영역은 고정 높이 내부 scroll이었다.
캡처는 실제 장비·성능·의료 판정 검증이 아니다.

격리 실행은 scripts/ui_preview.py. Flask의 실제 Jinja templates에 synthetic API adapters를 연결한다.
본 서버를 import/실행하지 않아 FaceMesh·모델·DB startup을 호출하지 않는다.
이 fixture의 인증은 합성 adapter이며 실제 인증 회귀는 기존 backend unit/AST tests로 확인한다.
