# Integrated implementation tracking

P0: inspect current code and baseline, preserve files and record environmental gaps.
P1: strict providers, bounded local transport, safe allowlisted context, fake HTTP tests.
P2: chat API/UI, administrator atomic settings and config status; deployment tools.
P3: immutable sample/ROI provenance and authenticated registration; CAM options.
P4: independent image adapter, strict schema and separately isolated server runtime.
P5: durable bounded research jobs, cancellation/recovery and admin comparison.
P6: reproducible offline runner and evaluation with explicit denominators.
P7: hardware validation only after actual reachability/model/data access.
P8: tested evidence, runbooks and accurate handoff after each implemented unit.

Never force model co-residency or automatically invoke cloud on local failure.
Never alter .env, HASH_PEPPER, CUDA/PyTorch, operational DB, weights or user data.

Current state: P0 done; P1/P2/P3 code and mocks done; P4/P5 code and mocks done;
P6 E0/E1/E2/E3/E4 code and mock verification complete; P7 has verified the
pinned container core but remains blocked on official MedGemma source access,
model memory/inference, provenance, and approved evaluation data; P8 is current. See `HANDOFF.md` for the next work.
