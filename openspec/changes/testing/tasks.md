## 1. Test infrastructure setup

- [x] 1.1 Create `tests/conftest.py` with shared fixtures: `onboard_module` (importlib import of onboard-product.py), `--update-snapshots` pytest CLI flag, and temp directory helpers
- [x] 1.2 Verify existing tests still pass after adding conftest.py (`uv run python -m pytest tests/test_generation.py -v`)

## 2. Unit tests for pure functions

- [x] 2.1 Create `tests/test_unit.py` with unit tests for `canonicalize`: dots-to-dashes, uppercase-to-lowercase, already-canonical, multiple dots
- [x] 2.2 Add unit tests for `get_application_name` and `get_component_name`: main branch (no suffix), non-main with dots, non-main without dots
- [x] 2.3 Add unit tests for `get_branch_info`: explicit branch, missing branch defaults to main, dotted branch
- [x] 2.4 Add unit tests for `yaml_value`: bool→lowercase, string→double-quoted, int/float→unquoted, other types→quoted string
- [x] 2.5 Add unit tests for `parse_gitlab_url`: multi-level path, two-level path, too-few segments raises ValueError
- [x] 2.6 Add unit tests for `extract_repository_name`: with scheme, without scheme, no path raises ValueError
- [x] 2.7 Add unit tests for `resolve_repo_path`: local_repo_path wins, repo_overrides wins over derived, default derived path from URL

## 3. Unit tests for config normalization

- [x] 3.1 Add unit tests for `normalize_rpa_config`: old format passthrough, new format merges common, tags append (both sides, one side only, neither), invalid format returns empty list
- [x] 3.2 Add unit tests for `normalize_component_config`: old format passthrough, new format merges common fields, pipelinerun defaults merge into each entry, pipelinerun from common only, rpa_values merge, invalid format returns empty list

## 4. Unit tests for config loading

- [x] 4.1 Add unit tests for `Config` priority chain: CLI overrides env, env overrides TOML, TOML overrides defaults, defaults used when nothing specified
- [x] 4.2 Add unit tests for `collect_config_files`: glob expansion, directory scan (YAML only), hidden file exclusion, deduplication, no-matches raises ValueError

## 5. Property-based validation tests

- [x] 5.1 Create `tests/test_properties.py` with helpers to generate output to temp dirs using test configs and walk/parse YAML files
- [x] 5.2 Add property tests for KRD Application resources: required fields (apiVersion, kind, metadata.name, spec.displayName)
- [x] 5.3 Add property tests for KRD Component resources: required fields, spec.application matches versioned app name, spec.source.git.revision matches branch
- [x] 5.4 Add property tests for KRD ImageRepository resources: required fields
- [x] 5.5 Add property tests for KRD ReleasePlan resources: required fields, spec.application matches versioned app name
- [x] 5.6 Add property tests for KRD ReleasePlanAdmission resources: required fields (apiVersion, kind, metadata.name, spec.applications, spec.policy, spec.data)
- [x] 5.7 Add property tests for kustomization.yaml: required fields, resources sorted with no duplicates, every resource entry corresponds to an existing file
- [x] 5.8 Add property tests for branch-aware naming consistency: all resources in a generation run use the same versioned app name and branch suffix

## 6. Pipelinerun property tests

- [x] 6.1 Add property tests for pipelinerun Tekton structure: apiVersion, kind, metadata (name, namespace, labels, annotations), spec (pipelineRef, params)
- [x] 6.2 Add property tests for CEL expressions: correct branch references in on-cel-expression annotations, pathChanged() calls present for cel_path_changed entries
- [x] 6.3 Add property tests for CEL variant placeholder: {variant} replaced in cel_path_changed and cel_push_tag_prefixes, no literal {variant} remains
- [x] 6.4 Add property tests for label construction: name and com.redhat.component from prod_repository, CPE label format validation
- [x] 6.5 Add property tests for label filtering: use_build_args=true removes name/component labels, keeps cpe
- [x] 6.6 Add property tests for file pairs: both on-pull-request and on-push files exist for each component

## 7. Developer portal and ITS property tests

- [x] 7.1 Add property tests for developer portal version files: required camelCase fields (versionName, ga, hidden, releaseDate)
- [x] 7.2 Add property tests for developer portal validation: product_slug with path separators raises ValueError, missing required fields raises ValueError, common field inheritance works
- [x] 7.3 Add property tests for IntegrationTestScenario resources: required fields, branch-aware naming, releasePlanAdmissionName auto-suffixing, components default to all

## 8. Tech-preview filtering and recreate mode tests

- [x] 8.1 Add tests for tech-preview component filtering: stage RPA includes all, tech-preview prod RPA only includes tech_preview=true, regular prod RPA excludes tech_preview=true, prod RPA skips full-container without prod_repository
- [x] 8.2 Add tests for recreate mode: managed subdirectories removed, non-managed files preserved
- [x] 8.3 Add tests for release plan / RPA name matching: missing RPA raises ValueError, orphaned RPA produces warning

## 9. Snapshot update gate

- [x] 9.1 Modify `tests/test_generation.py` to use `--update-snapshots` flag: snapshot mismatch fails without flag, overwrites expected files with flag
- [x] 9.2 Update CLAUDE.md regeneration instructions to include `--update-snapshots` in the workflow

## 10. Verification

- [x] 10.1 Run full test suite (`uv run python -m pytest -v`) and verify all tests pass
- [x] 10.2 Run linter (`uv run ruff check .`) and verify no issues
