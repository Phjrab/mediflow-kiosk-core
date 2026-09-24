# MediFlow Kiosk Core — 포트폴리오 설명·증거 (2026-09-24)

기준: 로컬 `main` `9b9625af35bd31c46af797e2e9efd8e5d167ae8a`.
운영 장비의 마지막 기록된 A 배포 `9cc410a`와 B controller release `86bebb6`은
서로 다른 기준입니다. 이 문서 작업은 장비 접속이나 추론을 수행하지 않았습니다.

## 소개 초안

MediFlow는 USB 카메라 입력에서 안구 결과 확인까지 이어지는 Jetson 기반 연구용
키오스크 코어입니다. 검사 선택과 문진 후 얼굴 영상의 눈 영역을 MediaPipe Face
Mesh로 찾고, EfficientNet-B0이 정상 포함 5개 클래스로 분류합니다. Grad-CAM과
픽셀 지표를 결과와 함께 보여 주며 사용자 이력·보고서로 연결합니다. 일반 LLM
설명은 선택한 provider가 준비된 경우에만 사용하고, MedGemma E1/E2 연구 경로는
운영 결과와 분리합니다. 피부·두피 모델은 아직 설정되지 않았습니다. 합성 입력의
통합 검증은 기록돼 있지만 의료 정확도와 실제 환자 대상 유효성은 확인되지
않았습니다.

## 문제 / 접근 / 확인 결과 / 남은 검증

| 구분 | 설명과 근거 |
|---|---|
| 문제 | 촬영, 안구 분류, 설명, 결과 기록을 하나의 사용 흐름으로 연결해야 함 |
| 접근 | [눈 검출](../modules/detector.py) → [분류·Grad-CAM](../modules/classifier.py) → 웹 결과·저장 (`eye_server.py`) |
| 확인 결과 | 2026-09-21 단일 생성 이미지 E0~E4 통합 기록은 성공; paired assessed 결과 0건 ([증거](agent/evidence/jetson-a-synthetic-e0-e4-2026-09-21.json)) |
| 남은 검증 | 라벨 있는 평가, 실제 환자 데이터 검토, 장기 GPU 안정성, 새 live Admin Apply |

## 실제 AI 경로와 조건

| 구성 | 현재 확인된 역할 | 제한 |
|---|---|---|
| MediaPipe Face Mesh | 좌·우 눈 ROI를 224×224로 추출 | 얼굴/눈 검출 실패 가능 |
| EfficientNet-B0 | 결막염·다래끼·백내장·정상·포도막염 5개 클래스 | 진단 확정이나 공개 성능 재현 근거 아님 |
| Grad-CAM | 예측 클래스에 대한 시각화 | 병변 위치의 임상 정답이 아님 |
| 일반 LLM | `LLM_PROVIDER`로 OpenAI/Gemini/local 중 명시적 선택 ([dispatch](../utils/llm_client.py)) | local 실패 시 cloud 자동 fallback 없음 |
| MedGemma E1/E2 | 분리된 연구 VLM 입력·출력 | 기본 사용자 분류·DB·PDF 대체 아님 |
| E3/E4 | 설명 생성/결정적 비교 | 새 영상 분류 모델이 아님 |
| 피부·두피 | UI·문진·촬영과 모델 등록 틀 ([설정](../config/screening_modalities.json)) | 모델 `not_configured` |

## 검증 수치의 의미

- 2026-09-21 E0~E4는 생성 이미지 1개, `N_labelled=0`의 통합 증거입니다.
  다섯 job 성공은 정확도, 민감도, 특이도 또는 임상 결과가 아닙니다.
- `modules/classifier.py` 첫 docstring의 `99.09%`는 공개 평가 데이터셋,
  분할, 표본 수, 체크포인트와 평가 스크립트의 연결이 확인되지 않았습니다.
  따라서 제품 성능 주장에 사용하지 않습니다. 해당 docstring도 향후
  `과거 기록 수치, 재현 평가 근거 미확인`으로 수정하는 것이 좋습니다.
- [Admin Control handoff](agent/admin-control/HANDOFF.md)의 2026-09-23
  로그인·overview·동일 설정 draft→plan은 실제 새 Apply/모델 전환의 검증이
  아닙니다. 거부 응답 복구는 동일 plan의 명시적 거부·미접수·건강한 B 상태에서만
  pause를 해제하며 timeout이나 불확실 응답에서는 해제하지 않습니다.

## 개발 과정의 AI 활용과 개인 기여 확인

제품 내부 AI 추론과 개발 중 AI 도구 사용은 별개의 사실입니다. 저장소의
[agent 작업 기록](agent/WORKLOG.md), [Admin 작업 기록](agent/admin-control/WORKLOG.md),
커밋은 설계·구현·테스트의 흐름을 보여 줍니다. 하지만 이 기록만으로 특정 모델
사용, 개인별 작성 비율이나 본인의 직접 구현 부분을 확정할 수 없습니다.

지원서에 1인칭으로 쓰기 전에 다음을 확인합니다.

| 확인 항목 | 필요한 자료 |
|---|---|
| 본인이 정한 요구·안전 기준 | 당시 의사결정과 리뷰 기록 |
| AI에 맡긴 작업 | 실제 지시·대화, 수용·수정한 산출물 |
| 본인이 수행한 통합·검증 | 커밋/PR, 장비 기록, 테스트 판단의 담당 범위 |
| 모델 학습·평가 | 데이터셋 출처, split/중복 통제, checkpoint, 평가 출력 |

설명 가능한 기술 문제 사례는 A/B 장치의 단일 모델 순차 운영, 사용자 결과와
연구 데이터를 분리한 구조, 모델 전환 시 연구 작업 중단·복구 조건입니다.
각 사례를 개인 성과로 쓰려면 본인 역할을 위 자료로 연결해야 합니다.

## 공개용 화면 목록

현재 README에 연결할 비식별 실제 화면은 확보되지 않았습니다. 화면을 만들 때
환자 얼굴·문진·QR·사용자 식별자·계정·내부 주소·키를 제외하고 원본 날짜와
배포 SHA를 기록합니다.

| 화면 | 보여 줄 내용 | 필수 캡션 |
|---|---|---|
| 검사 선택·촬영/눈 정렬 | 기본 운영 입력 흐름 | 실제 장비/fixture, 촬영 날짜 |
| 5개 클래스 결과·Grad-CAM | 분류 결과 표시와 설명 | 예시 입력/실제 입력, 의료 평가 아님 |
| Admin overview·draft→plan | 제어 경계와 사전 계획 | 2026-09-23 기록, 새 live Apply 아님 |
| E0~E4 연구 요약 | 운영/연구 데이터 분리 | 생성 이미지, `N_labelled=0` |
| 모바일·PDF 예시 | 사용자 결과 확인 경로 | 모든 개인 식별자와 QR 제거 |

실제 캡처 없이 도식만 사용하면 `구현 구조도`라고 표시하고 작동 화면의 증거로
제시하지 않습니다. 자세한 환경과 조건은 [로컬 AI runbook](LOCAL_AI_RUNBOOK.md),
[실험 프로토콜](AI_EXPERIMENT_PROTOCOL.md), [Admin handoff](agent/admin-control/HANDOFF.md)에
연결합니다.

## GitHub About 후보 (미적용)

설명: `Jetson eye-screening kiosk core with EfficientNet, Grad-CAM, optional LLM explanations, and isolated VLM research`

Topics: `jetson`, `edge-ai`, `computer-vision`, `efficientnet`, `grad-cam`, `local-llm`, `flask`.
