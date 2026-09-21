# Admin Control Handoff

Current phase: C0-C4 CODE/MOCK complete, C1/C2 read-only management deployed, and
C4 managed ingress plus actual chat rollback verified. Final deployed runtime source is
`c1e84bb`. C5 remains partial because the VLM device receipt and permanent
MedGemma lifecycle binding are not complete.

The existing LLM/VLM, F1, regression, and synthetic E0-E4 device evidence is
preserved. A runs `codex/admin-control-a-deploy`; its deployed SHA is `1ec6f31`.
B's final controller and ingress source is the clean detached `c1e84bb` release;
the earlier `f0f0555` release remains available for rollback. A's `.env` backup is
owner-only, and its only live setting change is
`VLM_BASE_URL=http://192.168.50.11:8080`; its non-VLM digest is unchanged. The A
database and user data and B inference keys, models, and user data were not changed.

The deployed B inference path is now controller-authoritative: network port 8080
is managed ingress, raw chat is loopback-only 18080, and raw VLM ports 8081/18081
are closed. One real chat apply/rollback completed through the durable operation
coordinator. The permanently running controller still has drafts and mutations
disabled because a concrete MedGemma launcher/owner callback is not wired.

Current device state:

- B controller PID 37652 runs `c1e84bb` and listens only on `127.0.0.1:8090`.
- B managed ingress PID 37550 runs `c1e84bb` on port 8080. Its durable journal is
  open at generation 1 with zero active and zero unknown leases.
- B general LLM PID 37864 is exact-owned and healthy on `127.0.0.1:18080`; its
  runtime cwd is the compatible `6c2d9b1` release. MedGemma is stopped.
- A tunnel PID 1947132 listens only on `127.0.0.1:18090` and forwards only to B loopback 8090; its private PID record is under `/home/jetson_orin_nano/.local/state/mediflow-ai/admin-control-tunnel/`. It has no autostart entry.
- A reads `/home/jetson_orin_nano/.config/mediflow-ai/admin-control-readonly.env`; the file enables reads but keeps drafts and mutations off. The management credential is a separate owner-only mode-0600 file on each device.
- Authenticated GET state/capabilities/current succeeded through A. Capabilities
  reports managed ingress authoritative, drafts false, mutations false and no
  operations. A-to-B synthetic chat/receipt passed after rollback.
- A's kiosk was already stopped and remains stopped; no web process was available to restart. The same-origin route was instead exercised with the actual A virtualenv and did not load the classifier.

Validation: local runnable regression is 160 passed with one skipped; B preflight
C4 suites passed 32 and the direct-CLI device subset passed 17. Real shared-lock,
raw-bypass, receipt, inactive-VLM lease, controller isolation and rollback checks
passed. Earlier regression evidence remains preserved.

Still blocked/not run:

- Permanent controller mutation and a device-tested MedGemma launcher/owner
  binding: BLOCKED_GATE. Do not enable drafts/mutations before this is complete.
- E3 general-LLM receipt is device-verified. E1/E2 VLM device receipt after a
  sequential MedGemma profile selection remains BLOCKED_GATE.
- Permanent controller POST endpoints remain disabled. One local synthetic
  draft/plan was executed directly through the operation coordinator and finished
  `rolled_back` after its injected verification failure.
- A MedGemma start or model/profile switch, medical quality evaluation, and
  real-user-data validation: NOT_RUN.

Next action: implement and mock-test the fixed MedGemma service manager and bind
both owned engines plus the managed ingress to controller bootstrap. Then use a
separate approved window for one sequential chat→VLM→chat synthetic transition.
Keep the current controller mutations off and preserve the C4 rollback environment.

Exact approval phrase for the next device-writing step:

> 승인합니다: `codex/admin-control`의 최신 푸시 HEAD에 MedGemma 고정 launcher·exact owner process manager와 controller mutation bootstrap을 로컬 코드·mock으로 구현하고, 검증된 코드만 Jetson B의 새 detached release로 배포하는 것을 승인합니다. 현재 managed ingress·raw chat 18080·controller·A tunnel과 모든 owner-only 키·환경·rollback 파일을 보존하고, mock·identity·drain·unknown lease·receipt·원복 게이트가 모두 통과한 후에만 유지보수 창에서 draft/mutation을 일시 활성화하여 합성 chat→MedGemma→chat 순차 전환 1회를 실행하세요. 동시 GPU 상주는 하지 말고, 전환 후 drafts/mutations는 다시 비활성화하세요. 실패·drift·미관리 프로세스·unknown lease가 발생하면 admission을 닫고 현재 `1:1:chat_only`로 즉시 원복한 뒤 추가 재시작을 하지 마세요. 모델 파일·키·DB·사용자 데이터·CUDA/PyTorch·의료 품질 평가는 변경하지 마세요.
