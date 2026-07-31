#!/usr/bin/env python3
"""
Product Onboarding Script for Konflux

This script generates Kubernetes resources for onboarding new products to the Konflux platform.
It supports generating two types of resources:

1. KRD (Konflux Release Data) resources: Application, Component, ImageRepository, ReleasePlan,
   and ReleasePlanAdmission resources that define how the product is built and released.

2. Pipelinerun resources: Tekton pipeline configurations for CI/CD automation, including
   both pull-request and push-triggered pipelines.

The script supports branch-specific resource generation, allowing separate configurations
for main development branches and maintenance/release branches (e.g., rhoai-2.23).

Usage:
    python3 onboard-product.py --config /path/to/config.yaml --mode krd          # Generate only KRD resources
    python3 onboard-product.py --config /path/to/config.yaml --mode pipelinerun  # Generate only pipelinerun resources
    python3 onboard-product.py --config /path/to/config.yaml --mode both         # Generate both types

Configuration:
    Product configurations are maintained in: https://gitlab.com/redhat/rhel-ai/ci-cd/aipcc-product-onboarding-configs
    Templates are loaded from templates/ directory (configurable via env vars)
    Output paths are configurable via environment variables
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader
from ruamel.yaml import YAML

from config import Config

yaml = YAML()
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.explicit_start = True
yaml.width = 4096

_yaml_inline = YAML()
_yaml_inline.indent(mapping=2, sequence=4, offset=2)
_yaml_inline.width = 4096

_yaml_for_filter = YAML()
_yaml_for_filter.indent(mapping=2, sequence=4, offset=2)
_yaml_for_filter.width = 4096


def canonicalize(value):
    """Convert dots to dashes and lowercase for filename-safe resource names."""
    return value.replace(".", "-").lower()


def prefix_repo_path(prefix, path):
    """Prepend a repo-subdirectory prefix to a repo-root-relative path.

    Used when a component lives in a monorepo subdirectory (component `context`
    other than "."). When prefix is empty (context == "." or unset), the path is
    returned unchanged so output for existing configs is byte-identical.
    """
    if not prefix or not path:
        return path
    return f"{prefix}/{path.removeprefix('./')}"


def create_kustomization(directory, files, tenant):
    """
    Create or update a kustomization.yaml file in the specified directory.

    This function either creates a new kustomization.yaml or updates an existing one
    by merging the provided files with any existing resources.

    Args:
        directory (str): Directory where kustomization.yaml should be created/updated
        files (list): List of filenames to include in the resources section
        tenant (str): Tenant name for the namespace field
    """
    kustomization_file = os.path.join(directory, "kustomization.yaml")

    if os.path.exists(kustomization_file):
        with open(kustomization_file) as f:
            existing_content = yaml.load(f)

        existing_resources = existing_content.get("resources", [])
        all_resources = list(set(existing_resources + files))

        kustomization_content = existing_content
        kustomization_content["resources"] = sorted(all_resources)
    else:
        kustomization_content = {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "namespace": tenant,
            "resources": sorted(files),
        }

    with open(kustomization_file, "w") as f:
        yaml.dump(kustomization_content, f)


def write_with_newline(filepath, content):
    """Writes content to a file, ensuring it ends with a newline."""
    if not content.endswith("\n"):
        content += "\n"
    with open(filepath, "w") as f:
        f.write(content)


def ensure_dirs(*paths):
    for p in paths:
        os.makedirs(p, exist_ok=True)


def get_directory_resources(directory):
    """Get all files and directories in a directory for kustomization resources."""
    if not os.path.exists(directory):
        return []

    resources = []
    for item in os.listdir(directory):
        os.path.join(directory, item)
        if not item.startswith(".") and item != "kustomization.yaml":
            resources.append(item)

    return sorted(resources)


def collect_config_files(config_patterns, config_dir, include_parent=False):
    """
    Collect all config files from patterns and directory.

    Args:
        config_patterns (list): List of file paths or glob patterns (can be None)
        config_dir (Path): Directory to scan for YAML files (can be None)
        include_parent (bool): Also scan the parent of config_dir for YAML files

    Returns:
        list: Sorted list of Path objects for config files

    Raises:
        ValueError: If no config files found or directory doesn't exist
    """
    config_files = []

    # Process --config patterns
    if config_patterns:
        for pattern in config_patterns:
            matches = glob.glob(pattern, recursive=True)
            if matches:
                config_files.extend([Path(m).resolve() for m in matches])
            else:
                # Treat as literal path if no glob matches
                path = Path(pattern)
                if path.exists():
                    config_files.append(path.resolve())
                # If path doesn't exist and no glob matches, skip it

    # Process --config-dir
    if config_dir:
        if not config_dir.exists():
            raise ValueError(f"Config directory does not exist: {config_dir}")
        if not config_dir.is_dir():
            raise ValueError(f"Config directory is not a directory: {config_dir}")

        yaml_files = list(config_dir.glob("*.yaml"))
        # Filter out hidden/backup files
        yaml_files = [f.resolve() for f in yaml_files if not f.name.startswith((".", "_", "~"))]
        config_files.extend(yaml_files)

        if include_parent:
            parent = config_dir.resolve().parent
            parent_yamls = [
                f.resolve() for f in parent.glob("*.yaml") if not f.name.startswith((".", "_", "~"))
            ]
            config_files.extend(parent_yamls)

    # Remove duplicates (after resolving paths) and sort
    config_files = sorted(set(config_files))

    if not config_files:
        raise ValueError("No config files found matching the specified patterns/directory")

    return config_files


def get_application_name(base_name, branch):
    """
    Generate application name with branch suffix for non-main branches.

    For main branches: returns base_name (e.g., "llama-stack")
    For other branches: returns base_name-branch (e.g., "llama-stack-rhoai-2-23")

    This ensures that different branches have separate Application resources
    that can be independently managed and released.

    Args:
        base_name (str): Base application name from the YAML definition
        branch (str): Git branch name (e.g., "main", "rhoai-2.23")

    Returns:
        str: Versioned application name
    """
    if branch == "main":
        return base_name
    else:
        normalized_branch = canonicalize(branch)
        return f"{base_name}-{normalized_branch}"


def get_component_name(base_name, branch):
    """
    Generate component name with branch suffix for non-main branches.

    This ensures components match their associated applications and can
    reference the correct branch-specific resources.

    Args:
        base_name (str): Base component name from the YAML definition
        branch (str): Git branch name (e.g., "main", "rhoai-2.23")

    Returns:
        str: Versioned component name
    """
    if branch == "main":
        return base_name
    else:
        normalized_branch = canonicalize(branch)
        return f"{base_name}-{normalized_branch}"


def normalize_rpa_config(rpa_config):
    """
    Normalize RPA configuration from dict with 'common' and 'rpas' keys.

    Common fields are merged with each RPA:
    - Tags are APPENDED (RPA tags added to common tags)
    - All other fields are OVERRIDDEN (RPA value replaces common value)

    Args:
        rpa_config: Dict with 'common' and 'rpas' keys

    Returns:
        list: List of fully merged RPA configurations

    Examples:
        {"common": {"tags": ["v1", "v2"]}, "rpas": [
            {"name": "stage", "tags": ["stage"]},
            {"name": "prod", "tags": ["stable"]}
        ]}
        Returns: [
            {"name": "stage", "tags": ["v1", "v2", "stage"]},
            {"name": "prod", "tags": ["v1", "v2", "stable"]}
        ]
    """
    if not rpa_config:
        return []
    if not isinstance(rpa_config, dict) or "rpas" not in rpa_config:
        raise ValueError(
            f"Invalid RPA config format: expected dict with 'rpas' key, got {type(rpa_config).__name__}"
        )

    common = rpa_config.get("common", {})
    rpas = rpa_config.get("rpas", [])

    # Merge common with each RPA (RPA overrides common, except tags which append)
    merged_rpas = []
    for rpa in rpas:
        merged_rpa = {**common, **rpa}

        # Special handling for tags: append RPA tags to common tags instead of replacing
        if "tags" in common and "tags" in rpa:
            merged_rpa["tags"] = common["tags"] + rpa["tags"]

        merged_rpas.append(merged_rpa)

    return merged_rpas


def normalize_component_config(components_config):
    """
    Normalize component configuration from dict with 'common' and 'items' keys.

    Common fields are merged with each component:
    - Top-level fields: component overrides common
    - common.pipelinerun (a dict of defaults) is merged into each entry
      of the component's pipelinerun list
    - All fields are OVERRIDDEN (component value replaces common value)
    """
    if not isinstance(components_config, dict) or "items" not in components_config:
        raise ValueError(
            f"Invalid components config format: expected dict with 'items' key, got {type(components_config).__name__}"
        )

    common = components_config.get("common", {})
    items = components_config.get("items", [])

    # Separate pipelinerun and rpa_values defaults from other common fields
    common_fields = {k: v for k, v in common.items() if k not in ("pipelinerun", "rpa_values")}
    common_pipelinerun = common.get("pipelinerun", {})
    common_rpa_values = common.get("rpa_values", {})

    merged_components = []
    for component in items:
        # Merge top-level fields (component overrides common)
        merged = {**common_fields, **component}

        # Merge pipelinerun defaults into each pipelinerun entry
        if common_pipelinerun and "pipelinerun" in component:
            merged_pipelineruns = []
            for pr_entry in component["pipelinerun"]:
                merged_pr = {**common_pipelinerun, **pr_entry}

                # params lists are combined (common + item), not overwritten
                common_params = common_pipelinerun.get("params", [])
                item_params = pr_entry.get("params", [])
                if common_params and item_params:
                    item_names = {p["name"] for p in item_params}
                    combined = [p for p in common_params if p["name"] not in item_names]
                    combined.extend(item_params)
                    merged_pr["params"] = combined

                merged_pipelineruns.append(merged_pr)
            merged["pipelinerun"] = merged_pipelineruns
        elif common_pipelinerun and "pipelinerun" not in component:
            merged["pipelinerun"] = [dict(common_pipelinerun)]

        # Merge rpa_values defaults (component overrides common)
        if common_rpa_values:
            merged["rpa_values"] = {**common_rpa_values, **component.get("rpa_values", {})}

        merged_components.append(merged)

    return merged_components


def get_branch_info(definition):
    """
    Extract branch information and calculate versioned names from a product definition.

    This is a convenience function that extracts all the branch-related information
    needed for resource generation in one call.

    Args:
        definition (dict): Product definition from the YAML data

    Returns:
        tuple: (branch_name, normalized_branch_name, versioned_app_name)
    """
    branch = definition.get("branch", "main")
    app_name = definition["application"]
    normalized_branch = canonicalize(branch)
    versioned_app_name = get_application_name(app_name, branch)

    return branch, normalized_branch, versioned_app_name


def yaml_value(value):
    """
    Format a Python value for YAML output, preserving type distinction.

    - Booleans: rendered as lowercase 'true'/'false' (unquoted)
    - Strings: rendered with double quotes
    - Numbers: passed through as-is (unquoted)
    - Other types: converted to quoted string

    Args:
        value: The value to format

    Returns:
        The formatted value for YAML
    """
    if isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, str):
        return f'"{value}"'
    elif isinstance(value, int | float):
        return value
    else:
        return f'"{str(value)}"'


def _strip_ruamel_types(value):
    if isinstance(value, dict):
        return {k: _strip_ruamel_types(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_ruamel_types(v) for v in value]
    return value


def to_yaml_filter(value, indent=0):
    stream = StringIO()
    _yaml_for_filter.dump(_strip_ruamel_types(value), stream)
    result = stream.getvalue().rstrip("\n")
    lines = result.split("\n")
    if lines and lines[0] != lines[0].lstrip():
        offset = len(lines[0]) - len(lines[0].lstrip())
        lines = [line[offset:] if line[:offset].isspace() else line for line in lines]
    if indent > 0:
        return "\n".join((" " * indent + line) for line in lines)
    return "\n".join(lines)


def create_jinja_env(template_dir):
    """
    Create standardized Jinja2 environment with custom delimiters.

    Uses [[ and ]] as delimiters instead of {{ }} to avoid conflicts
    with YAML and Kubernetes resource syntax.

    Args:
        template_dir (str): Directory containing Jinja2 templates

    Returns:
        jinja2.Environment: Configured Jinja2 environment
    """
    env = Environment(
        loader=FileSystemLoader(template_dir),
        variable_start_string="[[",
        variable_end_string="]]",
    )
    env.filters["yaml_value"] = yaml_value
    env.filters["to_yaml"] = to_yaml_filter
    return env


def parse_gitlab_url(url):
    """
    Parse GitLab URL to extract organization and repository path.

    Args:
        url (str): GitLab URL (e.g., "https://gitlab.com/redhat/rhel-ai/llama-stack/containers")

    Returns:
        tuple: (org, repo_path) where org is the top-level organization
               and repo_path is the full repository path

    Example:
        parse_gitlab_url("https://gitlab.com/redhat/rhel-ai/llama-stack/containers")
        returns: ("redhat", "rhel-ai/llama-stack/containers")
    """
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")

    if len(path_parts) < 2:
        raise ValueError(f"Invalid GitLab URL format: {url}")

    org = path_parts[0]
    repo = "/".join(path_parts[1:])

    return org, repo


def extract_repository_name(registry_url):
    """
    Extract repository path from a container registry URL.

    Args:
        registry_url (str): Container registry URL
                           (e.g., "registry.redhat.io/rhelai3/bootc-cuda-rhel9")

    Returns:
        str: Repository path without the registry domain
             (e.g., "rhelai3/bootc-cuda-rhel9")

    Example:
        extract_repository_name("registry.redhat.io/rhelai3/bootc-cuda-rhel9")
        returns: "rhelai3/bootc-cuda-rhel9"
    """
    # Remove schema if present
    if "://" in registry_url:
        registry_url = registry_url.split("://", 1)[1]

    # Split on first slash to separate registry domain from repository path
    parts = registry_url.split("/", 1)
    if len(parts) < 2:
        raise ValueError(f"Invalid registry URL format: {registry_url}")

    return parts[1]


def extract_stage_repo_name(stage_repository):
    """Extract namespace/name from a stage repository URL, keeping last two path segments.

    Stage repos may have an extra path segment vs prod (e.g. quay.io/org/namespace/name
    vs registry.redhat.io/namespace/name); keep only the last two segments if so.
    """
    repo_path = extract_repository_name(stage_repository)
    segments = repo_path.split("/")
    return "/".join(segments[-2:]) if len(segments) > 2 else repo_path


def resolve_repo_path(component, gitlab_repo_path, repo_overrides):
    """
    Resolve the local filesystem path for a component repository.

    Raises ValueError if the component URL cannot be parsed.
    """
    if "local_repo_path" in component:
        return component["local_repo_path"]
    org, repo = parse_gitlab_url(component["url"])  # raises ValueError on bad URL
    repo_key = f"{org}/{repo}"
    if repo_overrides and repo_key in repo_overrides:
        return repo_overrides[repo_key]
    return os.path.join(gitlab_repo_path, org, repo)


def check_repo_health(path, name, expected_branch=None, strict=True):
    """
    Check if a git repository is healthy.

    Returns (errors, warnings):
      errors  — blocking issues that must be fixed (missing path if strict, not a git repo)
      warnings — soft issues the user can override (behind remote, missing path if not strict)

    Args:
        path: Path to the repository root
        name: Human-readable name for messages
        expected_branch: If set, warn when the repo is on a different branch
        strict: If True, missing path / not-a-git-repo go into errors; if False, into warnings
    """
    errors = []
    warnings = []

    if not os.path.exists(path):
        msg = f"{name}: path does not exist: {path}"
        (errors if strict else warnings).append(msg)
        return errors, warnings

    result = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=path, capture_output=True)
    if result.returncode != 0:
        msg = f"{name}: not a git repository: {path}"
        (errors if strict else warnings).append(msg)
        return errors, warnings

    result = subprocess.run(
        ["git", "branch", "--show-current"], cwd=path, capture_output=True, text=True
    )
    current_branch = result.stdout.strip()
    if expected_branch and current_branch != expected_branch:
        warnings.append(
            f"{name}: on branch '{current_branch}', expected '{expected_branch}'"
            f" — make sure this will be merged to '{expected_branch}'"
        )

    try:
        print("    Fetching remote...", end="", flush=True)
        subprocess.run(["git", "fetch", "--quiet"], cwd=path, capture_output=True, timeout=15)
        print(" done")
        result = subprocess.run(
            ["git", "rev-list", "HEAD..@{u}", "--count"],
            cwd=path,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            behind = int(result.stdout.strip() or 0)
            if behind > 0:
                warnings.append(
                    f"{name}: {behind} commit(s) behind origin/{current_branch or expected_branch}"
                )
    except subprocess.TimeoutExpired:
        print(" timed out, skipping remote check")

    return errors, warnings


def collect_repo_warnings(data, config, mode):
    """
    Collect git repository health issues for all paths that will be written to.

    Returns (errors, warnings):
      errors  — blocking issues (KRD path missing/not-git)
      warnings — soft issues the user can override (behind remote, component path missing)
    """
    all_errors = []
    all_warnings = []

    print("Checking repository health...")

    if mode in ["krd", "both"]:
        print(f"  Checking KRD repository: {config['krd_path']}")
        errors, warnings = check_repo_health(str(config["krd_path"]), "KRD repository", strict=True)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    if mode in ["pipelinerun", "both"]:
        gitlab_repo_path = str(config["gitlab_repo_path"])
        repo_overrides = config.get("repo_overrides", {})
        seen_repos = set()

        for definition in data.get("definitions", []):
            expected_branch = definition.get("branch", "main")

            for component in normalize_component_config(definition.get("components", [])):
                try:
                    repo_path = resolve_repo_path(component, gitlab_repo_path, repo_overrides)
                except ValueError as e:
                    print(f"Error resolving repo path for component '{component['name']}': {e}")
                    continue

                if repo_path in seen_repos:
                    continue
                seen_repos.add(repo_path)

                print(f"  Checking {repo_path} (branch: {expected_branch})")
                errors, warnings = check_repo_health(
                    repo_path,
                    repo_path,
                    expected_branch=expected_branch,
                    strict=True,
                )
                all_errors.extend(errors)
                all_warnings.extend(warnings)

    return all_errors, all_warnings


def prompt_continue_with_warnings(warnings):
    """
    Print soft repository warnings and ask the user whether to continue.

    In non-interactive mode (e.g. CI), warnings are printed but execution
    continues automatically. Returns True to continue, False to abort.
    """
    print("\nRepository warnings (non-blocking):")
    for w in warnings:
        print(f"  ! {w}")

    if not sys.stdin.isatty():
        print("\nNon-interactive mode: continuing despite warnings.")
        return True

    print()
    try:
        answer = input("Continue anyway? [y/N] ").strip().lower()
        return answer in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        print()
        return False


def render_pipelinerun_templates(
    data, template_dir, gitlab_repo_path, repo_overrides=None, recreate=False
):
    """
    Generate Tekton pipelinerun YAML files for CI/CD automation.

    Creates both pull-request and push-triggered pipeline configurations
    that are placed in the .tekton/ directory of each component's repository.

    The pipelinerun files use the same branch-aware naming as KRD resources
    to ensure they reference the correct components.

    Args:
        data (dict): Product definitions loaded from YAML
        template_dir (str): Directory containing pipelinerun Jinja2 templates
        gitlab_repo_path (str): Base path where GitLab repositories are checked out

    Output Structure:
        {gitlab_repo_path}/{org}/{repo}/.tekton/
        ├── {component}-on-pull-request.yaml
        └── {component}-on-push.yaml
    """
    env = create_jinja_env(template_dir)

    if recreate:
        tekton_dirs_to_clean = set()
        for definition in data.get("definitions", []):
            components = normalize_component_config(definition.get("components", []))
            for component in components:
                try:
                    tekton_dir = os.path.join(
                        resolve_repo_path(component, gitlab_repo_path, repo_overrides), ".tekton"
                    )
                except ValueError:
                    continue
                if os.path.exists(tekton_dir):
                    tekton_dirs_to_clean.add(tekton_dir)

        if tekton_dirs_to_clean:
            print(
                f"\n--recreate: Cleaning {len(tekton_dirs_to_clean)} .tekton "
                f"director{'y' if len(tekton_dirs_to_clean) == 1 else 'ies'}:"
            )
            for tekton_dir in sorted(tekton_dirs_to_clean):
                print(f"  {tekton_dir}")
                for filename in os.listdir(tekton_dir):
                    if filename.endswith(".yaml"):
                        os.remove(os.path.join(tekton_dir, filename))
            print()

    for definition in data.get("definitions", []):
        tenant = definition["tenant"]

        branch, normalized_branch, versioned_app_name = get_branch_info(definition)

        # Construct CPE label: cpe:/a:redhat:{cpe_name}:{major.minor}::{rhel_target}
        # cpe_name/rhel_target from definition-level cpe: field, or RPA annotations
        # product_version from any RPA (prod preferred, falls back to first available;
        # all RPAs share the common product_version)
        cpe_value = None
        rpa_config = definition.get("release_plan_admission", [])
        rpas = normalize_rpa_config(rpa_config)
        prod_rpa = next((rpa for rpa in rpas if "prod" in rpa.get("name", "").lower()), None)
        version_rpa = prod_rpa or (rpas[0] if rpas else None)

        if version_rpa:
            cpe_config = definition.get("cpe", {})
            if "name" in cpe_config and "rhel_target" in cpe_config:
                cpe_name = cpe_config["name"]
                rhel_target = cpe_config["rhel_target"]
            else:
                annotations = version_rpa.get("annotations", {})
                cpe_name = annotations.get("cpe_name")
                rhel_target = annotations.get("rhel_target")

            if cpe_name and rhel_target:
                product_version = version_rpa.get("product_version", "")
                version_parts = product_version.split(".")
                if len(version_parts) < 2:
                    raise ValueError(
                        f"CPE requires major.minor product_version but got '{product_version}' "
                        f"in RPA '{version_rpa.get('name', '')}'"
                    )
                major_minor = f"{version_parts[0]}.{version_parts[1]}"
                cpe_value = f"cpe:/a:redhat:{cpe_name}:{major_minor}::{rhel_target}"

        components = normalize_component_config(definition.get("components", []))

        for component in components:
            base_component_name = component["name"]
            component_name = get_component_name(base_component_name, branch)
            component_url = component["url"]

            # Build labels array for pipelinerun
            labels = []
            if "prod_repository" in component:
                try:
                    repo_name = extract_repository_name(component["prod_repository"])
                    labels.append(f"name={repo_name}")
                    labels.append(f"com.redhat.component={repo_name}-container")
                except ValueError as e:
                    print(
                        f"Warning: Could not extract repository name from prod_repository for {component_name}: {e}"
                    )
            elif "stage_repository" in component:
                try:
                    repo_name = extract_stage_repo_name(component["stage_repository"])
                    labels.append(f"name={repo_name}")
                    labels.append(f"com.redhat.component={repo_name}-container")
                except ValueError as e:
                    print(
                        f"Warning: Could not extract repository name from stage_repository for {component_name}: {e}"
                    )

            if cpe_value:
                labels.append(f"cpe={cpe_value}")

            try:
                tekton_dir = os.path.join(
                    resolve_repo_path(component, gitlab_repo_path, repo_overrides), ".tekton"
                )
            except ValueError as e:
                print(f"Error resolving repo path for component {component_name}: {e}")
                continue

            ensure_dirs(tekton_dir)

            for pipelinerun_config in component.get("pipelinerun", []):
                pipeline = pipelinerun_config["pipeline"]

                # Extract common parameters
                build_platforms = pipelinerun_config.get("build_platforms", [])
                timeouts = pipelinerun_config.get("timeouts", {})
                # cel_path_changed: paths are used verbatim, relative to the repo root.
                # context_cel_path_changed: paths are relative to the component's
                # `context` and get that prefix applied (monorepo layouts).
                cel_path_changed = pipelinerun_config.get("cel_path_changed", [])
                context_cel_path_changed = pipelinerun_config.get("context_cel_path_changed", [])
                cel_push_tag_prefixes = pipelinerun_config.get("cel_push_tag_prefixes", [])
                build_nudge_files = pipelinerun_config.get("build_nudge_files", "")
                image_expires_after = pipelinerun_config.get("image_expires_after", "5d")
                path_context = pipelinerun_config.get("path_context", "./context/")

                raw_context = component.get("context", component.get("contenxt", "."))
                ctx_prefix = (
                    ""
                    if raw_context.strip("/").removeprefix("./") in ("", ".")
                    else raw_context.strip("/").removeprefix("./")
                )
                path_context = prefix_repo_path(ctx_prefix, path_context)

                # Select template based on pipeline type
                if pipeline == "disk-image":
                    template_name = "disk-image.yaml.j2"
                    image_type = pipelinerun_config["image_type"]
                    config_toml = prefix_repo_path(ctx_prefix, pipelinerun_config["config_toml"])
                elif pipeline == "full-container":
                    template_name = "full-container.yaml.j2"
                    # Extract full-container specific parameters
                    build_args_file = pipelinerun_config["build_args_file"]
                    build_args_file = prefix_repo_path(ctx_prefix, build_args_file)
                    variant = pipelinerun_config.get("variant", "")
                    skip_checks = pipelinerun_config.get("skip-checks", False)
                    use_build_args = pipelinerun_config.get("use_build_args", False)

                    # Build build_args array from config and/or use_build_args
                    build_args = list(pipelinerun_config.get("build_args", []))
                    if use_build_args:
                        if "prod_repository" in component:
                            try:
                                repo_name = extract_repository_name(component["prod_repository"])
                                build_args.append(f"NAME={repo_name}")
                            except ValueError as e:
                                print(
                                    f"Warning: Could not extract repository name from prod_repository for {component_name}: {e}"
                                )
                        elif "stage_repository" in component:
                            try:
                                repo_name = extract_stage_repo_name(component["stage_repository"])
                                build_args.append(f"NAME={repo_name}")
                            except ValueError as e:
                                print(
                                    f"Warning: Could not extract repository name from stage_repository for {component_name}: {e}"
                                )
                else:
                    raise ValueError(
                        f"Unknown pipeline type '{pipeline}' for component '{component_name}'. Supported types: 'full-container', 'disk-image'"
                    )

                pipeline_template = env.get_template(template_name)

                # Replace {variant} placeholder in cel config entries
                variant_value = (
                    pipelinerun_config.get("variant", "") if pipeline == "full-container" else ""
                )
                cel_path_changed = [
                    path.replace("{variant}", variant_value) for path in cel_path_changed
                ]
                # Component-context-relative entries get the context prefix, then are
                # appended to the repo-root-relative ones.
                cel_path_changed += [
                    prefix_repo_path(ctx_prefix, path.replace("{variant}", variant_value))
                    for path in context_cel_path_changed
                ]
                if cel_push_tag_prefixes:
                    cel_push_tag_prefixes = [
                        prefix.replace("{variant}", variant_value)
                        for prefix in cel_push_tag_prefixes
                    ]

                for pr_type in ["pull", "push"]:
                    # Filter labels for full-container when use_build_args is true
                    # (name and component labels move to build-args, only cpe remains)
                    pipelinerun_labels = labels
                    if pipeline == "full-container" and use_build_args:
                        pipelinerun_labels = [
                            label
                            for label in labels
                            if not label.startswith("name=")
                            and not label.startswith("com.redhat.component=")
                        ]

                    # Prepare template parameters based on pipeline type
                    template_params = {
                        "application_name": versioned_app_name,
                        "component_name": component_name,
                        "base_component_name": base_component_name,
                        "component_url": component_url,
                        "component_dockerfile": prefix_repo_path(
                            ctx_prefix, component.get("dockerfile", "Containerfile")
                        ),
                        "tenant_name": tenant,
                        "pipelinerun_type": pr_type,
                        "branch": branch,
                        "timeouts": timeouts,
                        "path_context": path_context,
                        "build_platforms": build_platforms,
                        "cel_path_changed": cel_path_changed,
                        "cel_push_tag_prefixes": cel_push_tag_prefixes,
                        "build_nudge_files": build_nudge_files,
                        "image_expires_after": image_expires_after,
                        "labels": pipelinerun_labels,
                        "extra_params": pipelinerun_config.get("params", []),
                    }

                    # Add parameters specific to each pipeline type
                    if pipeline == "disk-image":
                        template_params.update(
                            {
                                "image_type": image_type,
                                "config_toml": config_toml,
                            }
                        )
                    elif pipeline == "full-container":
                        template_params.update(
                            {
                                "build_args_file": build_args_file,
                                "variant": variant,
                                "skip_checks": skip_checks,
                                "task_run_specs": pipelinerun_config.get("task_run_specs", []),
                                "build_args": build_args,
                                "path_in_repo": pipelinerun_config.get(
                                    "path_in_repo", "pipelines/full-container.yaml"
                                ),
                            }
                        )

                    pr_content = pipeline_template.render(**template_params)

                    pr_filename = f"{base_component_name}-on-{pr_type}{'-request' if pr_type == 'pull' else ''}.yaml"
                    pr_filepath = os.path.join(tekton_dir, pr_filename)
                    write_with_newline(pr_filepath, pr_content)

                    print(
                        f"Generated {pr_type} pipelinerun for '{component_name}' at {pr_filepath}"
                    )


def render_developer_portal_templates(data, template_dir, krd_path, recreate=False):
    """
    Generate developer portal product version YAML files.

    Creates per-version metadata files for each product defined in
    'developer_portal_versions' config entries.

    Args:
        data (dict): Merged config data containing 'developer_portal_versions'
        template_dir (str): Directory containing KRD Jinja2 templates
        krd_path (str): Output path (konflux-release-data repository)
        recreate (bool): If True, delete and recreate each product_slug directory
                         before generation to remove stale version files.

    Output Structure:
        {krd_path}/data/external/developer-portal/{product_slug}/{version_name}.yaml
    """
    _REQUIRED_VERSION_FIELDS = ("version_name", "ga", "hidden", "release_date")

    entries = data.get("developer_portal_versions", [])
    if not entries:
        return

    env = create_jinja_env(template_dir)
    template = env.get_template("developer-portal-version.yaml.j2")

    for entry in entries:
        product_slug = entry.get("product_slug")
        if not product_slug:
            raise ValueError(
                "developer_portal_versions entry missing required field 'product_slug'"
            )
        if "/" in product_slug or "\\" in product_slug:
            raise ValueError(f"'product_slug' must not contain path separators: {product_slug!r}")

        common = entry.get("common", {})
        output_dir = os.path.join(krd_path, "data", "external", "developer-portal", product_slug)

        if recreate and os.path.exists(output_dir):
            shutil.rmtree(output_dir)
            print(f"  --recreate: Removed {output_dir}")

        ensure_dirs(output_dir)

        for version in entry.get("versions", []):
            merged = {**common, **version}

            missing = [f for f in _REQUIRED_VERSION_FIELDS if f not in merged]
            if missing:
                raise ValueError(
                    f"developer_portal_versions entry for '{product_slug}' missing required "
                    f"field(s): {', '.join(missing)}"
                )

            version_name = merged["version_name"]

            content = template.render(
                version_name=version_name,
                ga=merged["ga"],
                hidden=merged["hidden"],
                invisible=merged.get("invisible", False),
                tracking_disabled=merged.get("tracking_disabled", False),
                terms_and_conditions=merged.get("terms_and_conditions"),
                release_date=merged["release_date"],
            )

            filename = f"{version_name}.yaml"
            write_with_newline(os.path.join(output_dir, filename), content)
            print(f"Generated developer-portal version '{version_name}' for '{product_slug}'")


def render_krd_templates(
    data, template_dir, krd_path, cluster="stone-prod-p02", recreate=False, recreate_rpa=False
):
    """
    Generate Konflux Release Data (KRD) resources for product onboarding.

    Creates all the Kubernetes resources needed to onboard a product to Konflux:
    - Application: Top-level application resource
    - Component: Build configuration pointing to source repository
    - ImageRepository: Container image storage configuration
    - ReleasePlan: Defines how releases are triggered and managed
    - ReleasePlanAdmission: Controls release approval and policies

    Resources are organized in a hierarchical directory structure that matches
    the Konflux tenant organization pattern.

    Args:
        data (dict): Product definitions loaded from YAML
        template_dir (str): Directory containing KRD Jinja2 templates
        krd_path (str): Output path (konflux-release-data repository)
        cluster (str): Target Kubernetes cluster name
        recreate (bool): If True, remove and recreate tenant folders before generation

    Output Structure:
        {krd_path}/tenants-config/cluster/{cluster}/tenants/{tenant}/{app_name}/{app_version}/
        ├── applications/
        │   ├── {app_name}.yaml
        │   └── kustomization.yaml
        ├── components/
        │   ├── {component_name}.yaml
        │   └── kustomization.yaml
        ├── imagerepositories/
        │   ├── {component_name}.yaml
        │   └── kustomization.yaml
        └── releaseplans/
            ├── {release_plan_name}.yaml
            └── kustomization.yaml

        Plus ReleasePlanAdmission resources in:
        {krd_path}/config/{cluster}.hjvn.p1/product/ReleasePlanAdmission/{tenant}/
    """
    env = create_jinja_env(template_dir)

    tenants_config_written = False
    tenant_app_names = {}
    definitions = data.get("definitions", [])

    # First pass: If recreate flag is set, selectively delete subdirectories
    # Keep non-ecp integration tests by deleting only ecp files from integrationtests/
    if recreate:
        paths_to_process = set()
        for definition in definitions:
            tenant = definition["tenant"]
            app_name = definition["application"]
            branch, normalized_branch, _ = get_branch_info(definition)

            base_path = os.path.join(
                krd_path,
                "tenants-config",
                "cluster",
                cluster,
                "tenants",
                tenant,
                app_name,
                normalized_branch,
            )

            if os.path.exists(base_path):
                paths_to_process.add(base_path)

        # Process each path with selective deletion
        if paths_to_process:
            print(
                f"\n--recreate: Cleaning {len(paths_to_process)} application director{'y' if len(paths_to_process) == 1 else 'ies'}:"
            )

            for base_path in sorted(paths_to_process):
                print(f"  {base_path}")

                # Delete managed subdirectories entirely
                subdirs_to_delete = [
                    "applications",
                    "components",
                    "imagerepositories",
                    "releaseplans",
                    "integrationtests",
                ]
                for subdir in subdirs_to_delete:
                    subdir_path = os.path.join(base_path, subdir)
                    if os.path.exists(subdir_path):
                        shutil.rmtree(subdir_path)

            print()

    if recreate_rpa:
        rpa_dirs_to_clean = set()
        for definition in definitions:
            tenant = definition["tenant"]
            rpa_dir = os.path.join(
                krd_path,
                "config",
                f"{cluster}.hjvn.p1",
                "product",
                "ReleasePlanAdmission",
                tenant.replace("-tenant", ""),
            )
            if os.path.exists(rpa_dir):
                rpa_dirs_to_clean.add(rpa_dir)

        if rpa_dirs_to_clean:
            print(
                f"\n--recreate-rpa: Cleaning {len(rpa_dirs_to_clean)} ReleasePlanAdmission "
                f"director{'y' if len(rpa_dirs_to_clean) == 1 else 'ies'}:"
            )
            for rpa_dir in sorted(rpa_dirs_to_clean):
                print(f"  {rpa_dir}")
                for filename in os.listdir(rpa_dir):
                    if filename.endswith(".yaml"):
                        os.remove(os.path.join(rpa_dir, filename))
            print()

    # Second pass: Generate all resources
    for definition in definitions:
        tenant = definition["tenant"]
        app_name = definition["application"]

        branch, normalized_branch, versioned_app_name = get_branch_info(definition)

        if tenant not in tenant_app_names:
            tenant_app_names[tenant] = set()
        tenant_app_names[tenant].add(app_name)

        base_path = os.path.join(
            krd_path,
            "tenants-config",
            "cluster",
            cluster,
            "tenants",
            tenant,
            app_name,
            normalized_branch,
        )

        apps_dir = os.path.join(base_path, "applications")
        components_dir = os.path.join(base_path, "components")
        imagerepos_dir = os.path.join(base_path, "imagerepositories")
        releaseplans_dir = os.path.join(base_path, "releaseplans")
        integrationtests_dir = os.path.join(base_path, "integrationtests")
        ensure_dirs(apps_dir, components_dir, imagerepos_dir, releaseplans_dir)

        app_template = env.get_template("application.yaml.j2")
        app_content = app_template.render(application_name=versioned_app_name)
        app_filename = f"{versioned_app_name}.yaml"
        write_with_newline(os.path.join(apps_dir, app_filename), app_content)
        create_kustomization(apps_dir, [app_filename], tenant)
        tenants_config_written = True

        components = normalize_component_config(definition.get("components", []))

        component_files = []
        imagerepo_files = []
        comp_template = env.get_template("component.yaml.j2")
        imagerepo_template = env.get_template("imagerepository.yaml.j2")

        for component in components:
            base_component_name = component["name"]
            component_name = get_component_name(base_component_name, branch)

            # Extract optional component-level configuration
            component_config = component.get("component", {})
            build_nudge_enabled = component_config.get("build_nudge_enabled", False)
            build_nudges_ref = component_config.get("build_nudges_ref", [])
            mintmaker_enabled = component_config.get("mintmaker_enabled", False)
            # Apply branch-aware naming to build nudge references
            build_nudges_ref = [get_component_name(ref, branch) for ref in build_nudges_ref]

            comp_content = comp_template.render(
                application_name=versioned_app_name,
                component_name=component_name,
                component_context=component.get("context", component.get("contenxt", ".")),
                component_dockerfile=component.get("dockerfile", "Containerfile"),
                component_url=component["url"],
                component_revision=branch,
                is_main_branch=(branch == "main"),
                build_nudge_enabled=build_nudge_enabled,
                build_nudges_ref=build_nudges_ref,
                mintmaker_enabled=mintmaker_enabled,
            )
            comp_filename = f"{component_name}.yaml"
            write_with_newline(os.path.join(components_dir, comp_filename), comp_content)
            component_files.append(comp_filename)

            imagerepo_content = imagerepo_template.render(
                application_name=versioned_app_name,
                component_name=component_name,
                tenant_name=tenant,
            )
            write_with_newline(os.path.join(imagerepos_dir, comp_filename), imagerepo_content)
            imagerepo_files.append(comp_filename)

        create_kustomization(components_dir, component_files, tenant)
        create_kustomization(imagerepos_dir, imagerepo_files, tenant)

        releaseplan_files = []
        rp_template = env.get_template("releaseplan.yaml.j2")

        # Normalize RPA config for release plan generation (match by name, not index)
        rpa_config_for_rp = definition.get("release_plan_admission", [])
        rpas_for_rp = normalize_rpa_config(rpa_config_for_rp)
        rpa_name_set = {rpa["name"] for rpa in rpas_for_rp}
        rp_name_set = {rp["name"] for rp in definition.get("release_plan", [])}

        # Warn about RPAs with no matching release plan — they will be generated but never triggered
        for rpa in rpas_for_rp:
            if rpa["name"] not in rp_name_set:
                print(
                    f"Warning: RPA '{rpa['name']}' in application '{versioned_app_name}' "
                    f"has no matching release plan with the same name. "
                    f"The RPA will be generated but no release plan will point to it."
                )

        for rp in definition.get("release_plan", []):
            base_rp_name = rp["name"]
            if branch == "main":
                rp_name = base_rp_name
            else:
                rp_name = f"{base_rp_name}-{normalized_branch}"

            # Match RP to RPA by name — the release plan name must correspond to an RPA of the same name
            if base_rp_name not in rpa_name_set:
                raise ValueError(
                    f"Release plan '{base_rp_name}' has no matching RPA with the same name. "
                    f"Available RPAs: {sorted(rpa_name_set)}"
                )
            if branch == "main":
                rpa_name = base_rp_name
            else:
                rpa_name = f"{base_rp_name}-{normalized_branch}"

            # Collect component names for autorelease annotation
            component_names = [get_component_name(comp["name"], branch) for comp in components]

            # Validate final_pipeline config: a partial dict would silently render
            # Kubernetes resources with empty string values instead of failing loudly.
            final_pipeline = rp.get("final_pipeline")
            if final_pipeline is not None:
                required_final_pipeline_fields = [
                    "url",
                    "revision",
                    "path_in_repo",
                    "service_account_name",
                ]
                missing_final_pipeline_fields = [
                    field for field in required_final_pipeline_fields if field not in final_pipeline
                ]
                if missing_final_pipeline_fields:
                    raise ValueError(
                        f"Release plan '{base_rp_name}' has a 'final_pipeline' config missing required "
                        f"field(s): {sorted(missing_final_pipeline_fields)}"
                    )

            rp_content = rp_template.render(
                application_name=versioned_app_name,
                release_plan_name=rp_name,
                release_plan_autorelease=str(rp.get("autorelease", False)).lower(),
                release_plan_grace_period=rp["grace_period"],
                release_plan_admission_name=rpa_name,
                tenant_name=tenant,
                autorelease_annotation=rp.get("autorelease_annotation", False),
                author=rp.get("author"),
                components=component_names,
                final_pipeline=final_pipeline,
            )
            rp_filename = f"{rp_name}.yaml"
            write_with_newline(os.path.join(releaseplans_dir, rp_filename), rp_content)
            releaseplan_files.append(rp_filename)

        releaseplanadmission_files = []
        integrationtest_files = []
        rpa_template = env.get_template("releaseplanadmission.yaml.j2")

        rpa_base_path = os.path.join(
            krd_path,
            "config",
            f"{cluster}.hjvn.p1",
            "product",
            "ReleasePlanAdmission",
            tenant.replace("-tenant", ""),
        )
        ensure_dirs(rpa_base_path)

        rpa_config = definition.get("release_plan_admission", [])
        rpas = normalize_rpa_config(rpa_config)

        for rpa in rpas:
            base_rpa_name = rpa["name"]
            if branch == "main":
                rpa_name = base_rpa_name
            else:
                rpa_name = f"{base_rpa_name}-{normalized_branch}"

            # Detect if this is a tech preview RPA or stage RPA
            is_tech_preview_rpa = "tech-preview" in rpa_name or "tech_preview" in rpa_name
            is_stage_rpa = "stage" in rpa_name

            # Determine release type: explicit override or auto-detect from build pipeline
            if "release_type" in rpa:
                release_type = rpa["release_type"]
            elif "pipeline_type" in rpa:
                release_type = rpa["pipeline_type"]
            else:
                pipeline_types = set()
                for component in components:
                    for pipelinerun_config in component.get("pipelinerun", []):
                        pipeline_types.add(pipelinerun_config["pipeline"])

                if len(pipeline_types) > 1:
                    raise ValueError(
                        f"Mixed pipeline types found in application '{versioned_app_name}': {pipeline_types}. All components must use the same pipeline type for RPA generation."
                    )

                build_pipeline = pipeline_types.pop() if pipeline_types else "full-container"
                release_type = "cdn" if build_pipeline == "disk-image" else "container"

            valid_release_types = {"cdn", "marketplace", "container"}
            if release_type not in valid_release_types:
                raise ValueError(
                    f"Invalid release_type '{release_type}' for RPA '{rpa_name}'. "
                    f"Valid values: {sorted(valid_release_types)}"
                )

            # Parse per-RPA component entries (list of strings or objects with overrides)
            rpa_components_raw = rpa.get("components", None)
            rpa_component_filter = None
            rpa_component_overrides = {}
            if rpa_components_raw:
                rpa_component_filter = set()
                for entry in rpa_components_raw:
                    if isinstance(entry, str):
                        rpa_component_filter.add(entry)
                    elif isinstance(entry, dict):
                        name = entry["name"]
                        rpa_component_filter.add(name)
                        if "rpa_values" in entry:
                            rpa_component_overrides[name] = entry["rpa_values"]

            # Prepare components for RPA template
            updated_components = []
            for component in components:
                base_component_name = component["name"]
                component_name = get_component_name(base_component_name, branch)

                # Apply per-RPA component filter
                if rpa_component_filter and base_component_name not in rpa_component_filter:
                    continue

                # Check if component is marked for tech preview
                is_tech_preview_component = component.get("tech_preview", False)

                # Filter components based on RPA type:
                # - Stage RPA: include ALL components (tech preview status doesn't matter)
                # - Tech preview prod RPA: only include tech_preview=true components
                # - Regular prod RPA: only include tech_preview=false (or omitted) components
                if is_stage_rpa:
                    pass
                elif is_tech_preview_rpa and not is_tech_preview_component:
                    continue
                elif not is_tech_preview_rpa and is_tech_preview_component:
                    continue

                # For container RPAs (non-stage), skip components without prod_repository
                if (
                    not is_stage_rpa
                    and release_type == "container"
                    and "prod_repository" not in component
                ):
                    continue

                updated_component = component.copy()
                updated_component["name"] = component_name

                # Apply per-RPA rpa_values override if present
                if base_component_name in rpa_component_overrides:
                    updated_component["rpa_values"] = rpa_component_overrides[base_component_name]

                # Validate rpa_values for cdn release type
                if release_type == "cdn":
                    if "rpa_values" not in updated_component:
                        raise ValueError(
                            f"Component '{component_name}' in CDN RPA but missing required 'rpa_values' section"
                        )
                    rpa_values = updated_component["rpa_values"]
                    if "staged" not in rpa_values:
                        raise ValueError(
                            f"Component '{component_name}' missing required 'staged' block in rpa_values"
                        )
                    if "contentGateway" not in rpa_values:
                        raise ValueError(
                            f"Component '{component_name}' missing required 'contentGateway' block in rpa_values for CDN release"
                        )

                # Validate rpa_values for marketplace release type
                if release_type == "marketplace":
                    if "rpa_values" not in updated_component:
                        raise ValueError(
                            f"Component '{component_name}' in marketplace RPA but missing required 'rpa_values' section"
                        )
                    rpa_values = updated_component["rpa_values"]
                    if "staged" not in rpa_values:
                        raise ValueError(
                            f"Component '{component_name}' missing required 'staged' block in rpa_values"
                        )
                    if "productInfo" not in rpa_values:
                        raise ValueError(
                            f"Component '{component_name}' missing required 'productInfo' in rpa_values for marketplace release"
                        )
                    if "starmap" not in rpa_values:
                        raise ValueError(
                            f"Component '{component_name}' missing required 'starmap' in rpa_values for marketplace release"
                        )

                updated_components.append(updated_component)

            # Extract annotations from RPA config (if present)
            annotations = rpa.get("annotations", None)

            rpa_timeouts = rpa.get("timeouts", {})
            rpa_content = rpa_template.render(
                application_name=versioned_app_name,
                release_plan_admission_name=rpa_name,
                policy_name=rpa["policy"],
                single_component_mode=str(rpa["single_component_mode"]).lower()
                if "single_component_mode" in rpa
                else None,
                cdn_env=rpa.get("cdn_env"),
                tags=rpa.get("tags", []),
                product_name=rpa["product_name"],
                product_version=rpa["product_version"],
                product_id=rpa.get("product_id", []),
                intention=rpa["intention"],
                tenant_name=tenant,
                components=updated_components,
                service_account_name=rpa["service_account"],
                pipeline_path=rpa["pipeline_path"],
                pipeline_url=rpa.get(
                    "pipeline_url",
                    "https://github.com/konflux-ci/release-service-catalog.git",
                ),
                pipeline_revision=rpa.get("pipeline_revision", "production"),
                is_tech_preview=is_tech_preview_rpa,
                use_beta_keys=rpa.get("use_beta_keys", False),
                sign=rpa.get("sign", None),
                cloud_marketplaces_secret=rpa.get("cloud_marketplaces_secret", ""),
                cloud_marketplaces_pre_push=rpa.get("cloud_marketplaces_pre_push", False),
                push_source_container_default=rpa.get(
                    "push_source_container_default",
                    False if release_type in ("cdn", "marketplace") else True,
                ),
                annotations=annotations,
                pipeline_timeout=rpa_timeouts.get("pipeline", "4h0m0s"),
                tasks_timeout=rpa_timeouts.get("tasks", "4h0m0s"),
            )
            rpa_filename = f"{rpa_name}.yaml"
            rpa_filepath = os.path.join(rpa_base_path, rpa_filename)
            write_with_newline(rpa_filepath, rpa_content)
            releaseplanadmission_files.append(rpa_filename)

            print(f"Generated ReleasePlanAdmission '{rpa_name}' at {rpa_filepath}")

        # Generate IntegrationTestScenario resources from new integration_test_scenarios field
        its_configs = definition.get("integration_test_scenarios", [])
        for its_config in its_configs:
            template_name = its_config.get("template")
            if not template_name:
                print("Warning: IntegrationTestScenario config missing 'template' field, skipping")
                continue

            # Load the specified template
            template_file = f"{template_name}.yaml.j2"
            try:
                its_template = env.get_template(template_file)
            except Exception as e:
                print(f"Warning: Could not load template '{template_file}': {e}, skipping")
                continue

            # Get the base name and apply branch-aware naming
            base_its_name = its_config.get("name")
            if not base_its_name:
                print("Warning: IntegrationTestScenario config missing 'name' field, skipping")
                continue

            # Pattern: {app_name}-{branch}-{its_name}
            # For main: {app_name}-{its_name}
            # For branch: {app_name}-{normalized_branch}-{its_name}
            if branch == "main":
                its_name = f"{app_name}-{base_its_name}"
            else:
                its_name = f"{app_name}-{normalized_branch}-{base_its_name}"

            # Prepare component list with branch-aware names
            # If components not specified, use all components from the definition
            component_names = its_config.get("components", [])
            if not component_names:
                # Use all components from the definition
                component_names = [comp["name"] for comp in components]
            its_components = [
                {"name": get_component_name(comp_name, branch)} for comp_name in component_names
            ]

            # Prepare template parameters (pass all config fields to template)
            template_params = {
                "its_name": its_name,
                "application_name": versioned_app_name,
                "components": its_components,
                "path_in_repo": its_config.get("path_in_repo", ""),
            }

            # Add all other fields from the config (except template, name, components, path_in_repo)
            for key, value in its_config.items():
                if key not in ["template", "name", "components", "path_in_repo"]:
                    # Auto-suffix releasePlanAdmissionName params with the branch,
                    # consistent with how release plan and RPA names are suffixed.
                    # Configs can use the base name (e.g. "rhaiis-ubi9-prod") and
                    # the tool will append the branch suffix automatically.
                    # If the value already has the suffix, it's left unchanged.
                    if key == "params" and isinstance(value, list) and branch != "main":
                        value = [
                            {**p, "value": f"{p['value']}-{normalized_branch}"}
                            if p.get("name") == "releasePlanAdmissionName"
                            and "value" in p
                            and not p["value"].endswith(f"-{normalized_branch}")
                            else p
                            for p in value
                        ]
                    template_params[key] = value

            # Render the template
            its_content = its_template.render(**template_params)

            # Create integrationtests directory only when needed
            ensure_dirs(integrationtests_dir)

            its_filename = f"{its_name}.yaml"
            its_filepath = os.path.join(integrationtests_dir, its_filename)
            write_with_newline(its_filepath, its_content)
            integrationtest_files.append(its_filename)

            print(
                f"Generated IntegrationTestScenario '{its_name}' using template '{template_name}' at {its_filepath}"
            )

        # Include any existing integration tests on disk not generated from config
        # (e.g. manually placed files when --recreate is not used)
        if os.path.exists(integrationtests_dir):
            for filename in sorted(os.listdir(integrationtests_dir)):
                if (
                    filename.endswith(".yaml")
                    and filename != "kustomization.yaml"
                    and filename not in integrationtest_files
                ):
                    # This is a non-ECP test that exists on disk
                    integrationtest_files.append(filename)
                    print(f"Including existing non-ECP test '{filename}' in kustomization")

        if releaseplan_files:
            create_kustomization(releaseplans_dir, releaseplan_files, tenant)

        if integrationtest_files:
            create_kustomization(integrationtests_dir, integrationtest_files, tenant)

        # Dynamically get all subdirectories for the base_path kustomization
        app_version_directories = get_directory_resources(base_path)
        if app_version_directories:
            create_kustomization(base_path, app_version_directories, tenant)

        print(
            f"Generated files for application '{versioned_app_name}' in tenant '{tenant}' at {base_path}"
        )

    for tenant, app_names in tenant_app_names.items():
        for app_name in app_names:
            app_path = os.path.join(
                krd_path, "tenants-config", "cluster", cluster, "tenants", tenant, app_name
            )

            app_resources = get_directory_resources(app_path)
            if app_resources:
                create_kustomization(app_path, app_resources, tenant)

        tenant_path = os.path.join(
            krd_path, "tenants-config", "cluster", cluster, "tenants", tenant
        )

        tenant_resources = get_directory_resources(tenant_path)
        if tenant_resources:
            create_kustomization(tenant_path, tenant_resources, tenant)

    return tenants_config_written


def main():
    """
    Main entry point for the product onboarding script.

    Parses command line arguments and orchestrates the generation of either
    KRD resources, pipelinerun resources, or both based on the --mode flag.

    Configuration is loaded in priority order:
    1. CLI arguments (highest priority)
    2. Environment variables (backward compatible)
    3. Configuration file (.onboard-config.toml)
    4. Sensible defaults (lowest priority)

    Command Line Arguments:
        --config: Path to the product configuration YAML file (required)
        --mode: Generation mode (krd, pipelinerun, or both) - defaults to 'both'
        --settings: Path to TOML settings file (default: ./.onboard-config.toml)
        --krd-path: Output path for KRD resources (default: ./output/krd)
        --gitlab-path: Output path for pipelinerun resources (default: ./output/pipelinerun)
        --templates-dir: KRD templates directory (default: ./templates/KRD)
        --pipelinerun-templates-dir: Pipelinerun templates directory (default: ./templates/pipelinerun)
        --cluster: Target Kubernetes cluster (default: stone-prod-p02)
        --recreate: Remove and recreate tenant folders before generation (prevents orphaned resources)

    Environment Variables (backward compatible):
        KRD_TEMPLATES_DIR: KRD templates directory
        KRD_PATH: Output path for KRD resources
        CLUSTER: Target Kubernetes cluster name
        PIPELINERUN_TEMPLATE_DIR: Pipelinerun templates directory
        GITLAB_REPO_PATH: Base path for GitLab repository checkouts
    """
    parser = argparse.ArgumentParser(
        description="Generate KRD and pipelinerun resources for Konflux platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Config file arguments
    parser.add_argument(
        "--config",
        action="append",
        type=str,
        dest="config_patterns",
        help="Path or glob pattern for config file(s) (e.g., 'configs/*.yaml'). Can be specified multiple times.",
    )

    parser.add_argument(
        "--config-dir",
        type=Path,
        help="Directory containing multiple config YAML files. Processes all *.yaml files.",
    )

    # Mode selection
    parser.add_argument(
        "--mode",
        choices=["krd", "pipelinerun", "both"],
        default="both",
        help="Generation mode: krd, pipelinerun, or both (default: both)",
    )

    # Settings file
    parser.add_argument(
        "--settings",
        type=Path,
        help="Path to TOML settings file (default: ./.onboard-config.toml)",
    )

    # Path overrides
    parser.add_argument(
        "--krd-path",
        type=Path,
        dest="krd_path",
        help="Output path for KRD resources (default: ./output/krd)",
    )

    parser.add_argument(
        "--gitlab-path",
        type=Path,
        dest="gitlab_repo_path",
        help="Output path for pipelinerun resources (default: ./output/pipelinerun)",
    )

    parser.add_argument(
        "--templates-dir",
        type=Path,
        dest="krd_template_dir",
        help="KRD templates directory (default: ./templates/KRD)",
    )

    parser.add_argument(
        "--pipelinerun-templates-dir",
        type=Path,
        dest="pipelinerun_template_dir",
        help="Pipelinerun templates directory (default: ./templates/pipelinerun)",
    )

    # Cluster
    parser.add_argument(
        "--cluster",
        help="Target Kubernetes cluster (default: stone-prod-p02)",
    )

    # Recreate flag
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Remove and recreate managed resources before generating (cleans KRD tenant subdirs and .tekton/ pipelinerun files)",
    )

    parser.add_argument(
        "--recreate-rpa",
        action="store_true",
        help="Remove and recreate ReleasePlanAdmission files before generating (tenant-wide scope, run with all related configs to avoid orphaning)",
    )

    parser.add_argument(
        "--skip-repo-checks",
        action="store_true",
        help="Skip git repository health checks (branch, up-to-date) before generating resources",
    )

    parser.add_argument(
        "--include-parent",
        action="store_true",
        help="When used with --config-dir, also scan the parent directory for YAML config files (e.g., developer-portal.yaml)",
    )

    args = parser.parse_args()

    if args.recreate_rpa:
        print(
            "WARNING: --recreate-rpa deletes ALL .yaml files in ReleasePlanAdmission/{tenant}/ directories.\n"
            "This is tenant-wide — RPAs from other applications sharing the same tenant will be removed.\n"
            "Ensure all related configs are included in this run to avoid orphaning RPAs.\n"
        )

    # Validate that at least one config source is provided
    if not args.config_patterns and not args.config_dir:
        parser.error("At least one of --config or --config-dir must be specified")

    # Load configuration with hierarchical priority
    config = Config(
        config_file=args.settings,
        cli_overrides={
            "krd_path": args.krd_path,
            "gitlab_repo_path": args.gitlab_repo_path,
            "krd_template_dir": args.krd_template_dir,
            "pipelinerun_template_dir": args.pipelinerun_template_dir,
            "cluster": args.cluster,
        },
    )

    # Collect all config files
    config_files = collect_config_files(args.config_patterns, args.config_dir, args.include_parent)

    print(f"Processing {len(config_files)} configuration file(s):")
    for cf in config_files:
        print(f"  - {cf}")

    # Load and merge all definitions
    all_definitions = []
    all_developer_portal_versions = []
    for config_file in config_files:
        try:
            with open(config_file) as f:
                data = yaml.load(f)
                definitions = data.get("definitions", [])
                all_definitions.extend(definitions)
                dp_versions = data.get("developer_portal_versions", [])
                all_developer_portal_versions.extend(dp_versions)
                print(f"  Loaded {len(definitions)} definition(s) from {config_file.name}")
        except Exception as e:
            print(f"  Error loading {config_file}: {e}")
            raise

    # Create merged data structure
    merged_data = {
        "definitions": all_definitions,
        "developer_portal_versions": all_developer_portal_versions,
    }
    print(f"\nTotal: {len(all_definitions)} definition(s) to process\n")

    # Check repository health before writing anything
    if not args.skip_repo_checks:
        repo_errors, repo_warnings = collect_repo_warnings(merged_data, config, args.mode)

        if repo_errors:
            print("\nRepository errors (must be fixed before continuing):")
            for e in repo_errors:
                print(f"  x {e}")
            if repo_warnings:
                print("\nAdditional warnings:")
                for w in repo_warnings:
                    print(f"  ! {w}")
            print("\nAborted. Fix the errors above and try again.")
            sys.exit(1)

        if repo_warnings and not prompt_continue_with_warnings(repo_warnings):
            print("Aborted.")
            sys.exit(0)

    # Generate resources based on mode
    tenants_config_written = False
    if args.mode in ["krd", "both"]:
        print(f"Generating KRD templates to {config['krd_path']}")
        tenants_config_written = render_krd_templates(
            merged_data,
            str(config["krd_template_dir"]),
            str(config["krd_path"]),
            config["cluster"],
            args.recreate,
            args.recreate_rpa,
        )
        render_developer_portal_templates(
            merged_data,
            str(config["krd_template_dir"]),
            str(config["krd_path"]),
            args.recreate,
        )

    if args.mode in ["pipelinerun", "both"]:
        print(f"Generating pipelinerun templates to {config['gitlab_repo_path']}")
        render_pipelinerun_templates(
            merged_data,
            str(config["pipelinerun_template_dir"]),
            str(config["gitlab_repo_path"]),
            repo_overrides=config.get("repo_overrides", {}),
            recreate=args.recreate,
        )

    print("\nGeneration completed!")

    if tenants_config_written:
        krd_path = config["krd_path"]
        print(
            f"\n*** ACTION REQUIRED ***\n"
            f"tenants-config resources were generated. You must regenerate the manifests:\n"
            f"\n"
            f"  cd {krd_path} && bash tenants-config/build-manifests.sh\n"
            f"\n"
            f"Commit the result together with the generated KRD files."
        )


if __name__ == "__main__":
    main()
