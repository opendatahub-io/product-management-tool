## Why

The current test strategy for `onboard-product.py` relies on regenerating expected output files and comparing them against freshly generated output. Tests always pass after regeneration — they verify consistency within a single run but don't catch actual regressions in template rendering logic. When a template or generation code change breaks something, the workflow is: regenerate expected outputs, run tests, tests pass. The broken output becomes the new baseline without anyone noticing.

This leads to repeated manual testing after every change, and subtle errors or broken old behaviors slip through undetected.

## What Changes

- Add unit tests for pure functions (canonicalize, naming, normalization, URL parsing, yaml_value) that validate correctness independently of templates
- Add property-based validation tests that check structural invariants of generated YAML (required fields, valid references, consistent naming) — these catch malformed output even when snapshots are regenerated
- Add snapshot tests with an explicit `--update-snapshots` gate so baselines can only be updated deliberately, not silently
- Add validation tests for CEL expression construction, label generation/filtering, tech-preview component filtering, and RPA/release-plan name matching
- Add tests for config loading priority (CLI > env > TOML > defaults) and config file collection

## Capabilities

### New Capabilities
- `testing`: Comprehensive test suite covering unit tests, property-based YAML validation, snapshot tests with update gates, and integration-level correctness checks for all generation modes (KRD, pipelinerun, developer portal)

### Modified Capabilities
- `testing`: The existing spec at `openspec/specs/testing/spec.md` will be refined with delta specs to reflect the final implementation requirements

## Impact

- `tests/test_generation.py`: Existing tests remain but snapshot comparison gets the `--update-snapshots` gate
- New test files will be added under `tests/`
- `pyproject.toml`: May need new test dependencies (e.g., pytest flags configuration)
- `tests/configs/`: Existing test configs are reused; no changes needed
- `tests/expected/`: Existing expected outputs become snapshot baselines with explicit update semantics
- No changes to `onboard-product.py` or templates — this is a test-only change
