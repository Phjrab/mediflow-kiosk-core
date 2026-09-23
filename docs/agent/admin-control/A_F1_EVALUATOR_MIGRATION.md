# Jetson A Macro-F1 Evaluator Migration

Status: deployed on A as `a8257f9` after the gates below passed. This was a
source-only change to the research evaluator. No model inference or web restart
was required.

## Exact scope

- Source fix: `4ff21a2` on `codex/admin-control`.
- Expected A starting commit: `265e545` on `codex/admin-control-a-deploy`.
- Only `experiments/evaluate.py` and `tests/test_experiment_evaluate.py` may
  change. The reviewed patch from the A branch's ancestor `f53a1c6` to
  `4ff21a2` for those two paths has SHA-256
  `857f8b1174412884d49f145f00feeb016bfe48a56bb87bb37c061c4ddb977e80`.
- The corrected metric is `2*TP/(2*TP+FP+FN)` on the answered subset. A
  misclassified class contributes zero; a class absent from both actual and
  predicted answered samples remains undefined. Stored reports are not
  modified by installing this source change.

## Preconditions and sequence

1. Confirm A's branch, exact HEAD, clean worktree, and deployed file hashes.
   Stop on drift. Record non-revealing hashes and permissions for `.env`, both
   operational databases, the owner-only key files, and existing research
   databases. Do not read their contents into logs or copy them to the Mac.
2. Transfer the exact two-file patch only after its local hash matches the
   value above. On A, verify its hash again and require `git apply --check`
   before applying. Confirm `git diff --name-only` lists only the two paths.
3. Run A's existing project virtualenv evaluation tests first, then the F1
   cases and related E3/E4/store tests. No package install, model request,
   research job, or database write is required. If a test fails, restore only
   the two changed source/test files to A's recorded starting commit.
4. Verify the protected hashes and permissions remain unchanged. Commit only
   the two paths on A's existing deployment branch, push that branch, and
   record both SHAs and the test evidence. Do not merge to `main` as part of
   this migration.

## Stop conditions

Stop without deployment if A's starting commit, worktree, patch hash, source
paths, protected-file hashes, key permissions, or focused test results differ
from the expected baseline. Do not restart A's web process or touch B. Do not
rewrite any existing research report or claim medical-quality validation.

## Completed evidence

- A began clean at `265e545`; the two source/test hashes matched their
  `f53a1c6` ancestor. The transferred patch matched the SHA-256 above and
  passed `git apply --check` before changing exactly two files.
- A's existing project virtualenv passed 10 evaluation tests, the five F1
  cases again, 12 store tests, five E3 tests, six survey/hybrid tests, and the
  full 173-test suite. `git diff --check` passed.
- Before/after hashes of `.env`, operational DBs, owner-only VLM key, and all
  four existing research DBs were identical. The key retained mode 0600.
- Only the two approved files were committed and pushed on A's existing
  `codex/admin-control-a-deploy` branch as `a8257f9`. No report was rewritten,
  and no model, worker, controller, B service, or user data changed.
