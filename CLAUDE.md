# CLAUDE.md - Development Instructions

This file contains instructions for Claude to work effectively with this repository.

## Project Overview

This is a Python-based tool for onboarding products to the Konflux platform. It generates Kubernetes resources (KRD) and CI/CD configurations (pipelinerun) using Jinja2 templates.

## Development Commands

### Setup with uv
```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies and create virtual environment
uv sync

# Install in development mode
uv pip install -e .
```

### Code Quality
```bash
# Format code
uv run ruff format .

# Lint code  
uv run ruff check .

# Type checking
# No mypy configured - ask user if needed
```

### Testing
```bash
# Run all tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Run specific test
uv run pytest tests/test_generation.py::TestGeneration::test_krd_generation -v

# Run tests for specific pipeline type
uv run pytest tests/test_generation.py -k "full-container" -v
uv run pytest tests/test_generation.py -k "disk-image" -v
```

### Updating Expected Test Outputs
When templates or generation logic changes, the expected test outputs need to be regenerated:

**When to regenerate:**
- After modifying any Jinja2 templates in `templates/KRD/` or `templates/pipelinerun/`
- After changes to `onboard-product.py` that affect generated output format
- After rebasing on main if upstream template changes occurred
- When tests fail due to formatting/content differences (not logic errors)

**How to regenerate:**
```bash
# Clean existing expected outputs
rm -rf tests/expected/full-container/* tests/expected/disk-image/*
mkdir -p tests/expected/full-container/{krd,pipelinerun} tests/expected/disk-image/{krd,pipelinerun}

# Regenerate full-container expected outputs
KRD_PATH="$(pwd)/tests/expected/full-container/krd/" \
GITLAB_REPO_PATH="$(pwd)/tests/expected/full-container/pipelinerun/" \
uv run python onboard-product.py --config tests/configs/test-full-container.yaml --mode both

# Regenerate disk-image expected outputs
KRD_PATH="$(pwd)/tests/expected/disk-image/krd/" \
GITLAB_REPO_PATH="$(pwd)/tests/expected/disk-image/pipelinerun/" \
uv run python onboard-product.py --config tests/configs/test-disk-image.yaml --mode both

# Verify tests pass
uv run pytest tests/test_generation.py -v
```

**Important:** Always regenerate BOTH pipeline types and run tests to ensure consistency. Commit the updated expected outputs with your template/logic changes.

### Running the Tool

Product configurations are maintained in a separate repository: https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-onboarding-configs

```bash
# Clone the configs repository (if not already cloned)
git clone https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-onboarding-configs.git

# Single config file (traditional)
uv run python onboard-product.py --config /path/to/aipcc-product-onboarding-configs/llama-stack/llama-stack-rhoai-2-23.yaml

# Multiple configs with glob patterns
uv run python onboard-product.py --config "/path/to/configs/*.yaml"
uv run python onboard-product.py --config "configs/app-*.yaml" --config "configs/service-*.yaml"

# Process entire directory
uv run python onboard-product.py --config-dir /path/to/configs/llama-stack/

# Combined approach
uv run python onboard-product.py --config critical.yaml --config "optional-*.yaml" --config-dir shared/

# With --recreate to avoid orphaning resources
uv run python onboard-product.py --config-dir /path/to/configs/ --recreate

# Mode options
uv run python onboard-product.py --config config.yaml --mode krd          # Only KRD
uv run python onboard-product.py --config config.yaml --mode pipelinerun  # Only pipelinerun
uv run python onboard-product.py --config config.yaml --mode both         # Both (default)
```

## Architecture Notes

### Template System
- Uses Jinja2 with custom delimiters `[[` and `]]` to avoid YAML conflicts
- KRD templates in `templates/KRD/`:
  - `application.yaml.j2`, `component.yaml.j2`, `imagerepository.yaml.j2`, `releaseplan.yaml.j2`, `releaseplanadmission.yaml.j2`
  - IntegrationTestScenario templates: `its-ecp.yaml.j2`, `its-konflux-data.yaml.j2`
- Pipelinerun templates in `templates/pipelinerun/`:
  - `full-container.yaml.j2` - Standard container builds (pathInRepo: pipelines/full-container.yaml)
  - `disk-image.yaml.j2` - Disk image builds (pathInRepo: pipelines/disk-image.yaml)
- Template selection based on `pipeline` field in pipelinerun configuration
- Pipelinerun supports configurable parameters: `path_context`, `snyk_project_name`, `snyk_org`, `build_platforms`

### Branch-Aware Naming
- Main branch: Uses base names (e.g., "llama-stack")
- Other branches: Adds branch suffix (e.g., "llama-stack-rhoai-2-23")
- Ensures separate resource management for different product versions

### Dependencies
- `ruamel.yaml>=0.17.0` - YAML processing with formatting preservation
- `jinja2>=3.0.0` - Template rendering
- `pytest>=7.0.0` - Testing framework (dev dependency)

### Testing Strategy
- End-to-end regression tests in `tests/test_generation.py`
- Two test classes:
  - `TestGeneration`: Tests single-config scenarios (backward compatibility)
  - `TestMultiConfig`: Tests multi-config scenarios (glob patterns, --config-dir)
- Test configs:
  - `tests/configs/test-full-container.yaml` - Full container pipeline test
  - `tests/configs/test-disk-image.yaml` - Disk image pipeline test
  - `tests/configs/multi-config-test/` - Directory with 3 minimal configs for multi-config tests
- Expected outputs stored in `tests/expected/{pipeline-type}/{krd,pipelinerun}/`
- Tests generate output to temporary directories and compare with expected files
- Parametrized tests for both pipeline types (full-container and disk-image)
- Tests cover KRD generation, pipelinerun generation, end-to-end scenarios, and multi-config processing

**Adding new tests:**
1. For new features affecting output, add to `TestGeneration` class
2. For new config handling features, add to `TestMultiConfig` class
3. Use `setup_method()` to create temp directories, `teardown_method()` to clean up
4. Import functions from onboard-product.py via importlib (due to dash in filename)
5. Use `compare_directories()` helper to check output matches expected

### Configuration
Environment variables for paths:
- `TEMPLATES_DIR` - KRD templates directory (default: templates/KRD)
- `KRD_PATH` - Output path for KRD resources (default: /home/jrusz/repos/konflux-release-data/)
- `CLUSTER` - Target Kubernetes cluster (default: stone-prod-p02)
- `PIPELINERUN_TEMPLATE_DIR` - Pipelinerun templates (default: templates/pipelinerun)
- `GITLAB_REPO_PATH` - GitLab repositories base path (default: /home/jrusz/other-repos/)

### Output Structure
KRD resources organized as:
```
{KRD_PATH}/tenants-config/cluster/{cluster}/tenants/{tenant}/{app}/{branch}/
├── applications/{app}.yaml
├── components/{component}.yaml
├── imagerepositories/{component}.yaml
├── releaseplans/{releaseplan}.yaml
└── integrationtests/{its_name}.yaml  (optional, only when integration_test_scenarios defined)
```

Pipelinerun resources as:
```
{GITLAB_REPO_PATH}/{org}/{repo}/.tekton/
├── {component}-on-pull-request.yaml
└── {component}-on-push.yaml
```

## Configuration Files
- Product configs are maintained in a separate repository: https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-onboarding-configs
- Organized by product family: llama-stack/, rhaiis/, rhelai/, base-images/, examples/
- Examples: examples/basic-product.yaml, examples/advanced-product.yaml
- Production configs: llama-stack/llama-stack-rhoai-2-23.yaml, rhaiis/rhaiis-3-2-4.yaml, etc.

### Repository Configuration
- Components require two repository fields:
  - `stage_repository`: Used in ReleasePlanAdmission when RPA name contains "stage" (for full-container)
  - `prod_repository`: Used in ReleasePlanAdmission when RPA name contains "prod" (for full-container)
- ImageRepository uses constructed path: `{tenant}/{application}/{component}`
- Template automatically selects appropriate repository based on RPA name pattern

### RPA Configuration by Pipeline Type
- **ReleasePlanAdmission template selection** based on component pipeline types:
  - All components in an application must use the same pipeline type
  - `full-container`: Standard container release with repository mappings
  - `disk-image`: Disk image release with CDN staging and content gateway configuration
- **Disk-Image Specific Requirements**:
  - Components must include `rpa_values` section with required fields
  - Required fields: `destination`, `version`, `filename`, `source`, `productName`, `productCode`, `productVersion`, `filePrefix`
  - Optional field: `contentType` (defaults to "disk-image")
  - RPA includes `cdn: env` section (stage/prod based on RPA name)
  - No `defaults` section or repository mappings

### Service Account Configuration
- Each ReleasePlanAdmission requires a `service_account` field
- Used for pipeline authentication and registry push permissions
- Common pattern: `release-registry-{product-name}` (e.g., "release-registry-llama-stack")
- Must exist in the target cluster with appropriate RBAC permissions

### Pipeline Path Configuration
- Each ReleasePlanAdmission requires a `pipeline_path` field
- Specifies the path to the release pipeline in the konflux-ci/release-service-catalog repository
- Common paths:
  - Stage: `pipelines/managed/push-to-external-registry/push-to-external-registry.yaml`
  - Production: `pipelines/managed/rh-advisories/rh-advisories.yaml`
- Path is relative to the release-service-catalog repository root

### Pipelinerun Configuration Options
- **Pipeline Type Selection** (required `pipeline` field):
  - `"full-container"`: Standard container builds with build args, variants, skip-checks
  - `"disk-image"`: Disk image builds with hardcoded image-type, config-toml, bib-file
- **Shared Optional Parameters** (both pipeline types):
  - `path_context`: Build context directory (default: `"./context/"`)
  - `snyk_project_name`: Snyk project name for security scanning (default: `"ai-red-hat-inference-server"`)
  - `snyk_org`: Snyk organization ID (default: `"98e4f46e-334c-414b-b444-43361f404b2f"`)
  - `build_platforms`: Target architectures for multi-platform builds
  - `timeouts`: Pipeline execution time limits
- **Full-Container Specific Parameters**:
  - `build_args_file`, `additional_build_secret`, `variant`, `skip-checks`
- **Disk-Image Specific**: Uses hardcoded values for `image-type: iso`, `config-toml: config/config-iso.toml`, `bib-file: bib.yaml`
- All paths are relative to the component repository root

### IntegrationTestScenario Configuration
Integration tests are configured using the `integration_test_scenarios` array in each product definition. The tool generates IntegrationTestScenario resources based on reusable templates.

**Configuration Structure**:
```yaml
definitions:
  - application: my-app
    # ... other fields ...
    integration_test_scenarios:
      - template: its-ecp                    # Required: template name (its-ecp, its-konflux-data)
        name: check-stage-ecp                # Required: base name for the test
        optional: true                       # Optional: mark test as optional (default: false)
        components:                          # Optional: specific components to test (default: all components)
          - component-1
          - component-2
        params:                              # Required: test-specific parameters
          - name: POLICY_CONFIGURATION
            value: tenant/policy-name
          - name: TIMEOUT
            value: 40m0s
        # Any other fields are passed through to the template
```

**Available Templates**:
- `its-ecp`: Enterprise Contract Policy tests (uses konflux-ci/build-definitions)
- `its-konflux-data`: Custom GitLab-based tests (uses rhel-ai/konflux-data)

**Branch-Aware Naming**:
- Main branch: `{app_name}-{its_name}` (e.g., "llama-stack-check-stage-ecp")
- Other branches: `{app_name}-{normalized_branch}-{its_name}` (e.g., "llama-stack-rhoai-2-23-check-stage-ecp")

**Component Selection**:
- If `components` field is omitted, all components from the definition are included
- If specified, only listed components are included (names are automatically versioned for branches)

**Template Parameters** (passed to Jinja2 templates):
- `its_name`: Generated name with branch suffix
- `application_name`: Versioned application name
- `components`: List of component dicts with versioned names
- `path_in_repo`: Pipeline path from config (default varies by template)
- All other fields from config (e.g., `optional`, `params`) are passed through

**Output**:
- Files created in `{tenant}/{app}/{branch}/integrationtests/{its_name}.yaml`
- Directory only created when scenarios are defined
- Non-ECP tests (files without "ecp" in name) are preserved during `--recreate`

**Example** (see `tests/configs/test-full-container.yaml` for complete example):
```yaml
integration_test_scenarios:
  - template: its-ecp
    name: check-stage-ecp
    optional: true
    params:
      - name: POLICY_CONFIGURATION
        value: tenant/stage-policy
      - name: SINGLE_COMPONENT
        value: "true"
```

## Code Structure and Key Functions

### Main Entry Point (main() function)
Located at line ~740-910 in onboard-product.py:
1. **Argument parsing** (lines 768-850): Sets up CLI arguments including --config, --config-dir, --mode, --recreate, etc.
2. **Config validation** (lines 848-850): Ensures at least one of --config or --config-dir is specified
3. **Configuration loading** (lines 852-862): Loads tool configuration (paths, cluster) from CLI, env vars, or TOML file
4. **Config file collection** (lines 864-886): Calls collect_config_files(), loads YAML, merges definitions
5. **Resource generation** (lines 888-905): Calls render_krd_templates() and/or render_pipelinerun_templates() based on mode

### Key Helper Functions

**collect_config_files(config_patterns, config_dir)** - Lines 113-160
- Collects config files from glob patterns and/or directory
- Handles both --config patterns (can be globs or literal paths) and --config-dir
- Uses `glob.glob()` with recursive=True for pattern matching
- Resolves all paths to absolute using `.resolve()` to detect duplicates
- Filters out hidden files (starting with `.`, `_`, `~`) from directories
- Returns sorted list of unique Path objects
- Raises ValueError if no configs found or directory doesn't exist

**render_krd_templates(data, template_dir, krd_path, cluster, recreate)** - Lines 573-1054
- Processes `definitions` array from merged config data
- For each definition, extracts tenant, application, branch
- **Key behavior with --recreate** (lines 619-689): Selective deletion approach
  - Deletes managed subdirectories: `applications/`, `components/`, `imagerepositories/`, `releaseplans/`
  - For `integrationtests/`: Deletes only ECP test files (containing "ecp"), preserves non-ECP tests
  - Removes `kustomization.yaml` (regenerated at the end)
- Creates directory structure: applications/, components/, imagerepositories/, releaseplans/, integrationtests/ (conditional)
- Generates Application resource (one per application)
- Generates Component and ImageRepository resources (one per component)
- Generates ReleasePlan resources (supports `autorelease_annotation` and `author` fields)
- Generates ReleasePlanAdmission resources in separate directory tree
- **Component filtering for prod RPAs** (lines 870-877): Skips components without `prod_repository` for production RPAs
- **IntegrationTestScenario generation** (lines 941-1007): Generates ITS from `integration_test_scenarios` array
  - Only creates integrationtests/ directory when scenarios are defined
  - Uses template-driven approach (its-ecp.yaml.j2, its-konflux-data.yaml.j2)
  - Supports branch-aware naming, component filtering, and parameter pass-through
- **Non-ECP test inclusion** (lines 1009-1020): Scans for existing non-ECP tests and includes in kustomization
- Uses `get_directory_resources()` for dynamic kustomization.yaml generation

**render_pipelinerun_templates(data, template_dir, gitlab_repo_path)** - Lines 277-390
- Generates .tekton/ files in component repositories
- For each component, determines tekton_dir from local_repo_path or parsed GitLab URL
- Generates two pipelinerun files per component: -on-pull-request.yaml and -on-push.yaml
- Template selection based on pipeline type (full-container.yaml.j2 or disk-image.yaml.j2)
- Uses base_component_name (not versioned) for pipelinerun filenames

**get_application_name(base_name, branch)** - Lines 163-187
- Returns base_name for "main" branch
- Returns "{base_name}-{normalized_branch}" for other branches
- Example: "llama-stack" on "main" → "llama-stack", on "rhoai-2.23" → "llama-stack-rhoai-2-23"

**get_component_name(base_name, branch)** - Lines 189-208
- Same logic as get_application_name but for components
- Ensures component names match their application versions

**canonicalize(value)** - Lines 44-46
- Converts dots to dashes for filename-safe names
- Used for branch names: "rhoai-2.23" → "rhoai-2-23"

**create_kustomization(directory, files, tenant)** - Lines 50-82
- Creates or updates kustomization.yaml in a directory
- Merges with existing resources if file exists
- Used for applications/, components/, imagerepositories/, releaseplans/, integrationtests/ directories

**get_directory_resources(directory)** - Lines 99-110
- Scans directory for files/folders to include in kustomization
- Filters out hidden files and kustomization.yaml itself
- Returns sorted list of resource names
- Used to dynamically generate base_path kustomization.yaml (avoids hardcoded integrationtests entry)

### Important Implementation Details

**Multi-Config Merge Logic** (lines 864-886):
```python
# Collect all config files
config_files = collect_config_files(args.config_patterns, args.config_dir)

# Load and merge definitions from all configs
all_definitions = []
for config_file in config_files:
    data = yaml.load(f)
    definitions = data.get("definitions", [])
    all_definitions.extend(definitions)

# Create merged data structure
merged_data = {"definitions": all_definitions}
```
- Concatenates definitions arrays from all config files
- No conflict detection needed per user requirement (each config defines unique tenant/app/branch)
- Single pass through render functions processes all definitions

**--recreate Flag: Selective Deletion** (lines 436-501):
```python
# Deletes managed subdirectories
subdirs_to_delete = ["applications", "components",
                     "imagerepositories", "releaseplans"]
for subdir in subdirs_to_delete:
    subdir_path = os.path.join(base_path, subdir)
    if os.path.exists(subdir_path):
        shutil.rmtree(subdir_path)

# Special handling for integrationtests: delete only ECP files
for filename in os.listdir(its_dir):
    if filename.endswith(".yaml") and filename != "kustomization.yaml":
        if "ecp" in filename:
            os.remove(file_path)  # Delete ECP tests
        # Keep non-ECP tests
```
- Selectively deletes managed subdirectories within `{tenant}/{app}/{branch}/`
- Does NOT delete entire application directory
- Preserves non-ECP integration tests (files without "ecp" in name)
- Safe to use with multi-config - only removes managed resources being regenerated

**Component Filtering for Prod RPAs** (lines 545-547):
```python
# For prod RPAs (non-stage), skip components without prod_repository
if not is_stage_rpa and "prod_repository" not in component:
    continue
```
- Stage RPAs include all components regardless of repository config
- Prod RPAs only include components with `prod_repository` field
- Prevents incomplete production releases

**Conditional IntegrationTests Directory** (lines 941-1026):
- Directory only created when `integration_test_scenarios` array has entries in the definition
- Uses template-driven generation (its-ecp, its-konflux-data templates)
- Uses `get_directory_resources()` to dynamically build kustomization resources
- No hardcoded "integrationtests" entry in kustomization.yaml

### Branch-Aware Naming Pattern
Every definition processes branch to create versioned names:
```python
branch, normalized_branch, versioned_app_name = get_branch_info(definition)
# branch = "rhoai-2.23" (original)
# normalized_branch = "rhoai-2-23" (canonicalized)
# versioned_app_name = "llama-stack-rhoai-2-23" (if not main)
```

Used for:
- Application name: `versioned_app_name`
- Component names: `get_component_name(base_name, branch)`
- Directory structure: `{app_name}/{normalized_branch}/`
- Release plan names: `{base_name}-{normalized_branch}` (if not main)

### Template Rendering
- Jinja2 with custom delimiters `[[` and `]]` to avoid YAML conflicts
- Template loading: `env = create_jinja_env(template_dir)`
- Rendering: `template.render(**params)` with specific parameters per resource type
- All rendered content written with trailing newline via `write_with_newline()`

### Error Handling Patterns
- Config file collection raises ValueError with descriptive messages
- Template rendering errors propagate with file context
- Path validation before directory operations
- Informative print statements for debugging (which files loaded, how many definitions, etc.)

## Common Modification Patterns

### Adding a New CLI Argument
1. Add parser argument in main() around line 768-840
2. Add to cli_overrides dict when creating Config object (line 853-862)
3. Use via `args.your_arg` or `config['your_arg']`

### Adding a New Resource Type
1. Create Jinja2 template in templates/KRD/ with `[[` `]]` delimiters
2. Add directory creation in render_krd_templates() (like apps_dir, components_dir)
3. Load template: `template = env.get_template("yourresource.yaml.j2")`
4. Render with appropriate parameters
5. Add to kustomization via `create_kustomization()` or `get_directory_resources()`

### Modifying Component Filtering Logic
- See lines 525-577 in render_krd_templates() for RPA component filtering
- Current filters: tech_preview, stage vs prod, prod_repository availability
- Add new filters in the component iteration loop before `updated_components.append()`

### Changing Output Directory Structure
- KRD base_path defined at lines 392-401
- Modify path components in os.path.join() chain
- Update kustomization creation calls to match new structure
- Regenerate test expected outputs

### Adding Config Validation
- Add validation in main() after loading merged_data (around line 886)
- Check for required fields, valid combinations, etc.
- Raise ValueError with descriptive message
- Consider adding validation helper functions

## Recent Feature Additions

### Multi-Config Support (AIPCC-8593)
**Problem solved**: Using `--recreate` with single config orphaned resources from other configs sharing same application.

**Changes made**:
1. Added glob pattern support to `--config` argument
2. Added new `--config-dir` option to process all YAML files in a directory
3. Implemented config merging logic to process multiple configs in single run
4. Updated argument parsing to support `action="append"` for multiple --config flags
5. Added `collect_config_files()` helper function with duplicate detection via path resolution

**Key implementation**:
- `--config` now accepts glob patterns like `"configs/*.yaml"` (quotes prevent shell expansion)
- Multiple `--config` flags can be combined: `--config "app-*.yaml" --config "service-*.yaml"`
- `--config-dir` processes all .yaml files in directory (filters hidden files)
- All approaches can be combined: `--config file.yaml --config "*.yaml" --config-dir dir/`
- Definitions from all configs merged into single array before processing
- Safe with `--recreate` - only removes directories for apps being regenerated

**Testing**:
- Added `tests/configs/multi-config-test/` with 3 minimal test configs
- Added `TestMultiConfig` class with 7 tests for glob, dir, combined, duplicates, errors
- All existing tests still pass (backward compatibility verified)

### Component Filtering & Conditional Directories (AIPCC-8593)
**Prod repository filtering**:
- Components without `prod_repository` field automatically excluded from production RPAs
- Stage RPAs include all components regardless
- Prevents incomplete production releases

**Conditional integrationtests directory**:
- Only created when `integration_test_scenarios` array has entries in the definition
- Uses template-driven generation (its-ecp, its-konflux-data templates)
- Uses dynamic `get_directory_resources()` instead of hardcoded kustomization entry
- Keeps output clean when integration tests not configured

**--recreate flag (updated to selective deletion)**:
- Selectively deletes managed subdirectories: applications/, components/, imagerepositories/, releaseplans/
- For integrationtests/: Deletes only ECP test files, preserves non-ECP tests
- Prevents orphaned component/imagerepository files when components removed from config
- Scoped deletion - only removes managed resources, not entire application directory

### Recent Improvements (2025-01)

**ReleasePlan autorelease annotation support**:
- Added `autorelease_annotation` boolean field to release_plan configuration
- When `true`: Generates annotation with component list: `UpdatedComponentIs('comp1') || UpdatedComponentIs('comp2')`
- When `false` (default): Generates label with boolean value
- Added `author` optional field for release plan author label
- Template: `templates/KRD/releaseplan.yaml.j2`

**IntegrationTestScenario template-driven generation**:
- New `integration_test_scenarios` configuration array in product definitions
- Template-based approach with its-ecp.yaml.j2 and its-konflux-data.yaml.j2
- Branch-aware naming: `{app}-{branch}-{test_name}` or `{app}-{test_name}` for main
- Flexible component selection and parameter pass-through
- Implementation: Lines 941-1007 in render_krd_templates()

**Template quote unification**:
- Unified all templates to use double quotes consistently
- Changed from mixed single/double quotes to double quotes only
- Affects all 9 templates: 7 in templates/KRD/ (including 2 ITS templates) and 2 in templates/pipelinerun/
- Improves consistency and readability

## Troubleshooting Common Issues

### Tests fail after code changes
1. Check if output format changed (intentionally or not)
2. If intentional, regenerate expected outputs (see "Updating Expected Test Outputs")
3. If unintentional, review code changes for bugs
4. Run single test with `-v` flag to see detailed diff

### Glob patterns not matching files
1. Use quotes around glob patterns: `--config "*.yaml"` not `--config *.yaml`
2. Check if shell is expanding pattern before script sees it
3. Use absolute paths or paths relative to current directory
4. Test pattern with `ls` command first: `ls configs/*.yaml`

### --recreate deleting too much / too little
- Deletes only `{tenant}/{app}/{branch}/` directory, check your config's tenant/app/branch values
- Multiple configs with same tenant/app/branch will conflict (last one wins)
- Use `--config-dir` with all related configs to process together

### Import errors in tests
- onboard-product.py has dash in filename, must use importlib
- See existing test setup for import pattern
- Import functions individually: `render_krd_templates = onboard_product.render_krd_templates`

### Pipelinerun files in wrong location
- Check `local_repo_path` in component config (overrides GitLab URL parsing)
- Verify GitLab URL format: `https://gitlab.com/{org}/{repo}`
- Check GITLAB_REPO_PATH environment variable or --gitlab-path argument