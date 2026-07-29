# AIPCC Product Management

Automated tools for onboarding new products to the Konflux platform. Given a product's source repository and registry destinations, this tool generates all the Kubernetes resources and CI/CD configurations needed to get builds and releases running.

## Features

- **KRD Generation**: Creates Konflux Release Data resources (Application, Component, ImageRepository, ReleasePlan, ReleasePlanAdmission)
- **Pipelinerun Generation**: Generates Tekton CI/CD pipeline configurations for pull requests and push events
- **Multi-Pipeline Support**: Supports both full-container and disk-image pipeline types
- **Branch-Aware**: Supports separate configurations for main development and maintenance branches
- **Template-Based**: Uses Jinja2 templates for flexible resource generation
- **Flexible Configuration**: Configure via CLI arguments, TOML files, environment variables, or sensible defaults
- **Smart Component Filtering**: Automatically separates tech-preview from GA components in ReleasePlanAdmissions, and skips components without `prod_repository` from production RPAs
- **CPE Label Injection**: Automatically generates CPE labels for pipelinerun files from prod RPA annotation data
- **Clean Regeneration**: `--recreate` flag removes old resources before generation to prevent orphaned files
- **Conditional Integration Tests**: Only creates `integrationtests/` directory when integration test scenarios are configured

## Requirements

- **Python 3.11 or later**
- **uv** (Python package manager)

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd aipcc-product-management

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies and create virtual environment
uv sync
```

### Basic Usage

Product configurations are maintained in a separate repository: [aipcc-product-management-configs](https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-management-configs)

```bash
# Clone the configs repository
git clone https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-management-configs.git

# Generate both KRD and pipelinerun resources
uv run python onboard-product.py --config /path/to/aipcc-product-management-configs/llama-stack/llama-stack-rhoai-2-23.yaml

# Generate only KRD resources
uv run python onboard-product.py --config /path/to/aipcc-product-management-configs/examples/basic-product.yaml --mode krd

# Generate only pipelinerun resources
uv run python onboard-product.py --config /path/to/aipcc-product-management-configs/examples/basic-product.yaml --mode pipelinerun

# Process multiple configs using glob pattern
uv run python onboard-product.py --config "/path/to/aipcc-product-management-configs/llama-stack/*.yaml"

# Process all configs in a directory
uv run python onboard-product.py --config-dir /path/to/aipcc-product-management-configs/llama-stack

# Combine multiple patterns and directories
uv run python onboard-product.py --config "/path/to/configs/app1/*.yaml" --config "/path/to/configs/app2/*.yaml" --config-dir /path/to/configs/shared
```

### Using with Podman/Docker (No Python Required)

A pre-built container image is published automatically from the main branch:

- **Quay.io**: `quay.io/aipcc-cicd/aipcc-product-management:latest`

```bash
# Clone the configs repository (if not already cloned)
git clone https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-management-configs.git

# Pull the pre-built image
podman pull quay.io/aipcc-cicd/aipcc-product-management:latest

# Generate both KRD and pipelinerun resources
podman run --rm --userns=keep-id:uid=1001,gid=1001 \
  -v /path/to/aipcc-product-management-configs:/configs:ro \
  -v /path/to/konflux-release-data:/krd \
  -v /path/to/gitlab-repos:/repos \
  -e KRD_PATH=/krd \
  -e GITLAB_REPO_PATH=/repos \
  quay.io/aipcc-cicd/aipcc-product-management:latest \
  --config /configs/llama-stack/llama-stack-rhoai-2-23.yaml

# Generate only pipelinerun resources
podman run --rm --userns=keep-id:uid=1001,gid=1001 \
  -v /path/to/aipcc-product-management-configs:/configs:ro \
  -v /path/to/gitlab-repos:/repos \
  -e GITLAB_REPO_PATH=/repos \
  quay.io/aipcc-cicd/aipcc-product-management:latest \
  --config /configs/llama-stack/llama-stack-rhoai-2-23.yaml --mode pipelinerun

# Build your own image instead
podman build -t onboard-product:latest .
```

**Important Notes:**
- **User namespace mapping**: Use `--userns=keep-id:uid=1001,gid=1001` to map your user to the container user (UID 1001). This ensures the container can write to your mounted directories without permission issues.
- **Mount configs**: Mount the configs repository with `-v /path/to/aipcc-product-management-configs:/configs:ro` (read-only).
- **Mount output directories**: Mount destination directories where you want files generated (KRD repo, GitLab repos).
- **Environment variables**: Use `-e` to set paths inside the container (e.g., `-e GITLAB_REPO_PATH=/repos`).
- **Docker alternative**: If using Docker instead of Podman, replace `podman` with `docker` and adjust the `--userns` flag to `--user $(id -u):$(id -g)` if needed.

## Configuration

### Product Configuration Files

Product configurations are maintained in a separate repository: [aipcc-product-management-configs](https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-management-configs)

This repository contains configurations organized by product family:
- `examples/` - Template configs for creating new products (basic and advanced examples)
- `llama-stack/` - Red Hat AI Inference Server (RHOAI component)
- `rhaiis/` - Red Hat AI Inference Server (core platform)
- `rhelai/` - Red Hat Enterprise Linux AI bootable containers
- `base-images/` - Red Hat OpenShift AI base images
- `docling/` - Docling document processing containers
- `test/` - Test repository configurations

See the [configs repository README](https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-management-configs) for details on configuration structure and naming conventions.

### Tool Configuration (Output Paths, Cluster Settings)

The tool supports flexible configuration through multiple methods with the following priority order:

**1. CLI Arguments (Highest Priority)**
```bash
uv run python onboard-product.py \
  --config product.yaml \
  --krd-path ./my-krd-output \
  --gitlab-path ./my-gitlab-repos \
  --cluster stone-prod-p01
```

Available arguments:
- `--config` - Path or glob pattern for config file(s) (can be specified multiple times)
- `--config-dir` - Directory containing multiple config YAML files
- `--mode` - Generation mode: krd, pipelinerun, or both (default: both)
- `--krd-path` - Output path for KRD resources
- `--gitlab-path` - Output path for pipelinerun resources
- `--templates-dir` - KRD templates directory
- `--pipelinerun-templates-dir` - Pipelinerun templates directory
- `--cluster` - Target Kubernetes cluster
- `--settings` - Path to TOML settings file
- `--recreate` - Remove and recreate managed resources before generation (cleans KRD tenant subdirs and `.tekton/` pipelinerun files)
- `--recreate-rpa` - Remove and recreate ReleasePlanAdmission files before generation (tenant-wide scope, see below)

**2. Configuration File**

Create `.onboard-config.toml` in your project directory:

```toml
[paths]
krd_path = "./output/krd"
gitlab_repo_path = "./output/pipelinerun"
krd_templates_dir = "./templates/KRD"
pipelinerun_template_dir = "./templates/pipelinerun"

[cluster]
name = "stone-prod-p02"
```


**3. Environment Variables (Backward Compatible)**
```bash
export KRD_PATH="/path/to/konflux-release-data/"
export GITLAB_REPO_PATH="/path/to/gitlab-repos/"
export CLUSTER="stone-prod-p02"
export KRD_TEMPLATES_DIR="templates/KRD"
export PIPELINERUN_TEMPLATE_DIR="templates/pipelinerun"
```

**4. Sensible Defaults (Lowest Priority)**
- `krd_path`: `./output/krd`
- `gitlab_repo_path`: `./output/pipelinerun`
- `krd_templates_dir`: `./templates/KRD`
- `pipelinerun_template_dir`: `./templates/pipelinerun`
- `cluster`: `stone-prod-p02`

The tool works out of the box with no configuration required.

## Output Structure

### KRD Resources
```
{KRD_PATH}/tenants-config/cluster/{cluster}/tenants/{tenant}/{app}/{branch}/
├── applications/{app}.yaml
├── components/{component}.yaml
├── imagerepositories/{component}.yaml
├── integrationtests/{test}.yaml   # Only created if integration tests configured
└── releaseplans/{releaseplan}.yaml

{KRD_PATH}/config/{cluster}.hjvn.p1/product/ReleasePlanAdmission/{tenant}/
└── {releaseplan}.yaml
```

### Pipelinerun Resources
```
{GITLAB_REPO_PATH}/{org}/{repo}/.tekton/
├── {component}-on-pull-request.yaml
└── {component}-on-push.yaml
```

## Advanced Features

### Clean Regeneration with --recreate

The `--recreate` flag selectively removes managed resources before regeneration, preventing orphaned files when components are removed from your configuration:

```bash
# Clean regeneration - removes old resources first
uv run python onboard-product.py --config product.yaml --recreate
```

**Use cases:**
- Removed components from your configuration (prevents orphaned component/imagerepository files)
- Changed branch names or application structure
- Want a clean slate matching your current configuration exactly

**How it works:**
- Selectively deletes managed subdirectories: `applications/`, `components/`, `imagerepositories/`, `releaseplans/`
- Deletes all `.yaml` files in managed `.tekton/` directories (per-component repo)
- For `integrationtests/`: Deletes only ECP test files (containing "ecp" in filename)
- **Preserves non-ECP integration tests** that you manually created
- Regenerates all managed resources from your configuration

**Without --recreate:** Files are merged/updated, deleted components remain in the output
**With --recreate:** Managed resources are removed and regenerated, non-ECP integration tests preserved

### RPA Cleanup with --recreate-rpa

The `--recreate-rpa` flag removes ReleasePlanAdmission files before regeneration. This is separate from `--recreate` because RPA directories are **tenant-wide** — they are shared across applications, unlike KRD directories which are scoped per-app.

```bash
# Clean regeneration including RPAs
uv run python onboard-product.py --config product.yaml --recreate --recreate-rpa
```

**Important:** `--recreate-rpa` deletes ALL `.yaml` files in `ReleasePlanAdmission/{tenant}/` directories. If multiple applications share a tenant, running with only one app's config will remove the other app's RPAs. Always include all related configs when using this flag.

### Component Filtering for Production Releases

Components are automatically filtered in ReleasePlanAdmission resources based on repository configuration and tech-preview status:

**Stage ReleasePlanAdmissions:**
- Include ALL components regardless of repository configuration or tech-preview status

**Production ReleasePlanAdmissions (regular):**
- Only include components that have `prod_repository` defined
- Skip components marked `tech_preview: true`

**Tech-preview Production ReleasePlanAdmissions** (RPA name contains "tech-preview"):
- Only include components marked `tech_preview: true`
- Uses a separate signing configuration (`hacbs-signing-pipeline-config-redhatbeta2`)

**Example configuration:**
```yaml
components:
  - name: stable-component
    stage_repository: quay.io/org/stable-stage
    prod_repository: quay.io/org/stable-prod     # Included in regular prod RPA

  - name: tech-preview-component
    tech_preview: true
    stage_repository: quay.io/org/preview-stage
    prod_repository: quay.io/org/preview-prod     # Included in tech-preview prod RPA only

  - name: experimental-component
    stage_repository: quay.io/org/experimental-stage
    # No prod_repository = excluded from all prod RPAs
```

### Integration Test Scenarios

The `integrationtests/` directory is only created when integration test scenarios are explicitly configured in your product definition:

```yaml
definitions:
  - application: my-product
    # ... other fields ...

    integration_test_scenarios:
      - template: its-ecp                    # Template: its-ecp or its-konflux-data
        name: check-stage-ecp                # Test name (gets branch suffix)
        optional: true                       # Mark test as optional
        components:                          # Optional: specific components (default: all)
          - component-1
        params:                              # Test-specific parameters
          - name: POLICY_CONFIGURATION
            value: tenant/stage-policy
          - name: TIMEOUT
            value: 40m0s
```

**Available templates:**
- `its-ecp` - Enterprise Contract Policy tests (uses konflux-ci/build-definitions)
- `its-konflux-data` - Custom GitLab-based tests (uses rhel-ai/konflux-data)

**When configured:** Creates `integrationtests/` directory with IntegrationTestScenario resources
**When omitted:** No directory created, kustomization.yaml excludes it automatically

**Naming:** Tests are branch-aware - on branch `rhoai-2.23`, test name `check-stage-ecp` becomes `my-product-rhoai-2-23-check-stage-ecp`

### Multi-Config Processing

Process multiple configuration files in a single run to manage related products or avoid orphaning resources with `--recreate`.

**Use cases**:
- Multiple products sharing a tenant
- Products with configs in different directories
- Batch processing all product configs at once
- Using `--recreate` without orphaning resources from other configs

**Methods**:

**1. Glob Patterns** - Match multiple configs using wildcards:
```bash
# All configs in a directory
uv run python onboard-product.py --config "configs/*.yaml"

# Specific pattern
uv run python onboard-product.py --config "configs/llama-stack-*.yaml"

# Multiple patterns
uv run python onboard-product.py --config "configs/app-*.yaml" --config "configs/service-*.yaml"
```

**2. Directory Processing** - Process all YAML files in a directory:
```bash
# Process entire directory
uv run python onboard-product.py --config-dir configs/llama-stack/

# Automatically filters out hidden files (starting with ., _, or ~)
```

**3. Combined Approach** - Mix and match for maximum control:
```bash
# Specific files + directory + glob patterns
uv run python onboard-product.py \
  --config configs/critical-app.yaml \
  --config "configs/optional-*.yaml" \
  --config-dir configs/shared/
```

**How it works**:
- All matched configs are loaded and their definitions merged
- Resources generated in a single pass (efficient for `--recreate`)
- Duplicates automatically removed (same config specified multiple ways)
- No conflicts if each config defines unique (tenant, application, branch) combinations

**Example with --recreate**:
```bash
# Before: Recreating single config orphaned resources from other configs
uv run python onboard-product.py --config app1.yaml --recreate  # Deletes app1 resources only

# After: Process all configs together - nothing orphaned
uv run python onboard-product.py --config "configs/*.yaml" --recreate  # Regenerates all apps
```

**This is especially critical for `--recreate-rpa`**: RPA directories are tenant-wide, so running with a subset of configs will delete RPAs from apps not included in the run. Always process all configs sharing a tenant together:
```bash
uv run python onboard-product.py --config "configs/*.yaml" --recreate --recreate-rpa
```

## Configuration Schema

### Required Fields

```yaml
definitions:
  - application: my-product              # Product name
    tenant: ai-tenant                   # Konflux tenant
    branch: rhoai-2.23                  # Target branch

    components:
      - name: my-service                 # Component name
        context: .                       # Build context
        dockerfile: Containerfile        # Dockerfile path
        url: https://gitlab.com/...       # Repository URL
        stage_repository: quay.io/.../stage  # Stage container registry (full-container only)
        prod_repository: quay.io/.../prod    # OPTIONAL - Production registry (full-container only)
        local_repo_path: /path/to/repo   # OPTIONAL - Override repo path for .tekton files

        pipelinerun:
          - build_args_file: build-args/default.conf    # Build config
            pipeline: full-container                     # Pipeline type
            additional_build_secret: registry-auth      # Registry secret

    release_plan:
      - name: my-product-stage           # Release plan name
        grace_period: 30                 # Grace period (days)
        autorelease: true                # Enable auto-release

    release_plan_admission:
      - name: my-product-stage           # Must match release_plan
        policy: registry-quay-stage      # Release policy
        tags: ["v1.0", "latest"]         # Image tags
        product_name: "My Product"       # Display name
        product_version: "1.0"           # Version string
        product_id: [12345]              # Product ID
        intention: staging               # Environment
        service_account: release-registry-my-product  # Service account
        pipeline_path: pipelines/managed/push-to-external-registry/push-to-external-registry.yaml
```

### Optional Fields

**Component-level:**
- `tech_preview` - Mark component as tech preview; controls which prod RPA it appears in (default: false)
- `variant` - Build variant for multi-variant builds
- `build_platforms` - Target architectures (default: pipeline defaults)
- `skip-checks` - Bypass quality gates (default: false)
- `timeouts` - Pipeline execution limits
- `local_repo_path` - Override GitLab repository path for .tekton file generation

**Component `component` sub-section:**
```yaml
components:
  - name: my-service
    component:
      mintmaker_enabled: true          # Enable MintMaker dependency updates (default: false, i.e. disabled)
      build_nudge_enabled: true        # Enable build nudging annotation
      build_nudges_ref:                # Components to nudge after this builds
        - other-component
```

**Pipelinerun-level:**
- `squash-build` - Squash build layers (optional, default: not set)
- `use_build_args` - Move name/component labels into build-args instead of pipelinerun labels (default: false)

**ReleasePlan-level:**
- `autorelease_annotation` - Use annotation instead of label for auto-release (default: false)
  - When `true`: Generates `annotations.release.appstudio.openshift.io/auto-release` with component list
  - When `false`: Generates `labels.release.appstudio.openshift.io/auto-release` with boolean value
- `author` - Author label for release plan (e.g., "rhel-ai-team")
- `final_pipeline` - Optional pipeline run after release completes (git resolver); omitted when not set
  ```yaml
  release_plan:
    - name: my-product-stage
      grace_period: 30
      autorelease: true
      final_pipeline:
        url: https://github.com/aipcc-cicd/konflux-data
        revision: main
        path_in_repo: pipelines/copy-clair-scan-results.yaml
        service_account_name: finalpipeline-sa
        params:                        # OPTIONAL - additional pipeline params
          - name: some-param
            value: some-value
  ```

**ReleasePlanAdmission-level:**
- `single_component_mode` - Individual vs bundled releases (default: false)
- `annotations` - Additional metadata used for CPE generation and compliance labels:
  ```yaml
  annotations:
    stream_name: ai-inference-server   # Product stream name
    cpe_name: ai_inference_server      # CPE identifier component
    rhel_target: el9                   # RHEL target platform
  ```
  When `cpe_name` and `rhel_target` are set on a prod RPA, the tool automatically injects a `cpe=` label into the generated pipelinerun files.

### Compact RPA Format (Recommended for Multiple RPAs)

When multiple release plan admissions share common fields, use the `common`/`rpas` structure to avoid repetition:

```yaml
release_plan_admission:
  common:
    single_component_mode: true
    annotations:
      stream_name: my-product
      cpe_name: my_product
      rhel_target: el9
    tags:
      - "3.2"
      - "3.2.0"
      - "3.2.0-{{ timestamp }}"
    product_name: "My Product"
    product_version: "3.2"
    product_id: [12345]
  rpas:
    - name: my-product-stage
      policy: registry-ai-quay-stage
      intention: staging
      service_account: release-registry-my-product
      pipeline_path: pipelines/managed/push-to-external-registry/push-to-external-registry.yaml
      tags:
        - "latest-stage"              # Appended to common tags
    - name: my-product-prod
      policy: registry-ai-containers-prod
      intention: production
      service_account: release-registry-prod
      pipeline_path: pipelines/managed/rh-advisories/rh-advisories.yaml
```

**Merge rules:** All fields from `common` are merged with each RPA entry. Per-RPA values override common values, except `tags` which are appended (common tags + RPA-specific tags).

## Templates

### KRD Templates (`templates/KRD/`)

- `application.yaml.j2` - Konflux Application resource
- `component.yaml.j2` - Component build configuration
- `imagerepository.yaml.j2` - Container image repository
- `releaseplan.yaml.j2` - Release plan definition
- `releaseplanadmission.yaml.j2` - Release admission control (supports both full-container and disk-image pipelines)
- `its-ecp.yaml.j2` - Enterprise Contract Policy integration tests
- `its-konflux-data.yaml.j2` - GitLab-based integration tests

### Pipelinerun Templates (`templates/pipelinerun/`)

- `full-container.yaml.j2` - Tekton pipelinerun for standard container builds
- `disk-image.yaml.j2` - Tekton pipelinerun for disk/ISO image builds

Both templates generate configurations for pull-request and push events.

## Drift Detection

Detect configuration drift between PMT configs (source of truth) and the actual KRD repo. The script runs PMT to generate expected KRD output, then compares against the real repo via `git diff`.

### Local Usage

```bash
# Check a single product
./scripts/drift-check.sh \
  --configs-dir ../aipcc-product-management-configs \
  --krd-repo ../konflux-release-data \
  --product rhelai

# Check all products
./scripts/drift-check.sh \
  --configs-dir ../aipcc-product-management-configs \
  --krd-repo ../konflux-release-data \
  --all
```

Exit code 0 means no drift; exit code 1 means drift was detected (details printed to stdout).

### CI Integration

Consumer repos can include the CI template to get per-product drift-check jobs on MRs and scheduled pipelines:

```yaml
include:
  - project: 'redhat/rhel-ai/ci-cd/aipcc-product-management'
    file: 'ci/drift-check.yml'
```

## Development

### Running Tests

The project includes comprehensive end-to-end regression tests:

```bash
# Run all tests
uv run python -m pytest

# Run tests with verbose output
uv run python -m pytest -v

# Run specific test
uv run python -m pytest tests/test_generation.py::TestGeneration::test_krd_generation -v

# Run tests for specific pipeline type
uv run python -m pytest tests/test_generation.py -k "full-container" -v
uv run python -m pytest tests/test_generation.py -k "disk-image" -v
```

### Updating Expected Test Outputs

When templates or generation logic changes, regenerate expected test outputs:

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
uv run python -m pytest tests/test_generation.py -v
```

**Important:** Always regenerate both pipeline types and run tests to ensure consistency. Commit the updated expected outputs with your template/logic changes.

### Code Quality

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Fix auto-fixable issues
uv run ruff check --fix .
```

### Branch-Specific Naming

The tool automatically generates branch-aware resource names:

- **Main branch**: Uses base names (e.g., `my-product`)
- **Other branches**: Adds branch suffix (e.g., `my-product-rhoai-2-23`)

This enables separate resource management for different product versions.

## Support

For issues or questions, contact the AIPCC team or create an issue in this repository.
