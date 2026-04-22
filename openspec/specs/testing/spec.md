# Testing Specification

## Purpose
Validate correctness of onboard-product.py output through property-based checks, unit tests, and snapshot tests with explicit update gates. Tests MUST catch regressions in template rendering, config normalization, naming logic, and generated YAML structure — not just verify consistency within a single run.

## Requirements

### Requirement: Unit tests for pure functions
The system MUST have unit tests for all pure functions that transform data, independent of template rendering or file I/O.

#### Scenario: canonicalize converts dots to dashes and lowercases
- GIVEN various inputs ("rhoai-2.23", "MyApp.V2", "already-canonical", "a.b.c.d")
- WHEN canonicalize is called
- THEN dots are replaced with dashes and the result is lowercased

#### Scenario: get_application_name branch-aware naming
- GIVEN base_name and branch combinations (main, non-main with dots, non-main without dots)
- WHEN get_application_name is called
- THEN main returns base_name unchanged
- AND non-main returns base_name-canonicalized_branch

#### Scenario: get_component_name branch-aware naming
- GIVEN base_name and branch combinations
- WHEN get_component_name is called
- THEN the same branch-aware rules as get_application_name apply

#### Scenario: get_branch_info extracts all branch data
- GIVEN a definition dict with application and optional branch
- WHEN get_branch_info is called
- THEN it returns (branch, normalized_branch, versioned_app_name) as a consistent tuple
- AND missing branch defaults to "main"

#### Scenario: yaml_value formats types correctly
- GIVEN values of type bool, str, int, float
- WHEN yaml_value is called
- THEN booleans become lowercase unquoted "true"/"false"
- AND strings are double-quoted
- AND numbers are unquoted

#### Scenario: parse_gitlab_url extracts org and repo
- GIVEN valid and invalid GitLab URLs
- WHEN parse_gitlab_url is called
- THEN valid URLs return (org, repo_path)
- AND invalid URLs (fewer than 2 path segments) raise ValueError

#### Scenario: extract_repository_name strips registry domain
- GIVEN registry URLs with and without scheme
- WHEN extract_repository_name is called
- THEN the domain is stripped and only the repo path remains
- AND URLs without a path component raise ValueError

#### Scenario: resolve_repo_path follows priority chain
- GIVEN components with local_repo_path, with repo_overrides match, and with neither
- WHEN resolve_repo_path is called
- THEN local_repo_path wins over repo_overrides
- AND repo_overrides wins over URL-derived path

### Requirement: Unit tests for config normalization
The system MUST have unit tests that verify normalize_component_config and normalize_rpa_config handle both old and new config formats correctly, including edge cases.

#### Scenario: normalize_rpa_config old format passthrough
- GIVEN an RPA config that is a plain list
- WHEN normalize_rpa_config is called
- THEN the same list is returned unchanged

#### Scenario: normalize_rpa_config new format merges common
- GIVEN an RPA config with "common" and "rpas" keys
- WHEN normalize_rpa_config is called
- THEN each RPA contains all common fields plus its own overrides
- AND RPA-specific values override common values

#### Scenario: normalize_rpa_config tags append
- GIVEN common tags ["v1", "v2"] and an RPA with tags ["stage"]
- WHEN normalize_rpa_config is called
- THEN the merged RPA has tags ["v1", "v2", "stage"] (common first, then RPA)

#### Scenario: normalize_rpa_config tags only in common or only in RPA
- GIVEN tags in only one side (common or RPA)
- WHEN normalize_rpa_config is called
- THEN those tags are used as-is without error

#### Scenario: normalize_rpa_config invalid format
- GIVEN an RPA config that is neither list nor dict-with-rpas (e.g., a string, an empty dict)
- WHEN normalize_rpa_config is called
- THEN an empty list is returned

#### Scenario: normalize_component_config old format passthrough
- GIVEN a component config that is a plain list
- WHEN normalize_component_config is called
- THEN the same list is returned unchanged

#### Scenario: normalize_component_config new format merges common fields
- GIVEN a config with "common" top-level fields and "items"
- WHEN normalize_component_config is called
- THEN each component has common fields merged, with component values overriding

#### Scenario: normalize_component_config pipelinerun defaults merge
- GIVEN common.pipelinerun with defaults and a component with its own pipelinerun list
- WHEN normalize_component_config is called
- THEN each pipelinerun entry has common.pipelinerun merged in
- AND component pipelinerun values override common pipelinerun values

#### Scenario: normalize_component_config pipelinerun from common only
- GIVEN common.pipelinerun with defaults and a component with no pipelinerun field
- WHEN normalize_component_config is called
- THEN the component gets a single-element pipelinerun list from common defaults

#### Scenario: normalize_component_config rpa_values merge
- GIVEN common.rpa_values and a component with partial rpa_values
- WHEN normalize_component_config is called
- THEN common rpa_values are merged with component overrides winning

### Requirement: Property-based validation of generated KRD YAML
The system MUST validate structural properties of generated KRD resources, independent of exact content matching. These checks run on freshly generated output and catch malformed resources even when snapshots are regenerated.

#### Scenario: Application resources have required fields
- GIVEN any generated application YAML file
- WHEN the file is parsed
- THEN it MUST contain apiVersion, kind ("Application"), metadata.name, and spec.displayName
- AND metadata.name matches the versioned application name

#### Scenario: Component resources have required fields
- GIVEN any generated component YAML file
- WHEN the file is parsed
- THEN it MUST contain apiVersion, kind ("Component"), metadata.name, metadata.annotations, spec.application, spec.componentName, spec.source.git.url, and spec.source.git.revision
- AND spec.application matches the versioned application name

#### Scenario: ImageRepository resources have required fields
- GIVEN any generated imagerepository YAML file
- WHEN the file is parsed
- THEN it MUST contain apiVersion, kind ("ImageRepository"), metadata.name, and metadata.labels

#### Scenario: ReleasePlan resources have required fields
- GIVEN any generated releaseplan YAML file
- WHEN the file is parsed
- THEN it MUST contain apiVersion, kind ("ReleasePlan"), metadata.name, spec.application, and spec.target
- AND spec.application matches the versioned application name

#### Scenario: ReleasePlanAdmission resources have required fields
- GIVEN any generated releaseplanadmission YAML file
- WHEN the file is parsed
- THEN it MUST contain apiVersion, kind ("ReleasePlanAdmission"), metadata.name, spec.applications, spec.policy, and spec.data

#### Scenario: Kustomization files are valid
- GIVEN any generated kustomization.yaml
- WHEN the file is parsed
- THEN it MUST contain apiVersion, kind ("Kustomization"), namespace, and resources
- AND resources is a sorted list with no duplicates
- AND every entry in resources corresponds to a file that exists in the same directory

#### Scenario: Component revision matches branch
- GIVEN a definition with branch "rhoai-2.23"
- WHEN KRD is generated
- THEN every component resource has spec.source.git.revision equal to "rhoai-2.23"

#### Scenario: Branch-aware naming is consistent across resources
- GIVEN a definition with branch "rhoai-2.23" and application "my-app"
- WHEN KRD is generated
- THEN the application name is "my-app-rhoai-2-23" across all resources
- AND component names include the "-rhoai-2-23" suffix
- AND release plan names include the "-rhoai-2-23" suffix

### Requirement: Property-based validation of generated pipelinerun YAML
The system MUST validate structural properties of generated Tekton pipelinerun files.

#### Scenario: Pipelinerun files have required Tekton structure
- GIVEN any generated pipelinerun YAML file
- WHEN the file is parsed
- THEN it MUST contain apiVersion ("tekton.dev/v1"), kind ("PipelineRun"), metadata, and spec
- AND metadata MUST contain name, namespace, labels, and annotations
- AND spec MUST contain pipelineRef and params

#### Scenario: CEL expressions reference correct branch
- GIVEN a definition with branch "test-branch"
- WHEN pipelinerun is generated
- THEN on-pull-request files have CEL annotations referencing "test-branch" as target_branch
- AND on-push files (without tag prefixes) reference "test-branch" as target_branch

#### Scenario: CEL path expressions use pathChanged correctly
- GIVEN cel_path_changed entries ["ci", "context/app/***"]
- WHEN pipelinerun is generated
- THEN the CEL expression contains pathChanged() calls for each entry
- AND pathChanged() is not called with empty strings

#### Scenario: CEL variant placeholder replacement
- GIVEN cel_path_changed entries containing "{variant}" and variant "my-variant"
- WHEN pipelinerun is generated
- THEN "{variant}" is replaced with "my-variant" in all CEL expressions
- AND no literal "{variant}" remains in the output

#### Scenario: Labels are correctly constructed
- GIVEN a component with prod_repository "registry.redhat.io/rhelai3/bootc-cuda-rhel9"
- WHEN pipelinerun is generated
- THEN labels include "name=rhelai3/bootc-cuda-rhel9"
- AND labels include "com.redhat.component=rhelai3/bootc-cuda-rhel9-container"

#### Scenario: Labels filtered when use_build_args is true
- GIVEN a full-container pipelinerun with use_build_args=true
- WHEN pipelinerun is generated
- THEN name and com.redhat.component labels are removed from pipelinerun labels
- AND cpe label (if present) is kept

#### Scenario: CPE label format is valid
- GIVEN a definition with cpe config (name, rhel_target) and a prod RPA with product_version "1.0.0"
- WHEN pipelinerun is generated
- THEN the CPE label follows the format "cpe:/a:redhat:{name}:{major.minor}::{rhel_target}"
- AND only major.minor from product_version is used (not the patch)

#### Scenario: Both pull-request and push files are generated
- GIVEN any pipelinerun component config
- WHEN pipelinerun is generated
- THEN exactly two files are created: {component}-on-pull-request.yaml and {component}-on-push.yaml

### Requirement: Property-based validation of developer portal YAML
The system MUST validate developer portal version file structure.

#### Scenario: Version files have required fields
- GIVEN any generated developer portal version YAML
- WHEN the file is parsed
- THEN it MUST contain versionName, ga, hidden, and releaseDate (camelCase)

#### Scenario: product_slug validation
- GIVEN a product_slug containing "/" or "\"
- WHEN developer portal generation is attempted
- THEN a ValueError is raised

#### Scenario: Missing required version fields
- GIVEN a version entry missing version_name, ga, hidden, or release_date
- WHEN developer portal generation is attempted
- THEN a ValueError is raised listing the missing fields

#### Scenario: Common fields are inherited
- GIVEN a common section with ga=true and a version without ga
- WHEN developer portal generation runs
- THEN the version inherits ga=true from common

### Requirement: Snapshot tests with explicit update gate
The system MUST support golden file comparison tests that do NOT auto-update. Snapshots can only be updated by running pytest with a --update-snapshots flag.

#### Scenario: Snapshot matches
- GIVEN existing snapshot files and no changes to templates or logic
- WHEN tests run without --update-snapshots
- THEN tests pass by comparing generated output to snapshots

#### Scenario: Snapshot mismatch without flag
- GIVEN a template change that alters output
- WHEN tests run without --update-snapshots
- THEN the test FAILS with a clear diff showing expected vs actual

#### Scenario: Snapshot update with flag
- GIVEN a template change that alters output
- WHEN tests run with --update-snapshots
- THEN snapshot files are overwritten with new output
- AND the test passes
- AND the updated snapshots appear in git diff for human review

### Requirement: Integration test scenario validation
The system MUST validate that integration test scenario (ITS) resources are correctly generated.

#### Scenario: ITS resources have required fields
- GIVEN any generated integration test scenario YAML
- WHEN the file is parsed
- THEN it MUST contain apiVersion, kind ("IntegrationTestScenario"), metadata.name, spec.application, and spec.contexts

#### Scenario: ITS branch-aware naming
- GIVEN a definition with branch "rhoai-2.23", application "my-app", and ITS name "check-ecp"
- WHEN ITS resources are generated
- THEN the ITS name is "my-app-rhoai-2-23-check-ecp"

#### Scenario: ITS releasePlanAdmissionName auto-suffixed
- GIVEN a non-main branch and a param with name "releasePlanAdmissionName"
- WHEN ITS resources are generated
- THEN the param value has the normalized branch suffix appended
- AND if the value already has the suffix, it is not doubled

#### Scenario: ITS components default to all
- GIVEN an ITS config with no "components" field
- WHEN ITS resources are generated
- THEN all components from the definition are included

### Requirement: Tech-preview component filtering in RPAs
The system MUST correctly filter components based on RPA type and tech_preview status.

#### Scenario: Stage RPA includes all components
- GIVEN components with mixed tech_preview values and a stage RPA
- WHEN RPA resources are generated
- THEN all components are included regardless of tech_preview

#### Scenario: Tech-preview prod RPA includes only tech-preview components
- GIVEN components with tech_preview=true and tech_preview=false
- AND a prod RPA with "tech-preview" in its name
- WHEN RPA resources are generated
- THEN only tech_preview=true components are included

#### Scenario: Regular prod RPA excludes tech-preview components
- GIVEN components with tech_preview=true and tech_preview=false
- AND a regular prod RPA
- WHEN RPA resources are generated
- THEN only tech_preview=false (or omitted) components are included

#### Scenario: Prod RPA skips full-container components without prod_repository
- GIVEN a full-container component without prod_repository field
- AND a non-stage prod RPA
- WHEN RPA resources are generated
- THEN that component is excluded from the RPA

### Requirement: Recreate mode correctness
The system MUST correctly clean up managed directories when --recreate is used, without destroying non-managed resources.

#### Scenario: Managed subdirectories are removed
- GIVEN an existing application directory with applications/, components/, imagerepositories/, releaseplans/, integrationtests/
- WHEN generation runs with --recreate
- THEN those subdirectories are deleted before regeneration

#### Scenario: Non-managed files are preserved
- GIVEN an existing application directory with a custom subdirectory not in the managed list
- WHEN generation runs with --recreate
- THEN the custom subdirectory is not deleted

### Requirement: Config loading priority
The system MUST load configuration in priority order: CLI args > environment variables > config file (.onboard-config.toml) > defaults.

#### Scenario: CLI overrides environment
- GIVEN KRD_PATH env var set to "/env/path" and --krd-path CLI arg set to "/cli/path"
- WHEN Config is initialized
- THEN config["krd_path"] is "/cli/path"

#### Scenario: Environment overrides config file
- GIVEN KRD_PATH env var set to "/env/path" and .onboard-config.toml with krd_path="/toml/path"
- WHEN Config is initialized with no CLI override for krd_path
- THEN config["krd_path"] is "/env/path"

#### Scenario: Config file overrides defaults
- GIVEN no env var and .onboard-config.toml with krd_path="/toml/path"
- WHEN Config is initialized with no CLI override
- THEN config["krd_path"] is "/toml/path"

#### Scenario: Defaults used when nothing else specified
- GIVEN no env var, no config file, no CLI override
- WHEN Config is initialized
- THEN config["krd_path"] is the default "./output/krd"

### Requirement: collect_config_files handles patterns and directories
The system MUST collect config files from glob patterns and directories, deduplicating and sorting results.

#### Scenario: Glob patterns expand correctly
- GIVEN a pattern "configs/*.yaml" matching 3 files
- WHEN collect_config_files is called
- THEN all 3 files are returned as resolved Path objects

#### Scenario: Config directory scans YAML files
- GIVEN a directory with 2 .yaml files and 1 .txt file
- WHEN collect_config_files is called with that directory
- THEN only the 2 .yaml files are returned

#### Scenario: Hidden files are excluded from directory scan
- GIVEN a directory with ".hidden.yaml" and "_backup.yaml"
- WHEN collect_config_files is called
- THEN hidden and backup files are excluded

#### Scenario: Duplicates are removed
- GIVEN a pattern and directory that both match the same file
- WHEN collect_config_files is called
- THEN the file appears only once

#### Scenario: No matches raises ValueError
- GIVEN patterns and directories that match no files
- WHEN collect_config_files is called
- THEN a ValueError is raised

### Requirement: Release plan and RPA name matching
The system MUST validate that release plans have corresponding RPAs and warn about orphaned RPAs.

#### Scenario: Release plan without matching RPA raises error
- GIVEN a release plan named "prod" but no RPA named "prod"
- WHEN KRD generation runs
- THEN a ValueError is raised listing available RPA names

#### Scenario: RPA without matching release plan produces warning
- GIVEN an RPA named "extra-stage" but no release plan named "extra-stage"
- WHEN KRD generation runs
- THEN a warning is printed but generation continues
