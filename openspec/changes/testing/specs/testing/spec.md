## MODIFIED Requirements

### Requirement: Snapshot tests with explicit update gate
The system MUST support golden file comparison tests that do NOT auto-update. Snapshots can only be updated by running pytest with a `--update-snapshots` flag. The existing `tests/expected/` directories serve as snapshot baselines. The existing `compare_directories()` helper SHALL be wrapped to support the update gate.

#### Scenario: Snapshot matches
- GIVEN existing snapshot files in `tests/expected/` and no changes to templates or logic
- WHEN tests run without `--update-snapshots`
- THEN tests pass by comparing generated output to snapshots

#### Scenario: Snapshot mismatch without flag
- GIVEN a template change that alters generated output
- WHEN tests run without `--update-snapshots`
- THEN the test FAILS with a clear diff showing expected vs actual file content

#### Scenario: Snapshot update with flag
- GIVEN a template change that alters generated output
- WHEN tests run with `--update-snapshots`
- THEN snapshot files in `tests/expected/` are overwritten with new output
- AND the test passes
- AND the updated snapshots appear in `git diff` for human review before commit
