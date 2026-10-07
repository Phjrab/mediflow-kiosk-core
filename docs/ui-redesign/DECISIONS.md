# 결정 기록

- 2026-10-07: 현재 실제 흐름은 식별/동의가 검사 선택보다 먼저다. stepper도 이 순서를 반영한다.
- 기존 Jinja page와 DOM IDs/events를 유지한다. 새 SPA/framework/backend로 이관하지 않는다.
- 색 토큰은 공통 계층으로 추출하고 페이지별 구조만 기존 CSS에 둔다. !important 덧붙이기를 사용하지 않는다.
- 서버 capability의 model_status=ready인 항목만 시작/전체 선택에 포함한다. 캐시로 준비를 추정하지 않는다.
- 미설정 capture/result 구조는 기존 직접 경로에서 분석 불가를 계속 명시한다.
- 위험 액션은 기존 권한/CSRF/confirm/gate를 유지한다. 검증은 mock preview와 기존 isolated tests만 사용한다.
- 외부 reference 재열람은 하지 않았으며 팩의 명시 목표를 적용한다. 신규 제품 dependency/분석 SDK/원격 font는 없다.

- 활성 route 외에도 보존 대상 dormant 모바일 template을 브라우저에서 검사했다. 원본 m_index의 orphan script와 m_result의 번역이 측정 child DOM을 지우던 오류를 함께 수정했다. m_index의 확대 금지 viewport도 제거했다. 새 운영 모바일 route는 만들지 않았다.
- 신규 Q&A 연결은 기존 chat-widget을 result에 포함하며 provider status의 configured만 활성화한다. 외부 provider routing/backend는 변경하지 않는다.
- current_frame의 monotonic age와 UVC permission 관측만 backend에 추가한다. 3초 stale 표시는 UI freshness이며 의료 threshold가 아니다.
- 최종 source 검토에서 DEBUG_MODE가 Face Mesh 표시 설정이라는 잘못된 안내를 제거했다. 관리자 상세의 명시적 버튼은 기존 `/video_frame?mesh=1` 한 프레임을 조회하고 닫을 때 src를 지운다. missing/stale에는 비활성화하며 새 카메라 session을 시작하지 않는다. 환자 및 dormant 모바일 preview는 mesh=0이다.
