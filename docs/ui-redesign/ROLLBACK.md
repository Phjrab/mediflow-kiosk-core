# UI 변경 rollback

초기 리디자인은 기존 clean baseline `bfab34c`에서 branch `codex/ui-mediflow-guided-screening`에
만든 두 로컬 커밋으로 구성한다. UI·관측 source commit은 `0c7fbf0f598ea65f952e8bd61dd61842cb8ef331`,
증거·문서는 그 다음 commit이다. `git log -2 --oneline`으로 정확한 두 SHA를 확인한다.

후속 드롭다운 높이 조정 커밋(`Align dropdown and text input heights`)이 있으면
`git log --oneline`에서 해당 SHA를 확인해 먼저 revert한다. 그 후 아래 초기 source 원복을 진행한다.

## source 원복

현재 사용자 변경이 있으면 먼저 내용을 확인하고 보존한다. source commit만 되돌리려면:

```sh
git revert 0c7fbf0f598ea65f952e8bd61dd61842cb8ef331
```

이 명령은 UI·추가 camera telemetry·테스트/fixture 변경을 되돌리는 새 commit을 만든다.
기록을 reset/clean/force-push로 지우지 않는다. 충돌이 생기면 사용자 변경과 함께 검토한다.
증거·README까지 원복할 때는 문서 commit을 먼저 `git revert <evidence-commit>`한 뒤 source를
revert한다. 이 문서가 포함된 HEAD SHA는 `git log`에서 확인한다.

## 저장과 운영 경계

- DB/schema/.env/HASH_PEPPER/config.local.json/모델 artifact를 변경하지 않았다.
  따라서 원복에 DB 삭제·migration·모델 교체·서비스 restart 명령이 필요하지 않다.
- theme, i18n_language, selectedLanguage 등 기존 preference key/값은 migrate하지 않았다.
  source 원복 후 기존 preference를 그대로 읽을 수 있다.
- 문진 draft는 신규 session-only key `screening_survey_draft`다. 원복 전 사용자가 작성 중이면
  먼저 기존 UI로 입력을 처리한다. 원복 후 남은 draft key는 이전 UI에서 무시하며 탭의
  session이 끝날 때 사라진다. theme나 모든 브라우저 storage를 일괄 삭제하지 않는다.
- 검사 종료 시 지운 session·기존 민감 local mirror는 개인정보 정리이며 복원하지 않는다.
  서버에 저장된 이력은 이 정리로 삭제되지 않는다.
- 이번 검증에서는 운영 Apply·메시지·외부 LLM·모델 변경·서비스 재시작을 하지 않았다.
  해당 운영 액션을 되돌리는 절차는 이번 rollback의 범위가 아니다.

격리 preview를 다시 실행했다면 해당 terminal의 Ctrl-C로 **본인이 만든 서버만** 종료한다.
운영 서비스에 pkill이나 시스템 restart를 실행하지 않는다.
