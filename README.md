# AIPCC Product Onboarding

Automated tools for onboarding new products to the Konflux platform. This tool generates Kubernetes resources and CI/CD configurations needed to integrate products with Red Hat's build and release infrastructure.

## Features

- **KRD Generation**: Creates Konflux Release Data resources (Application, Component, ImageRepository, ReleasePlan, ReleasePlanAdmission)
- **Pipelinerun Generation**: Generates Tekton CI/CD pipeline configurations for pull requests and push events
- **Branch-Aware**: Supports separate configurations for main development and maintenance branches
- **Template-Based**: Uses Jinja2 templates for flexible resource generation
- **Environment Configurable**: All paths and settings configurable via environment variables

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd aipcc-product-onboarding

# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

```bash
# Generate both KRD and pipelinerun resources
python3 onboard-product.py --config configs/llama-stack.yaml

# Generate only KRD resources
python3 onboard-product.py --config configs/basic-product.yaml --mode krd

# Generate only pipelinerun resources
python3 onboard-product.py --config configs/basic-product.yaml --mode pipelinerun
```

### Using with Podman/Docker (No Python Required)

If you don't have Python installed, you can use the containerized version:

```bash
# Build the container image
podman build -t onboard-product:latest .

# Generate both KRD and pipelinerun resources
podman run --rm --userns=keep-id:uid=1001,gid=1001 \
  -v $(pwd)/configs:/opt/app-root/src/configs:ro \
  -v /path/to/konflux-release-data:/krd \
  -v /path/to/gitlab-repos:/repos \
  -e KRD_PATH=/krd \
  -e GITLAB_REPO_PATH=/repos \
  onboard-product:latest \
  --config configs/llama-stack.yaml

# Generate only pipelinerun resources
podman run --rm --userns=keep-id:uid=1001,gid=1001 \
  -v $(pwd)/configs:/opt/app-root/src/configs:ro \
  -v /path/to/gitlab-repos:/repos \
  -e GITLAB_REPO_PATH=/repos \
  onboard-product:latest \
  --config configs/llama-stack.yaml --mode pipelinerun

# Generate only KRD resources
podman run --rm --userns=keep-id:uid=1001,gid=1001 \
  -v $(pwd)/configs:/opt/app-root/src/configs:ro \
  -v /path/to/konflux-release-data:/krd \
  -e KRD_PATH=/krd \
  onboard-product:latest \
  --config configs/basic-product.yaml --mode krd

# View help
podman run --rm onboard-product:latest --help
```

**Important Notes:**
- **User namespace mapping**: Use `--userns=keep-id:uid=1001,gid=1001` to map your user to the container user (UID 1001). This ensures the container can write to your mounted directories without permission issues.
- **Mount configs**: Mount your configs directory with `-v $(pwd)/configs:/opt/app-root/src/configs:ro` (read-only).
- **Mount output directories**: Mount destination directories where you want files generated (KRD repo, GitLab repos).
- **Environment variables**: Use `-e` to set paths inside the container (e.g., `-e GITLAB_REPO_PATH=/repos`).
- **Docker alternative**: If using Docker instead of Podman, replace `podman` with `docker` and adjust the `--userns` flag to `--user $(id -u):$(id -g)` if needed.

## Configuration

### Product Configuration Files

Product configurations are stored in the `configs/` directory:

- `basic-product.yaml` - Simple example with detailed comments
- `advanced-product.yaml` - Complex example showing all options
- `llama-stack.yaml` - Real-world production example

### Environment Variables

Configure output paths and settings:

```bash
export KRD_PATH="/path/to/konflux-release-data/"           # KRD output directory
export GITLAB_REPO_PATH="/path/to/gitlab-repos/"           # GitLab repositories base path
export CLUSTER="stone-prod-p02"                            # Target Kubernetes cluster
export TEMPLATES_DIR="templates/KRD"                       # KRD templates directory
export PIPELINERUN_TEMPLATE_DIR="templates/pipelinerun"    # Pipelinerun templates directory
```

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
- `releaseplanadmission.yaml.j2` - Release admission control

### Pipelinerun Templates (`templates/pipelinerun/`)

- `unified.yaml.j2` - Tekton pipelinerun configuration for both pull-request and push events

## Development

### Code Quality

```bash
# Format and lint code
ruff format .
ruff check .

# Run type checking (if using mypy)
mypy onboard-product.py
```

### Branch-Specific Naming

The tool automatically generates branch-aware resource names:

- **Main branch**: Uses base names (e.g., `my-product`)
- **Other branches**: Adds branch suffix (e.g., `my-product-rhoai-2-23`)

This enables separate resource management for different product versions.

## Support

For issues or questions, contact the AIPCC team or create an issue in this repository.