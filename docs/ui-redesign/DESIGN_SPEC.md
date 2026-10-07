# MediFlow design system

Guided Screening은 한 화면 한 과제와 기존 순서(시작 → 식별·동의 → 검사 선택 → 문진 →
촬영·분석 → 결과)를 사용한다. Clinical Operations는 14~16px 운영 목록·설정·검토 영역으로 구분한다.

색은 mediflow-tokens.css의 단일 계층: 배경 #F6F8F5, 표면 #FFFFFF, 본문 #173534,
primary #146B65, 보조 #E7F1ED. 기존 변수는 alias로 연결한다. theme preference와
6개 기존 언어를 유지한다. system font를 쓰며 CDN 없이 렌더된다.

환자 본문 20px, 제목 32~44px, touch control 56px 이상, radius 18px.
모바일은 18px 본문·56px 주요 행동, 단일 열, 문서 scroll. 고정 height/overflow를 피한다.
관리자는 navbar + 작업별 section과 목록·상세를 쓴다. plan과 Apply는 분리한다.
미준비/실패/미확인/오래됨을 문구와 disabled/경계 스타일로 표시한다.

focus ring #795400, semantic nav/aria-current step, skip link, reduced-motion,
dialog focus trap/복귀를 공통 shell에서 제공한다. 대비는 05에서 실제 계산·브라우저 검사한다.
수치와 기존 의료 상태 매핑은 그대로 유지하며 모델 점수와 진료 확인 필요 경계를 붙인다.
