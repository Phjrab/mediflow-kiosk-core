# Datasets 모델 통합 작업 기록

## 2026-09-29 P0

- 기존 `mediflow-kiosk-core`의 다른 미커밋 UI 작업이 `26faa17`로 정리된 것을 확인하고, 별도 작업 브랜치를 그 커밋으로 fast-forward 했다. 원본 체크아웃의 파일은 수정하지 않았다.
- datasets 원본은 `ffd71eca68ff1e21c145ed56158f4cfa77f7f037` 분리 worktree에 고정했다. 기존 로컬 복사본은 sparse checkout이었으므로 원본의 `src`, `data_examples`를 추가 확보했다.
- macOS arm64, Python 3.13.2, TensorFlow 미설치, Jetson/카메라 미제공 환경이다. 운영 DB와 서비스는 아직 실행하거나 변경하지 않았다.
- 세 모델 파일의 SHA-256은 팩과 일치한다. 실제 forward는 P1에서 실행한다.

## 2026-09-29 실행 위치 변경

- 사용자가 구현·검증을 Mac 대신 원격 Jetson에서 진행하도록 변경했다. 그 직전에 시작한 Mac TensorFlow 2.20.0/Keras 3.13.2 기준 추론은 고정 원본 `ffd71ec`과 6개 샘플로 완료했다. 결과는 ignored `runtime/datasets-integration/20260929-local-01/reference/baseline/`에 있다. 이는 Jetson 실행 증거가 아니다.
- 기존 SSH 별칭 `jetson_orin_nano`에 BatchMode, 5초 timeout으로 읽기 전용 접속을 시도했으나 시간 초과됐다. 장비 파일/서비스/DB는 변경하지 않았다.
- 원격 접속 가능 경로를 받은 뒤 장비에서 환경 및 운영 범위를 먼저 확인해야 한다. 이 Mac 작업 브랜치에는 아직 기능 구현이 없다.
