# MediFlow Admin Control C0 Baseline

Recorded 2026-09-21 KST. This is an observation baseline, not a reset target.

## Sources read

- Complete attached `MEDIFLOW_ADMIN_CONTROL_ALL_IN_ONE.md` (1,256 lines), including API, UI, C0-C6, tests, rollout, and reviewed baseline sections.
- Repository `docs/agent/HANDOFF.md`, `WORKLOG.md`, `IMPLEMENTATION_PLAN.md`, and the earlier integrated LLM/VLM prompt.
- `eye_server.py`, `web/templates/admin_config.html`, `utils/ai_config.py`, `utils/llm_client.py`.
- `scripts/local_llm_service.py`, `scripts/run_local_llm_candidate.sh`, `services/medgemma/app.py`.
- Experiment store, worker, evaluation, and existing AI/lifecycle tests.
- No repository `AGENTS.md` exists at this baseline.

## Source and deployed revisions

| Location | Branch / role | SHA | Working tree |
|---|---|---|---|
| Mac source | `codex/admin-control`, created from `codex/local-ai-shadow-experiments` | base `2ccd9f1ba60e6fa773a8ae4afb723d6ff4b5a930` | clean before C0 implementation |
| Jetson A `/home/jetson_orin_nano/project/eye_project` | `codex/local-llm-operational` | `6ee537fa82e32d9761b026f3bf464a3ebbc6fadc` | clean |
| Jetson B versioned release `/home/jetson2/mediflow-ai/control/releases/5c81b8d` | `codex/local-ai-shadow-experiments` | `2ccd9f1ba60e6fa773a8ae4afb723d6ff4b5a930` | clean |
| Jetson B preserved operational control directory | non-Git | n/a | preserved |

At observation time B listened on 8080 only. Ports 8081 and 8090 were not listening. No process or configuration was changed during C0.

## Preserved evidence

- Jetson A's actual virtual environment previously passed 141 discovered tests.
- F1 evaluation includes zero-prediction reference classes; the existing handoff records the regression result.
- One synthetic, non-user sample completed E0-E4 on device. Evidence: `docs/agent/evidence/jetson-a-synthetic-e0-e4-2026-09-21.json`, SHA-256 `0471a186621128da0595daca2eb94d3f9f27512ba6e892bcc29d740d4c85b07b`.
- This is engineering integration evidence. Medical quality evaluation and real-user-data validation remain unperformed.

## Authority boundaries

| Data | Authority | Application |
|---|---|---|
| Provider, endpoint, inference credential, timeouts | Jetson A bootstrap/config | A request routing only |
| Local chat temperature, top-p, max output | Jetson A versioned generation snapshot | Next admitted local chat request only |
| Artifact, preset, context, resource placement, active profile | Jetson B immutable runtime revision | Draft then plan; C4 operation required to mutate |
| E0-E4 model/prompt/config lineage | Research run snapshot plus B receipt | Existing run remains immutable |

The UI uses the fixed serving alias for routing and displays artifact identity separately. Alias changes cannot stand in for a weight switch.

## Current hard-coded runtime points

- `run_local_llm_candidate.sh` fixes Qwen artifact, alias, port 8080, context 4096, and parallelism 1.
- `local_llm_service.py` owns the general LLM through its exact PID/UID/executable/argv/cwd/boot/start-tick record and `flock`. Its `inspect_service(..., remove_stale=False)` path is suitable for a side-effect-free snapshot.
- MedGemma's llama.cpp CLI backend starts a child per request; service readiness and model residency must remain separate.
- The current external inference ports are not controlled by a shared admission layer. B-authoritative in-flight completion is therefore unknown and real lifecycle mutation is blocked.

## Trust and safety decisions

- Browser to A remains same-origin admin session plus CSRF; the browser receives neither B address nor management credential.
- A to B uses a separate management key file and verified HTTPS. Plain HTTP is accepted only for loopback, allowing an approved local tunnel without disabling certificate validation for a remote IP.
- B has no HTML, login page, iframe, arbitrary URL/path/argv/shell, model download, quantization, Docker, reboot, purge, or prompt editor.
- Management reads never load a model, generate, clean stale PID metadata, or recover a service.
- C0-C3 cannot execute an operation. `AI_CONTROL_MUTATIONS_ENABLED` is off and the operation endpoint fails closed.

## Write gate blockers

Real B lifecycle changes remain `BLOCKED_GATE` until the managed inference ingress owns admission and leases for both chat and VLM, raw-port bypass is closed, research queued/running protection is wired, TLS/bootstrap trust is installed, and C4 race/crash/rollback tests pass. The prior synthetic E0-E4 result satisfies an integration evidence input; it does not satisfy these control-plane gates by itself.
