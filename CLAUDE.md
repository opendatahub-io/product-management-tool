# CLAUDE.md - Development Instructions

Python tool that generates Kubernetes resources (KRD) and Tekton CI/CD configs (pipelinerun) for onboarding products to the Konflux platform. Single main script: `onboard-product.py`. Configuration management in `config.py`.

## Development Commands

```bash
# Setup
uv sync

# Run
uv run python onboard-product.py --config /path/to/config.yaml
uv run python onboard-product.py --config-dir /path/to/configs/  # all YAMLs in dir
uv run python onboard-product.py --config "configs/*.yaml"        # glob patterns
uv run python onboard-product.py --config config.yaml --mode krd|pipelinerun|both
uv run python onboard-product.py --config-dir configs/ --recreate # prevent orphaned resources

# Test
uv run python -m pytest
uv run python -m pytest -v
uv run python -m pytest -k "full-container"

# Lint / format
uv run ruff check .
uv run ruff format .
```

Product configs live in a separate repo: `https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-onboarding-configs`

## Regenerating Expected Test Outputs

Run this after changing any template or generation logic. Always commit the updated expected outputs together with your template/logic changes so the diff is visible for review.

```bash
KRD_PATH="$(pwd)/tests/expected/full-container/krd/" \
GITLAB_REPO_PATH="$(pwd)/tests/expected/full-container/pipelinerun/" \
uv run python onboard-product.py --config tests/configs/test-full-container.yaml --mode both

KRD_PATH="$(pwd)/tests/expected/disk-image/krd/" \
GITLAB_REPO_PATH="$(pwd)/tests/expected/disk-image/pipelinerun/" \
uv run python onboard-product.py --config tests/configs/test-disk-image.yaml --mode both

uv run python -m pytest tests/test_generation.py -v
```

For a full reset of all expected outputs:

```bash
rm -rf tests/expected/full-container/* tests/expected/disk-image/*
mkdir -p tests/expected/full-container/{krd,pipelinerun} tests/expected/disk-image/{krd,pipelinerun}

KRD_PATH="$(pwd)/tests/expected/full-container/krd/" \
GITLAB_REPO_PATH="$(pwd)/tests/expected/full-container/pipelinerun/" \
uv run python onboard-product.py --config tests/configs/test-full-container.yaml --mode both

KRD_PATH="$(pwd)/tests/expected/disk-image/krd/" \
GITLAB_REPO_PATH="$(pwd)/tests/expected/disk-image/pipelinerun/" \
uv run python onboard-product.py --config tests/configs/test-disk-image.yaml --mode both

uv run python -m pytest tests/test_generation.py -v
```

## Architecture

### Template System
- Jinja2 with custom delimiters `[[` and `]]` to avoid YAML conflicts
- KRD templates: `templates/KRD/` — application, component, imagerepository, releaseplan, releaseplanadmission, its-ecp, its-konflux-data
- Pipelinerun templates: `templates/pipelinerun/` — `full-container.yaml.j2`, `disk-image.yaml.j2`
- Template selection driven by `pipeline` field in config

### Branch-Aware Naming
- `main` branch → base name (e.g., `llama-stack`)
- Other branches → base name + normalized branch suffix (e.g., `llama-stack-rhoai-2-23`)
- Dots converted to dashes: `rhoai-2.23` → `rhoai-2-23`

### Output Structure

KRD:
```
{KRD_PATH}/tenants-config/cluster/{cluster}/tenants/{tenant}/{app}/{branch}/
├── applications/{app}.yaml
├── components/{component}.yaml
├── imagerepositories/{component}.yaml
├── releaseplans/{releaseplan}.yaml
└── integrationtests/{its_name}.yaml   # only when integration_test_scenarios defined
```

Pipelinerun:
```
{GITLAB_REPO_PATH}/{org}/{repo}/.tekton/
├── {component}-on-pull-request.yaml
└── {component}-on-push.yaml
```

## Configuration

Priority order: CLI args > environment variables > `.onboard-config.toml` > defaults

| Env var | TOML key (`[paths]`) | Default |
|---|---|---|
| `KRD_TEMPLATES_DIR` | `krd_templates_dir` | `./templates/KRD` |
| `KRD_PATH` | `krd_path` | `./output/krd` |
| `PIPELINERUN_TEMPLATE_DIR` | `pipelinerun_template_dir` | `./templates/pipelinerun` |
| `GITLAB_REPO_PATH` | `gitlab_repo_path` | `./output/pipelinerun` |
| `CLUSTER` | `[cluster] name` | `stone-prod-p02` |

Copy `.onboard-config.toml.example` to `.onboard-config.toml` for local overrides (gitignored).

## Testing

- Tests in `tests/test_generation.py`, three test classes: `TestGeneration`, `TestMultiConfig`, `TestDeveloperPortal`
- Expected outputs in `tests/expected/{pipeline-type}/{krd,pipelinerun}/`
- `onboard-product.py` has a dash in the filename — tests import it via `importlib`
- Use `compare_directories()` helper when adding new output comparison tests
- Developer portal test config: `tests/configs/test-developer-portal.yaml`

## Troubleshooting

**Tests fail after template/logic changes** — regenerate expected outputs (see above).

**Glob patterns not matching** — quote them: `--config "*.yaml"`, not `--config *.yaml`.

**Pipelinerun files in wrong location** — check `local_repo_path` in component config; it overrides the GitLab URL-based path resolution.

**`--recreate` scope** — deletes only managed subdirs within `{tenant}/{app}/{branch}/`, not the whole app dir. Run with all related configs together to avoid orphaning resources.
