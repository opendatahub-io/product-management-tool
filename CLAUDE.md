# CLAUDE.md - Development Instructions

This file contains instructions for Claude to work effectively with this repository.

## Project Overview

This is a Python-based tool for onboarding products to the Konflux platform. It generates Kubernetes resources (KRD) and CI/CD configurations (pipelinerun) using Jinja2 templates.

## Development Commands

### Code Quality
```bash
# Format code
ruff format .

# Lint code  
ruff check .

# Type checking
# No mypy configured - ask user if needed
```

### Running the Tool
```bash
# Generate both KRD and pipelinerun resources
python3 onboard-product.py --config configs/llama-stack.yaml

# Generate only KRD resources
python3 onboard-product.py --config configs/basic-product.yaml --mode krd

# Generate only pipelinerun resources
python3 onboard-product.py --config configs/basic-product.yaml --mode pipelinerun
```

## Architecture Notes

### Template System
- Uses Jinja2 with custom delimiters `[[` and `]]` to avoid YAML conflicts
- KRD templates in `templates/KRD/`: application.yaml.j2, component.yaml.j2, imagerepository.yaml.j2, releaseplan.yaml.j2, releaseplanadmission.yaml.j2
- Pipelinerun templates in `templates/pipelinerun/`: unified.yaml.j2

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