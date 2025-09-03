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

### Running the Tool
```bash
# Generate both KRD and pipelinerun resources
uv run python onboard-product.py --config configs/llama-stack.yaml

# Generate only KRD resources
uv run python onboard-product.py --config configs/basic-product.yaml --mode krd

# Generate only pipelinerun resources
uv run python onboard-product.py --config configs/basic-product.yaml --mode pipelinerun
```

## Architecture Notes

### Template System
- Uses Jinja2 with custom delimiters `[[` and `]]` to avoid YAML conflicts
- KRD templates in `templates/KRD/`: application.yaml.j2, component.yaml.j2, imagerepository.yaml.j2, releaseplan.yaml.j2, releaseplanadmission.yaml.j2
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
└── releaseplans/{releaseplan}.yaml
```

Pipelinerun resources as:
```
{GITLAB_REPO_PATH}/{org}/{repo}/.tekton/
├── {component}-on-pull-request.yaml
└── {component}-on-push.yaml
```

## Configuration Files
- Product configs in `configs/` directory
- Examples: basic-product.yaml, advanced-product.yaml, llama-stack.yaml

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
  - Required fields: `destination`, `version`, `filename`, `source`, `productName`, `productCode`, `productVersionName`, `filePrefix`
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