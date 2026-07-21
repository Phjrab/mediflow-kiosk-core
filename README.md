# AI 안구 건강 스크리닝 키오스크

Jetson Orin Nano와 Raspberry Pi 5를 지원하는 엣지 AI 기반 안구 건강 스크리닝 프로젝트입니다. 카메라 또는 업로드 이미지에서 양안을 추출하고 질환 분류, 충혈도 분석, Grad-CAM 시각화, 문진, 사용자별 이력, PDF 보고서와 카카오톡 공유를 하나의 웹 UI에서 제공합니다.

> 이 시스템은 의료 진단을 확정하는 장비가 아니라 안구 건강 이상 징후를 선별하는 보조 도구입니다. 최종 판단은 안과 전문의 진료를 통해 확인해야 합니다.

## 현재 구현 기준

이 문서는 2026-07-21의 프로젝트 파일을 기준으로 작성되었습니다.

- 운영 웹 서버: `eye_server.py` (기본 포트 `5000`)
- 카카오 OAuth·PDF 브리지: `database/app.py` (기본 포트 `5001`)
- 통합 실행·종료: `start_services.sh`, `stop_services.sh`
- 운영 DB: `database/database.db`
- 스키마 단일 원본: `database/schema.sql`
- Jetson 추론: MediaPipe Face Mesh + PyTorch EfficientNet-B0 + Grad-CAM
- RPi 추론: ONNX Runtime 기반 호환 백엔드

`server.py`는 `/health`, `/predict`만 제공하는 경량 추론 API입니다. 키오스크 전체 기능의 기본 실행 파일은 `eye_server.py`입니다.

## 주요 기능

- 실시간 카메라 스트림과 눈 정렬 상태 표시
- 좌안·우안 순차 촬영 및 자동 촬영 상태 관리
- MediaPipe Face Mesh 기반 양안 검출과 224x224 정방형 크롭
- EfficientNet-B0 기반 5개 클래스 분류
  - 결막염
  - 다래끼
  - 백내장
  - 정상
  - 포도막염
- 예측 클래스의 Grad-CAM 히트맵 생성
- 충혈도 등 픽셀 지표 분석
- 사용자별 진단·문진 이력 저장, 조회, 삭제
- 모바일 접속용 4자리 PIN과 모바일 전용 화면
- 한국어·영어·중국어·베트남어 UI와 보고서 템플릿
- OpenAI 또는 Gemini 기반 진단 결과 질의응답
- PDF 보고서 생성, QR 코드, 카카오 OAuth 및 나에게 보내기
- 관리자 로그인, 런타임 설정 변경, 재시작·종료 기능

## 시스템 구성

```text
카메라/업로드 이미지
        |
        v
MediaPipe Face Mesh -> 좌안/우안 크롭
        |
        v
EfficientNet-B0 -> 질환 분류 + Grad-CAM
        |
        +-> 픽셀 분석/문진/AI 가이드
        |
        v
Flask eye_server.py :5000
        |
        +-> SQLite database/database.db
        +-> web/static/captures/users/<user_hash>/
        +-> PDF/카카오 브리지 database/app.py :5001
```

## 빠른 실행

### 1. 가상환경 준비

`start_services.sh`는 프로젝트의 `venv`를 먼저 찾고, 없으면 `.venv`를 사용합니다.

```bash
cd ~/project/eye_project
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

### 2. 의존성 설치

전체 웹 애플리케이션 기준:

```bash
pip install -r requirements.txt
```

Jetson에서는 NVIDIA JetPack 버전에 맞는 PyTorch·torchvision wheel을 우선 사용해야 합니다. 플랫폼별 참고 목록은 `requirements_jetson.txt`, `requirements_rpi.txt`에 있습니다.

### 3. 환경 파일 설정

```bash
cp .env.example .env
```

최소한 다음 값을 `.env`에 설정합니다.

```dotenv
MODEL_DEVICE=jetson
SERVER_HOST=0.0.0.0
SERVER_PORT=5000
HASH_PEPPER=replace-with-a-long-random-secret
EYE_APP_SECRET_KEY=replace-with-another-long-random-secret
ADMIN_LOGIN_PASSWORD=replace-with-an-admin-password
```

- `HASH_PEPPER`를 변경하면 같은 사용자 식별자의 해시가 달라지므로 운영 시작 후에는 유지해야 합니다.
- `EYE_APP_SECRET_KEY`는 Flask 관리자 세션 서명에 사용됩니다.
- 비밀값이 들어 있는 `.env`와 `config.local.json`은 Git에 커밋하지 않습니다.

### 4. 서비스 시작

```bash
./start_services.sh
```

스크립트가 수행하는 작업:

1. Jetson/RPi 플랫폼 및 `venv`/`.venv` 자동 감지
2. `database/database.db` 초기화
3. `database/history.db`의 레거시 기록을 중복 없이 마이그레이션
4. `eye_server.py`와 `database/app.py` 실행
5. `/status`와 카카오 로그인 엔드포인트 확인
6. Epiphany 브라우저를 키오스크 화면으로 실행

기본 접속 주소:

- 키오스크: `http://<device-ip>:5000/`
- 상태 확인: `http://<device-ip>:5000/status`
- 카카오 브리지 상태: `http://<device-ip>:5001/health`

기존 브라우저를 닫지 않고 서버만 재실행하려면:

```bash
CLOSE_EXISTING_BROWSERS=0 ./start_services.sh
```

서비스 종료:

```bash
./stop_services.sh
```

로그 파일:

- `logs/server.log`
- `logs/kakao_app.log`
- `logs/browser.log`

## Jetson과 RPi 실행 경로

### Jetson Orin Nano

```dotenv
MODEL_DEVICE=jetson
```

- `inference/jetson_backend.py`를 사용합니다.
- 현재 `config.py`는 메모리 사용을 줄이기 위해 EfficientNet 추론 장치를 CPU로 지정합니다.
- 눈 검출은 `modules/detector.py`의 MediaPipe Face Mesh를 사용합니다.
- `models/Augmented_EffNet_V1_B0_best.pth`가 분류 가중치입니다.
- `models/set_1000_YOLO26s_best.pt`는 레거시·ONNX 변환 경로에 남아 있으며 현재 Jetson 눈 검출에는 사용되지 않습니다.

### Raspberry Pi 5

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements_rpi.txt
```

```dotenv
MODEL_DEVICE=rpi
MEDIAPIPE_ONNX_PATH=models/yolo.onnx
CLASSIFIER_ONNX_PATH=models/efficientnet.onnx
```

모델 준비와 점검:

```bash
bash scripts/export_onnx_rpi.sh
bash scripts/rpi_preflight.sh
```

`start_services.sh`에는 RPi 브라우저 분기가 포함되어 있지만, 현재 RPi 의존성과 런북에서 검증 대상으로 삼는 경로는 경량 추론 API입니다. RPi에서 전체 `eye_server.py` 키오스크를 사용하려면 PyTorch·MediaPipe를 포함한 추가 의존성과 카메라 흐름을 장비에서 별도로 검증해야 합니다.

```bash
python server.py --device rpi
curl http://127.0.0.1:5000/health
```

현재 RPi 호환 백엔드는 ONNX 분류를 우선하며, 검출기 출력 파싱은 export 형식에 맞춘 추가 검증이 필요합니다. 세부 절차는 `docs/RPI5_UBUNTU_RUNBOOK.md`를 참고하십시오.

## 환경 변수

### 서버·보안

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `SERVER_HOST` | `0.0.0.0` | Flask 바인딩 주소 |
| `SERVER_PORT` | `5000` | 키오스크 서버 포트 |
| `DEBUG_MODE` | `0` | Flask 디버그 모드 |
| `HASH_PEPPER` | 없음 | 사용자 식별자 해시용 필수 비밀값 |
| `EYE_APP_SECRET_KEY` | 없음 | Flask 세션 서명 키 |
| `SESSION_COOKIE_SECURE` | `0` | HTTPS 운영 시 `1` 권장 |
| `EYE_DATABASE_PATH` | `database/database.db` | 운영 DB 경로 재정의 |
| `EXTERNAL_BASE_URL` | 자동 감지 | 외부에서 접근할 보고서 기준 URL |

### 카메라·추론

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `MODEL_DEVICE` | `jetson` | `jetson` 또는 `rpi` |
| `CAMERA_DEVICE_INDEX` | `0` | OpenCV 카메라 인덱스 |
| `CLASSIFIER_CONFIDENCE_THRESHOLD` | `0.7` | 분류 신뢰도 임계값 |
| `IRIS_REMOVAL_ENABLED` | `1` | 홍채 영역 제거 사용 여부 |
| `IRIS_THRESHOLD` | `0.3` | 홍채 제거 임계값 |
| `AUTO_DIST_THRESHOLD` | `30` | 자동 촬영 중심 거리 임계값 |
| `AUTO_SCALE_MIN` | `0.8` | 자동 촬영 최소 눈 크기 비율 |
| `AUTO_SCALE_MAX` | `1.1` | 자동 촬영 최대 눈 크기 비율 |
| `AUTO_CAPTURE_HOLD_FRAMES` | `10` | 촬영 조건 유지 프레임 수 |
| `MEDIAPIPE_ONNX_PATH` | `models/yolo.onnx` | RPi 검출 ONNX 경로 |
| `CLASSIFIER_ONNX_PATH` | `models/efficientnet.onnx` | RPi 분류 ONNX 경로 |

`MEDIAPIPE_CONF_THRESHOLD`, `MEDIAPIPE_IOU_THRESHOLD`, `MEDIAPIPE_INPUT_SIZE`, `MEDIAPIPE_STATUS_CONF_THRESHOLD`는 기존 설정 키 호환을 위해 유지됩니다. 현재 Jetson MediaPipe Face Mesh 검출기는 이 YOLO 임계값 일부를 직접 사용하지 않습니다.

### 관리자·LLM

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `ADMIN_LOGIN_NAME` | `admin` | 관리자 로그인 이름 |
| `ADMIN_LOGIN_PASSWORD` | 없음 | 관리자 로그인 비밀번호 |
| `ADMIN_LOGIN_MAX_ATTEMPTS` | `5` | 제한 시간 내 최대 실패 횟수 |
| `LLM_PROVIDER` | `openai` | `openai` 또는 `gemini` |
| `OPENAI_API_KEY` | 없음 | OpenAI 채팅 API 키 |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI 모델 이름 |
| `GEMINI_API_KEY` | 없음 | Gemini API 키 |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini 모델 이름 |

### 카카오 브리지

`database/app.py`는 환경 변수 또는 로컬 전용 `config.local.json`에서 다음 값을 읽습니다.

- `KAKAO_CLIENT_ID`
- `KAKAO_CLIENT_SECRET`
- `KAKAO_REDIRECT_URI`
- `KAKAO_REFRESH_TOKEN`
- `KAKAO_ACCESS_TOKEN` (키오스크 보고서 공유의 선택적 폴백)
- `KAKAO_APP_HOST` (기본 `0.0.0.0`)
- `KAKAO_APP_PORT` (기본 `5001`)
- `KAKAO_OAUTH_STATE_TTL_SECONDS` (기본 `600`)
- `KAKAO_BRIDGE_URL` (키오스크에서 브리지에 접근할 주소)

## 웹 페이지와 API

### 주요 페이지

| 경로 | 용도 |
| --- | --- |
| `/` | 키오스크 메인 |
| `/login` | 사용자·관리자 로그인 |
| `/capture` | 양안 촬영 |
| `/result` | 진단 결과 |
| `/report` | 사용자별 이력과 보고서 |
| `/report/pdf`, `/report_pdf` | PDF 보고서 화면 |
| `/survey` | 문진 |
| `/training` | 안내·훈련 화면 |
| `/m`, `/m/dashboard` | 모바일 접속 및 대시보드 |
| `/admin/config` | 관리자 설정 |

### 키오스크 API

- 상태·카메라: `GET /status`, `GET /video_feed`, `GET /video_frame`, `GET /detect_status`
- 카메라 세션: `POST /camera/session/start`, `POST /camera/session/stop`
- 진단: `POST /analyze`, `POST /diagnose`
- 촬영 상태: `GET /capture/state`, `POST /capture/reset`
- 진단 이력: `GET /api/history`, `DELETE /api/history/<history_id>`
- 문진: `POST /api/survey`, `GET /api/survey`, `DELETE /api/survey/<survey_id>`
- 모바일 PIN: `POST /api/generate_pin`, `GET /api/pin_status`, `POST /api/mobile_connected`, `POST /api/verify_pin`
- AI 기능: `POST /api/chat`, `POST /api/generate_report`
- 보고서: `POST /api/report/share`, `GET /api/report/dependencies`
- 관리자: `POST /api/admin/login`, `GET|POST /api/admin/config`, `POST /api/admin/logout`
- 운영 제어: `GET /api/admin/fallback_stats`, `POST /api/admin/server/restart`, `POST /api/admin/server/shutdown`

### 카카오·PDF 브리지 API

- `GET /health`
- `GET /kakao/login`
- `GET /kakao/callback`
- `POST /kakao/send_report`
- `POST /diagnosis`
- `GET /history`
- `GET /report/<session_id>`
- `GET /open/<session_id>`
- `GET /qr/<session_id>`

## 데이터 저장 구조

운영 데이터는 `database/database.db` 하나를 사용합니다. 런타임 코드는 테이블을 직접 만들지 않고 `database/schema.sql`을 읽어 초기화합니다.

| 테이블 | 역할 |
| --- | --- |
| `users` | 해시 사용자 식별자, 표시명, 카카오 토큰 정보 |
| `diagnosis_sessions` | AI 판독, 픽셀 지표, 문진, FHIR, 소견과 상태 |
| `session_assets` | 원본 이미지, PDF 등 진단 세션 파일 자산 |
| `survey_responses` | 사용자별 독립 문진 기록 |
| `event_logs` | 진단·PDF·카카오 전송 이벤트 |
| `migration_records` | 레거시 데이터의 중복 이전 방지 |

저장 위치:

- 운영 DB: `database/database.db`
- 레거시 마이그레이션 원본: `database/history.db`
- 촬영 이미지: `web/static/captures/users/<user_hash>/`
- 웹 보고서: `web/static/reports/`
- 카카오 브리지 보고서: `reports/`
- DB 백업: `database/backups/` (Git 제외)

서비스 시작 시 `database/history.db`의 `diagnosis_history`, `survey_history`를 읽어 통합 스키마로 이전합니다. `migration_records`를 사용하므로 같은 원본을 다시 실행해도 중복 생성되지 않습니다.

## 데이터 마이그레이션과 백필

레거시 DB 이전은 `start_services.sh`가 자동 실행합니다. 수동 실행이 필요한 경우:

```bash
source venv/bin/activate
python -c "from dotenv import load_dotenv; load_dotenv(); from database.db import migrate_legacy_history; print(migrate_legacy_history('database/history.db'))"
```

기존 진단 JSON에 AI 가이드 필드를 보강하려면:

```bash
python database/backfill_guides.py --db database/database.db --dry-run
python database/backfill_guides.py --db database/database.db
```

운영 DB를 변경하기 전에 `database/database.db`와 `database/history.db`를 별도 백업하십시오.

## 테스트와 운영 점검

```bash
source venv/bin/activate
python -m unittest discover -s tests -v
python -m py_compile eye_server.py database/db.py database/app.py
curl http://127.0.0.1:5000/status
curl http://127.0.0.1:5001/health
```

SQLite 무결성 점검:

```bash
sqlite3 database/database.db 'PRAGMA integrity_check;'
sqlite3 database/database.db 'PRAGMA foreign_key_check;'
```

`/status`의 `camera_connected`가 `false`이면 서버와 모델이 정상이어도 카메라 프레임이 들어오지 않은 상태입니다. 카메라 장치 인덱스와 권한을 확인하십시오.

## 프로젝트 구조

```text
eye_project/
├── eye_server.py                 # 전체 키오스크 Flask 서버
├── server.py                     # 경량 /health, /predict API
├── config.py                     # 카메라·모델·임계값 설정
├── model_loader.py               # Jetson/RPi 백엔드 팩토리
├── start_services.sh             # 통합 시작 스크립트
├── stop_services.sh              # 통합 종료 스크립트
├── requirements*.txt
├── database/
│   ├── app.py                    # 카카오 OAuth·PDF 브리지
│   ├── app3.py                   # 대체/실험 브리지 구현
│   ├── db.py                     # 통합 DB 접근·마이그레이션
│   ├── schema.sql                # 운영 스키마 단일 원본
│   └── backfill_guides.py
├── inference/
│   ├── base.py
│   ├── jetson_backend.py
│   └── rpi_backend.py
├── modules/
│   ├── detector.py               # MediaPipe 양안 검출
│   ├── classifier.py             # EfficientNet + Grad-CAM
│   └── analyzer.py               # 충혈도 등 픽셀 분석
├── models/
│   ├── Augmented_EffNet_V1_B0_best.pth
│   └── set_1000_YOLO26s_best.pt
├── scripts/
│   ├── export_onnx_rpi.sh
│   ├── install_git_hooks.sh
│   └── rpi_preflight.sh
├── tests/
│   └── test_database.py
├── utils/
│   ├── image_proc.py
│   ├── logger.py
│   └── security_utils.py
├── web/
│   ├── static/                   # CSS, JS, 이미지, 캡처, 보고서
│   └── templates/                # 키오스크·모바일·관리자 화면
└── docs/
    └── RPI5_UBUNTU_RUNBOOK.md
```

## Git 훅

RPi 작업 중 Jetson 전용 파일의 실수 커밋을 막으려면:

```bash
bash scripts/install_git_hooks.sh
```

보호 대상은 `inference/jetson_backend.py`, `requirements_jetson.txt`입니다. 의도적으로 변경할 때만 다음과 같이 우회합니다.

```bash
ALLOW_JETSON_CHANGES=1 git commit -m "Describe intentional Jetson change"
```
