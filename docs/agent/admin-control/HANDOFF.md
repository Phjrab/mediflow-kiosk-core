# Admin Control Handoff

Current phase: C0-C4 CODE/MOCK complete and C1/C2 DEVICE_READ_ONLY deployed; C5 remains PARTIAL/CODE/MOCK. C4 is uncommitted at the time of this handoff edit and is based on pushed source `6fa9e91`; replace this sentence with the final pushed SHA after commit.

The existing LLM/VLM, F1, regression, and synthetic E0-E4 device evidence is preserved. A runs `codex/admin-control-a-deploy`; its runtime-code merge is `1dffc7a` and later branch commits only update this deployment record. B has release `/home/jetson2/mediflow-ai/control/releases/f0f0555`. A's `.env`, database and user data and B's inference keys, models and lifecycle records were not changed.

Real B apply remains intentionally unavailable. Controller-authoritative ingress,
shared lifecycle locking, sequential owned adapters, unknown-lease recovery, and
E3 receipt persistence now exist in local code and mock tests. The currently
deployed inference ports still bypass those components, so no real model change is
safe until the separate maintenance migration is approved and completed.

Read-only device state:

- B controller PID 35999 listens only on `127.0.0.1:8090`; private PID record is under `/home/jetson2/.local/state/mediflow-ai/admin-control-runtime/`. It has no autostart entry.
- A tunnel PID 1947132 listens only on `127.0.0.1:18090` and forwards only to B loopback 8090; its private PID record is under `/home/jetson_orin_nano/.local/state/mediflow-ai/admin-control-tunnel/`. It has no autostart entry.
- A reads `/home/jetson_orin_nano/.config/mediflow-ai/admin-control-readonly.env`; the file enables reads but keeps drafts and mutations off. The management credential is a separate owner-only mode-0600 file on each device.
- Authenticated GET state/capabilities/models/current/events succeeded. Capabilities reports drafts false, mutations false and no operations. B's managed general LLM remained PID 9205 with its original start tick and healthy port 8080. MedGemma is stopped and port 8081 is free.
- A's kiosk was already stopped and remains stopped; no web process was available to restart. The same-origin route was instead exercised with the actual A virtualenv and did not load the classifier.

Validation: the A deployment merge passed 144 runnable tests with one skipped; B control suites passed 11; A focused device suites passed 9. The authenticated same-origin read, `.env`/DB hash preservation and exact process identity checks passed. The earlier A 141-test run predates this diff and is retained only as prior evidence.

Still blocked/not run:

- Managed chat/VLM ingress deployment, raw-port closure and device drain/switch/restore: BLOCKED_GATE. Review `C4_MAINTENANCE_MIGRATION.md` and its `.diff` first.
- E3 general-LLM runtime receipt is CODE/MOCK complete; device receipt verification remains BLOCKED_GATE.
- Draft/plan device writes and disabled-endpoint POST probes: NOT_RUN. A proposed POST probe was rejected because the approval covered GET verification only; no POST was sent.
- Any actual B model change, device mutation test, medical quality evaluation, or real-user-data validation: NOT_RUN.

Next action: review and execute the separate C4 maintenance migration only after
explicit approval. Keep drafts and mutations off during raw-port migration; enable
them only after ingress authority, exact process ownership, shared-lock contention,
synthetic receipt, and rollback checks pass. Preserve the current read-only release
and pre-migration general-LLM environment as the rollback path.

Exact approval phrase for the next device-writing step:

> 승인합니다: `codex/admin-control`의 푸시된 C4 HEAD를 기준으로 `docs/agent/admin-control/C4_MAINTENANCE_MIGRATION.md`의 게이트 순서와 `C4_MAINTENANCE_MIGRATION.diff`를 Jetson A/B의 별도 유지보수 창에서 적용하는 것을 승인합니다. 기존 일반 LLM을 정확한 소유권 검증 후에만 일시 중지하고 raw chat/VLM을 B loopback 18080/18081로 이동한 다음 managed ingress를 B:8080에 설치하고, A의 비공개 VLM URL만 B:8080으로 변경하세요. 기존 추론 키는 owner-only mode 0600 파일로 유지하고 출력·로그·저장소·프로세스 인자에 노출하지 마세요. draft/mutation은 raw 우회 차단·공유 lock·unknown lease·합성 receipt·원복 검증이 모두 통과할 때까지 비활성화로 유지하고, 통과 후에만 1회의 합성 apply·restore를 수행하세요. 미관리 프로세스, PID/argv/boot-id 불일치, active/unknown inference, raw 우회, receipt drift, rollback 실패 중 하나라도 발견되면 즉시 admission을 닫고 기존 chat-only 상태로 원복한 뒤 mutation을 켜지 마세요. 모델·키·DB·사용자 데이터·의료 품질 평가는 변경하지 마세요.
