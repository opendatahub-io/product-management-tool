## Context

`onboard-product.py` generates Kubernetes resources (KRD) and Tekton pipelinerun configs from YAML product definitions. The current test suite in `tests/test_generation.py` compares generated output against baseline files in `tests/expected/`. The regeneration workflow (`rm expected; regenerate; commit`) means broken output silently becomes the new baseline — tests verify self-consistency, not correctness.

The codebase has many pure functions (canonicalize, naming, normalization, URL parsing, yaml_value) that are untested in isolation. Template rendering produces structured YAML with invariants (required fields, valid CEL expressions, consistent naming) that are never validated.

## Goals / Non-Goals

**Goals:**
- Unit tests for every pure function in `onboard-product.py` and `config.py`
- Property-based validation that generated YAML has correct structure regardless of snapshot state
- Snapshot tests gated behind `--update-snapshots` so baselines require deliberate human review
- Tests that catch regressions in CEL expression building, label generation, tech-preview filtering, and config normalization

**Non-Goals:**
- Changing `onboard-product.py` or any template — this is test-only
- Full integration testing with real git repos or Konflux clusters
- Property-based testing with hypothesis/fuzzing — standard parametrized tests are sufficient
- Replacing the existing test infrastructure — extend it

## Decisions

### 1. Test file organization

Add new test files alongside the existing `tests/test_generation.py`:

- `tests/test_unit.py` — unit tests for pure functions (naming, normalization, URL parsing, yaml_value, config loading)
- `tests/test_properties.py` — property-based validation of generated YAML structure (runs generation, then validates invariants on output)
- `tests/test_generation.py` — existing file, modified to add `--update-snapshots` gate

**Why not one big file:** The existing `test_generation.py` is already 558 lines. Separating unit tests from property tests keeps each file focused and lets you run `pytest tests/test_unit.py` for fast feedback during development.

**Alternative considered:** Putting everything in `test_generation.py`. Rejected because it's already large and mixing unit tests with snapshot tests makes it hard to run them selectively.

### 2. Snapshot update gate via pytest flag

Add a `--update-snapshots` CLI flag to pytest via `conftest.py`. The existing `compare_directories()` helper checks this flag: if the snapshot mismatches and the flag is set, overwrite the expected files and pass; if the flag is not set, fail with a diff.

**Why conftest.py:** pytest's standard mechanism for custom CLI options. No new dependencies needed.

**Alternative considered:** A separate `update_snapshots.py` script. Rejected because it duplicates the generation logic and doesn't integrate with the test runner.

### 3. Import mechanism

The existing tests use `importlib.util` to import `onboard-product.py` (dash in filename). New test files will reuse the same pattern via a shared `conftest.py` fixture.

**Why:** Consistency with existing approach. Avoids renaming the main script which would break downstream workflows.

### 4. Property validation approach

Property tests generate output to a temp directory using the existing test configs (`tests/configs/test-full-container.yaml`, `tests/configs/test-disk-image.yaml`), then walk the output tree and validate YAML structure. They don't compare against baselines — they check invariants.

**Why temp dirs:** Isolation from snapshot baselines. Property tests and snapshot tests serve different purposes and shouldn't interfere.

**What properties to check:**
- Required fields per resource kind (apiVersion, kind, metadata.name, spec.*)
- Consistent branch-aware naming across all resources in a generation run
- Kustomization resources list matches actual files on disk
- Pipelinerun CEL annotations contain expected branch references
- CPE label format matches `cpe:/a:redhat:{name}:{major.minor}::{target}`
- Both pull-request and push files exist for each component

### 5. Unit test scope

Test every pure function directly with parametrized inputs. These are the functions most likely to have subtle bugs that snapshot tests miss:

| Function | Key edge cases |
|---|---|
| `canonicalize` | dots, uppercase, already-canonical, multiple dots |
| `get_application_name` / `get_component_name` | main branch, dotted branch, empty branch |
| `get_branch_info` | missing branch key, main, dotted branch |
| `yaml_value` | bool, string, int, float, other types |
| `parse_gitlab_url` | multi-level paths, two-level, too-few segments |
| `extract_repository_name` | with/without scheme, no path |
| `resolve_repo_path` | local_repo_path, override, derived, bad URL |
| `normalize_rpa_config` | list, dict, tags append, tags one-sided, invalid |
| `normalize_component_config` | list, dict, pipelinerun merge, rpa_values merge, pipelinerun from common only |
| `collect_config_files` | globs, directory, dedup, hidden files, no matches |
| `Config` | CLI > env > TOML > defaults priority chain |

## Risks / Trade-offs

- **[Risk] Property tests may drift from actual Kubernetes API requirements** → Mitigation: Base required fields on the actual templates, not on Kubernetes API docs. The tests validate what the tool produces, not what Kubernetes accepts.
- **[Risk] Snapshot update gate adds friction to the regeneration workflow** → Mitigation: This is intentional. The CLAUDE.md regeneration instructions will be updated to include `--update-snapshots`. The friction forces review.
- **[Risk] `importlib` import pattern is fragile** → Mitigation: Centralize it in `conftest.py` as a fixture so it's maintained in one place.
- **[Trade-off] No hypothesis/fuzzing** → Parametrized tests with hand-picked edge cases are simpler, faster, and sufficient for this codebase size. Can add hypothesis later if needed.
