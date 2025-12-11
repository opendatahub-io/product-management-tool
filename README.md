# AIPCC Product Onboarding

Automated tools for onboarding new products to the Konflux platform. This tool generates Kubernetes resources and CI/CD configurations needed to integrate products with Red Hat's build and release infrastructure.

## Features

- **KRD Generation**: Creates Konflux Release Data resources (Application, Component, ImageRepository, ReleasePlan, ReleasePlanAdmission)
- **Pipelinerun Generation**: Generates Tekton CI/CD pipeline configurations for pull requests and push events
- **Multi-Pipeline Support**: Supports both full-container and disk-image pipeline types
- **Branch-Aware**: Supports separate configurations for main development and maintenance branches
- **Template-Based**: Uses Jinja2 templates for flexible resource generation
- **Flexible Configuration**: Configure via CLI arguments, TOML files, environment variables, or use sensible defaults

## Requirements

- **Python 3.11 or later**
- **uv** (Python package manager)

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd aipcc-product-onboarding

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies and create virtual environment
uv sync
```

### Basic Usage

Product configurations are maintained in a separate repository: [aipcc-product-onboarding-configs](https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-onboarding-configs)

```bash
# Clone the configs repository
git clone https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-onboarding-configs.git

# Generate both KRD and pipelinerun resources
uv run python onboard-product.py --config /path/to/aipcc-product-onboarding-configs/llama-stack/llama-stack-rhoai-2-23.yaml

# Generate only KRD resources
uv run python onboard-product.py --config /path/to/aipcc-product-onboarding-configs/examples/basic-product.yaml --mode krd

# Generate only pipelinerun resources
uv run python onboard-product.py --config /path/to/aipcc-product-onboarding-configs/examples/basic-product.yaml --mode pipelinerun
```

### Using with Podman/Docker (No Python Required)

If you don't have Python installed, you can use the containerized version:

```bash
# Clone the configs repository (if not already cloned)
git clone https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-onboarding-configs.git

# Build the container image
podman build -t onboard-product:latest .

# Generate both KRD and pipelinerun resources
podman run --rm --userns=keep-id:uid=1001,gid=1001 \
  -v /path/to/aipcc-product-onboarding-configs:/configs:ro \
  -v /path/to/konflux-release-data:/krd \
  -v /path/to/gitlab-repos:/repos \
  -e KRD_PATH=/krd \
  -e GITLAB_REPO_PATH=/repos \
  onboard-product:latest \
  --config /configs/llama-stack/llama-stack-rhoai-2-23.yaml

# Generate only pipelinerun resources
podman run --rm --userns=keep-id:uid=1001,gid=1001 \
  -v /path/to/aipcc-product-onboarding-configs:/configs:ro \
  -v /path/to/gitlab-repos:/repos \
  -e GITLAB_REPO_PATH=/repos \
  onboard-product:latest \
  --config /configs/llama-stack/llama-stack-rhoai-2-23.yaml --mode pipelinerun

# Generate only KRD resources
podman run --rm --userns=keep-id:uid=1001,gid=1001 \
  -v /path/to/aipcc-product-onboarding-configs:/configs:ro \
  -v /path/to/konflux-release-data:/krd \
  -e KRD_PATH=/krd \
  onboard-product:latest \
  --config /configs/examples/basic-product.yaml --mode krd

# View help
podman run --rm onboard-product:latest --help
```

**Important Notes:**
- **Clone configs repository**: Clone [aipcc-product-onboarding-configs](https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-onboarding-configs) separately before running the container.
- **User namespace mapping**: Use `--userns=keep-id:uid=1001,gid=1001` to map your user to the container user (UID 1001). This ensures the container can write to your mounted directories without permission issues.
- **Mount configs**: Mount the configs repository with `-v /path/to/aipcc-product-onboarding-configs:/configs:ro` (read-only).
- **Mount output directories**: Mount destination directories where you want files generated (KRD repo, GitLab repos).
- **Environment variables**: Use `-e` to set paths inside the container (e.g., `-e GITLAB_REPO_PATH=/repos`).
- **Docker alternative**: If using Docker instead of Podman, replace `podman` with `docker` and adjust the `--userns` flag to `--user $(id -u):$(id -g)` if needed.

## Configuration

### Product Configuration Files

Product configurations are maintained in a separate repository: [aipcc-product-onboarding-configs](https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-onboarding-configs)

This repository contains configurations organized by product family:
- `examples/` - Template configs for creating new products (basic and advanced examples)
- `llama-stack/` - Red Hat AI Inference Server (RHOAI component)
- `rhaiis/` - Red Hat AI Inference Server (core platform)
- `rhelai/` - Red Hat Enterprise Linux AI bootable containers
- `base-images/` - Red Hat OpenShift AI base images
- `test/` - Test repository configurations

See the [configs repository README](https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-onboarding-configs) for details on configuration structure and naming conventions.

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
- `--krd-path` - Output path for KRD resources
- `--gitlab-path` - Output path for pipelinerun resources
- `--templates-dir` - KRD templates directory
- `--pipelinerun-templates-dir` - Pipelinerun templates directory
- `--cluster` - Target Kubernetes cluster
- `--settings` - Path to TOML settings file

**2. Configuration File**

Create `.onboard-config.toml` in your project directory:

```toml
[paths]
krd_path = "./output/krd"
gitlab_repo_path = "./output/pipelinerun"
templates_dir = "./templates/KRD"
pipelinerun_template_dir = "./templates/pipelinerun"

[cluster]
name = "stone-prod-p02"
```

See `.onboard-config.toml.example` for a complete example.

**3. Environment Variables (Backward Compatible)**
```bash
export KRD_PATH="/path/to/konflux-release-data/"
export GITLAB_REPO_PATH="/path/to/gitlab-repos/"
export CLUSTER="stone-prod-p02"
export TEMPLATES_DIR="templates/KRD"
export PIPELINERUN_TEMPLATE_DIR="templates/pipelinerun"
```

**4. Sensible Defaults (Lowest Priority)**
- `krd_path`: `./output/krd`
- `gitlab_repo_path`: `./output/pipelinerun`
- `templates_dir`: `./templates/KRD`
- `pipelinerun_template_dir`: `./templates/pipelinerun`
- `cluster`: `stone-prod-p02`

The tool works out of the box with no configuration required!

## Output Structure

### KRD Resources
```
{KRD_PATH}/tenants-config/cluster/{cluster}/tenants/{tenant}/{app}/{branch}/
├── applications/{app}.yaml
├── components/{component}.yaml
├── imagerepositories/{component}.yaml
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
        repository: quay.io/...          # Container registry
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
```

### Optional Fields

- `variant` - Build variant for multi-variant builds
- `build_platforms` - Target architectures (default: pipeline defaults)
- `skip-checks` - Bypass quality gates (default: false)
- `timeouts` - Pipeline execution limits
- `single_component_mode` - Individual vs bundled releases (default: false)
- `local_repo_path` - Override GitLab repository path for .tekton file generation

## Templates

### KRD Templates (`templates/KRD/`)

- `application.yaml.j2` - Konflux Application resource
- `component.yaml.j2` - Component build configuration
- `imagerepository.yaml.j2` - Container image repository
- `releaseplan.yaml.j2` - Release plan definition
- `releaseplanadmission.yaml.j2` - Release admission control (supports both full-container and disk-image pipelines)
- `integrationtestscenario.yaml.j2` - Integration test scenarios

### Pipelinerun Templates (`templates/pipelinerun/`)

- `full-container.yaml.j2` - Tekton pipelinerun for standard container builds
- `disk-image.yaml.j2` - Tekton pipelinerun for disk/ISO image builds

Both templates generate configurations for pull-request and push events.

## Development

### Running Tests

The project includes comprehensive end-to-end regression tests:

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
uv run pytest tests/test_generation.py -v
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
