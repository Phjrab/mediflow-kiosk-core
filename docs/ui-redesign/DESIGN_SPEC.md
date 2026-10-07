# MediFlow design system

Guided Screening은 한 화면 한 과제와 기존 순서(시작 → 식별·동의 → 검사 선택 → 문진 →
촬영·분석 → 결과)를 사용한다. Clinical Operations는 14~16px 운영 목록·설정·검토 영역으로 구분한다.

색은 mediflow-tokens.css의 단일 계층: 배경 #F6F8F5, 표면 #FFFFFF, 본문 #173534,
primary #146B65, 보조 #E7F1ED. 기존 변수는 alias로 연결한다. theme preference와
6개 기존 언어를 유지한다. SUIT Variable v2.0.5를 로컬 정적 자산으로 제공한다.
font-ui/font-display/font-numeric은 같은 family이며 미지원 glyph는 시스템 대체 글꼴로 렌더된다.

환자 본문 20px/1.6, 주요 안내·버튼 22px, 제목 32~40px/1.3, 보조 18px, meta 16px.
모바일은 18px 본문·19px 핵심 버튼·28px 제목이며 기존 56px 주요 행동 높이를 유지한다.
굵기는 본문 400/500, 문진·버튼 500/600, 제목 600/700, 한글 자간 0이다.
단일 열과 문서 scroll을 유지하며 고정 height/overflow를 피한다. radius 18px.
관리자는 navbar + 작업별 section과 목록·상세를 쓴다. plan과 Apply는 분리한다.
미준비/실패/미확인/오래됨을 문구와 disabled/경계 스타일로 표시한다.

focus ring #795400, semantic nav/aria-current step, skip link, reduced-motion,
dialog focus trap/복귀를 공통 shell에서 제공한다. 대비는 05에서 실제 계산·브라우저 검사한다.
수치와 기존 의료 상태 매핑은 그대로 유지하며 모델 점수와 진료 확인 필요 경계를 붙인다.
