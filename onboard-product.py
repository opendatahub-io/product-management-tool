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
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader
from ruamel.yaml import YAML

from config import Config

yaml = YAML()
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.explicit_start = True
yaml.width = 4096


def canonicalize(value):
    """Convert dots to dashes for filename-safe resource names."""
    return value.replace(".", "-")


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


def collect_config_files(config_patterns, config_dir):
    """
    Collect all config files from patterns and directory.

    Args:
        config_patterns (list): List of file paths or glob patterns (can be None)
        config_dir (Path): Directory to scan for YAML files (can be None)

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
    Normalize RPA configuration to support both old and new formats.

    Supports two formats:
    - Old format: List of RPA dicts directly
    - New format: Dict with 'common' and 'rpas' keys

    In the new format, common fields are merged with each RPA:
    - Tags are APPENDED (RPA tags added to common tags)
    - All other fields are OVERRIDDEN (RPA value replaces common value)

    Args:
        rpa_config: Either a list of RPAs or a dict with 'common' and 'rpas'

    Returns:
        list: List of fully merged RPA configurations

    Examples:
        Old format:
        [{"name": "stage", "policy": "p1"}, {"name": "prod", "policy": "p2"}]
        Returns: same list

        New format (tags append):
        {"common": {"tags": ["v1", "v2"]}, "rpas": [
            {"name": "stage", "tags": ["stage"]},
            {"name": "prod", "tags": ["stable"]}
        ]}
        Returns: [
            {"name": "stage", "tags": ["v1", "v2", "stage"]},
            {"name": "prod", "tags": ["v1", "v2", "stable"]}
        ]

    Note:
        TODO: Once all configs are migrated to new format, simplify this function
        to only handle dict format and remove backward compatibility for list format.
    """
    # Old format: direct list of RPAs (backward compatibility)
    if isinstance(rpa_config, list):
        return rpa_config

    # New format: dict with common and rpas
    if isinstance(rpa_config, dict) and "rpas" in rpa_config:
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

    # Invalid format, return empty list
    return []


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


def render_pipelinerun_templates(data, template_dir, gitlab_repo_path):
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

    for definition in data.get("definitions", []):
        tenant = definition["tenant"]

        branch, normalized_branch, versioned_app_name = get_branch_info(definition)

        # Construct CPE from prod RPA annotations and product_version
        # Format: cpe:/a:redhat:{cpe_name}:{major.minor}::{rhel_target}
        cpe_value = None
        rpa_config = definition.get("release_plan_admission", [])
        rpas = normalize_rpa_config(rpa_config)
        for rpa in rpas:
            rpa_name = rpa.get("name", "")
            if "prod" in rpa_name.lower():
                annotations = rpa.get("annotations", {})
                if "cpe_name" in annotations and "rhel_target" in annotations:
                    cpe_name = annotations["cpe_name"]
                    rhel_target = annotations["rhel_target"]
                    product_version = rpa.get("product_version", "")

                    # Extract major.minor from product_version (e.g., "3.3" from "3.3.0")
                    version_parts = product_version.split(".")
                    if len(version_parts) >= 2:
                        major_minor = f"{version_parts[0]}.{version_parts[1]}"
                        cpe_value = f"cpe:/a:redhat:{cpe_name}:{major_minor}::{rhel_target}"
                break

        for component in definition.get("components", []):
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

            if cpe_value:
                labels.append(f"cpe={cpe_value}")

            # Use local_repo_path if provided, otherwise construct from GitLab URL
            if "local_repo_path" in component:
                tekton_dir = os.path.join(component["local_repo_path"], ".tekton")
            else:
                try:
                    org, repo = parse_gitlab_url(component_url)
                except ValueError as e:
                    print(f"Error parsing URL for component {component_name}: {e}")
                    continue
                tekton_dir = os.path.join(gitlab_repo_path, org, repo, ".tekton")

            ensure_dirs(tekton_dir)

            for pipelinerun_config in component.get("pipelinerun", []):
                pipeline = pipelinerun_config["pipeline"]

                # Extract common parameters
                build_platforms = pipelinerun_config.get("build_platforms", [])
                timeouts = pipelinerun_config.get("timeouts", {})
                path_context = pipelinerun_config.get("path_context", "./context/")
                snyk_project_name = pipelinerun_config.get(
                    "snyk_project_name", "ai-red-hat-inference-server"
                )
                snyk_org = pipelinerun_config.get(
                    "snyk_org", "98e4f46e-334c-414b-b444-43361f404b2f"
                )

                # Select template based on pipeline type
                if pipeline == "disk-image":
                    template_name = "disk-image.yaml.j2"
                elif pipeline == "full-container":
                    template_name = "full-container.yaml.j2"
                    # Extract full-container specific parameters
                    build_args_file = pipelinerun_config["build_args_file"]
                    additional_build_secret = pipelinerun_config["additional_build_secret"]
                    variant = pipelinerun_config.get("variant", "")
                    skip_checks = pipelinerun_config.get("skip-checks", False)
                    squash_build = pipelinerun_config.get("squash-build", None)
                    use_build_args = pipelinerun_config.get("use_build_args", False)

                    # Build build_args array if use_build_args is enabled
                    build_args = []
                    if use_build_args and "prod_repository" in component:
                        try:
                            repo_name = extract_repository_name(component["prod_repository"])
                            build_args.append(f"NAME={repo_name}")
                        except ValueError as e:
                            print(
                                f"Warning: Could not extract repository name from prod_repository for {component_name}: {e}"
                            )
                else:
                    raise ValueError(
                        f"Unknown pipeline type '{pipeline}' for component '{component_name}'. Supported types: 'full-container', 'disk-image'"
                    )

                pipeline_template = env.get_template(template_name)

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
                        "component_dockerfile": component.get("dockerfile", "Containerfile"),
                        "tenant_name": tenant,
                        "pipelinerun_type": pr_type,
                        "branch": branch,
                        "timeouts": timeouts,
                        "path_context": path_context,
                        "snyk_project_name": snyk_project_name,
                        "snyk_org": snyk_org,
                        "build_platforms": build_platforms,
                        "labels": pipelinerun_labels,
                    }

                    # Add parameters specific to full-container pipeline
                    if pipeline == "full-container":
                        template_params.update(
                            {
                                "build_args_file": build_args_file,
                                "additional_build_secret": additional_build_secret,
                                "variant": variant,
                                "skip_checks": skip_checks,
                                "squash_build": squash_build,
                                "build_args": build_args,
                            }
                        )

                    pr_content = pipeline_template.render(**template_params)

                    pr_filename = f"{base_component_name}-on-{pr_type}{'-request' if pr_type == 'pull' else ''}.yaml"
                    pr_filepath = os.path.join(tekton_dir, pr_filename)
                    write_with_newline(pr_filepath, pr_content)

                    print(
                        f"Generated {pr_type} pipelinerun for '{component_name}' at {pr_filepath}"
                    )


def render_krd_templates(data, template_dir, krd_path, cluster="stone-prod-p02", recreate=False):
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
                ]
                for subdir in subdirs_to_delete:
                    subdir_path = os.path.join(base_path, subdir)
                    if os.path.exists(subdir_path):
                        shutil.rmtree(subdir_path)

                # Special handling for integrationtests: delete only ECP files
                its_dir = os.path.join(base_path, "integrationtests")
                if os.path.exists(its_dir):
                    ecp_files_deleted = 0
                    non_ecp_files_kept = 0

                    for filename in os.listdir(its_dir):
                        if filename.endswith(".yaml") and filename != "kustomization.yaml":
                            if "ecp" in filename:
                                file_path = os.path.join(its_dir, filename)
                                os.remove(file_path)
                                ecp_files_deleted += 1
                            else:
                                non_ecp_files_kept += 1

                    # Remove kustomization.yaml (will be regenerated with all files)
                    kustomization_path = os.path.join(its_dir, "kustomization.yaml")
                    if os.path.exists(kustomization_path):
                        os.remove(kustomization_path)

                    if ecp_files_deleted > 0 or non_ecp_files_kept > 0:
                        msg_parts = []
                        if ecp_files_deleted > 0:
                            msg_parts.append(f"removed {ecp_files_deleted} ECP test(s)")
                        if non_ecp_files_kept > 0:
                            msg_parts.append(f"kept {non_ecp_files_kept} non-ECP test(s)")
                        print(f"    integrationtests/: {', '.join(msg_parts)}")

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

        component_files = []
        imagerepo_files = []
        comp_template = env.get_template("component.yaml.j2")
        imagerepo_template = env.get_template("imagerepository.yaml.j2")

        for component in definition.get("components", []):
            base_component_name = component["name"]
            component_name = get_component_name(base_component_name, branch)

            # Extract optional component-level configuration
            component_config = component.get("component", {})
            build_nudge_enabled = component_config.get("build_nudge_enabled", False)
            build_nudges_ref = component_config.get("build_nudges_ref", [])
            # Apply branch-aware naming to build nudge references
            build_nudges_ref = [get_component_name(ref, branch) for ref in build_nudges_ref]

            comp_content = comp_template.render(
                application_name=versioned_app_name,
                component_name=component_name,
                component_context=component.get("context", component.get("contenxt", ".")),
                component_dockerfile=component.get("dockerfile", "Containerfile"),
                component_url=component["url"],
                component_revision=branch,
                build_nudge_enabled=build_nudge_enabled,
                build_nudges_ref=build_nudges_ref,
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

        # Normalize RPA config for release plan generation (needed to get RPA names by index)
        rpa_config_for_rp = definition.get("release_plan_admission", [])
        rpas_for_rp = normalize_rpa_config(rpa_config_for_rp)

        for i, rp in enumerate(definition.get("release_plan", [])):
            base_rp_name = rp["name"]
            if branch == "main":
                rp_name = base_rp_name
            else:
                rp_name = f"{base_rp_name}-{normalized_branch}"

            base_rpa_name = rpas_for_rp[i]["name"]
            if branch == "main":
                rpa_name = base_rpa_name
            else:
                rpa_name = f"{base_rpa_name}-{normalized_branch}"

            # Collect component names for autorelease annotation
            component_names = [
                get_component_name(comp["name"], branch)
                for comp in definition.get("components", [])
            ]

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

            # Detect pipeline types for RPA template selection
            pipeline_types = set()
            for component in definition.get("components", []):
                for pipelinerun_config in component.get("pipelinerun", []):
                    pipeline_types.add(pipelinerun_config["pipeline"])

            # Validate that all components use the same pipeline type
            if len(pipeline_types) > 1:
                raise ValueError(
                    f"Mixed pipeline types found in application '{versioned_app_name}': {pipeline_types}. All components must use the same pipeline type for RPA generation."
                )

            rpa_pipeline_type = pipeline_types.pop() if pipeline_types else "full-container"

            # Prepare components for RPA template
            updated_components = []
            for component in definition.get("components", []):
                base_component_name = component["name"]
                component_name = get_component_name(base_component_name, branch)

                # Check if component is marked for tech preview
                is_tech_preview_component = component.get("tech_preview", False)

                # Filter components based on RPA type:
                # - Stage RPA: include ALL components (tech preview status doesn't matter)
                # - Tech preview prod RPA: only include tech_preview=true components
                # - Regular prod RPA: only include tech_preview=false (or omitted) components
                if is_stage_rpa:
                    pass  # Include all components in stage RPA
                elif is_tech_preview_rpa and not is_tech_preview_component:
                    continue  # Skip non-tech-preview components for tech preview RPA
                elif not is_tech_preview_rpa and is_tech_preview_component:
                    continue  # Skip tech-preview components for regular prod RPA

                # For prod RPAs (non-stage), skip full-container components without prod_repository
                # Disk-image components use rpa_values instead and don't need prod_repository
                if (
                    not is_stage_rpa
                    and rpa_pipeline_type == "full-container"
                    and "prod_repository" not in component
                ):
                    continue

                updated_component = component.copy()
                updated_component["name"] = component_name

                # Validate rpa_values for disk-image components
                if rpa_pipeline_type == "disk-image":
                    if "rpa_values" not in component:
                        raise ValueError(
                            f"Component '{component_name}' uses disk-image pipeline but missing required 'rpa_values' section"
                        )

                    rpa_values = component["rpa_values"]
                    required_fields = [
                        "destination",
                        "version",
                        "filename",
                        "source",
                        "productName",
                        "productCode",
                        "productVersion",
                        "filePrefix",
                    ]
                    missing_fields = [field for field in required_fields if field not in rpa_values]
                    if missing_fields:
                        raise ValueError(
                            f"Component '{component_name}' missing required rpa_values fields: {missing_fields}"
                        )

                    # Set default contentType
                    if "contentType" not in rpa_values:
                        updated_component["rpa_values"] = rpa_values.copy()
                        updated_component["rpa_values"]["contentType"] = "disk-image"

                updated_components.append(updated_component)

            # Extract annotations from RPA config (if present)
            annotations = rpa.get("annotations", None)

            rpa_content = rpa_template.render(
                application_name=versioned_app_name,
                release_plan_admission_name=rpa_name,
                policy_name=rpa["policy"],
                single_component_mode=str(rpa.get("single_component_mode", False)).lower(),
                tags=rpa.get("tags", []),
                product_name=rpa["product_name"],
                product_version=rpa["product_version"],
                product_id=rpa.get("product_id", []),
                intention=rpa["intention"],
                tenant_name=tenant,
                components=updated_components,
                service_account_name=rpa["service_account"],
                pipeline_path=rpa["pipeline_path"],
                rpa_pipeline_type=rpa_pipeline_type,
                is_tech_preview=is_tech_preview_rpa,
                annotations=annotations,
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
                component_names = [comp["name"] for comp in definition.get("components", [])]
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

        # Include any existing non-ECP integration tests in kustomization
        # These files were preserved during --recreate by not deleting them
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
        TEMPLATES_DIR: KRD templates directory
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
        help="Remove and recreate tenant folders before generating resources",
    )

    args = parser.parse_args()

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
    config_files = collect_config_files(args.config_patterns, args.config_dir)

    print(f"Processing {len(config_files)} configuration file(s):")
    for cf in config_files:
        print(f"  - {cf}")

    # Load and merge all definitions
    all_definitions = []
    for config_file in config_files:
        try:
            with open(config_file) as f:
                data = yaml.load(f)
                definitions = data.get("definitions", [])
                all_definitions.extend(definitions)
                print(f"  Loaded {len(definitions)} definition(s) from {config_file.name}")
        except Exception as e:
            print(f"  Error loading {config_file}: {e}")
            raise

    # Create merged data structure
    merged_data = {"definitions": all_definitions}
    print(f"\nTotal: {len(all_definitions)} definition(s) to process\n")

    # Generate resources based on mode
    if args.mode in ["krd", "both"]:
        print(f"Generating KRD templates to {config['krd_path']}")
        render_krd_templates(
            merged_data,
            str(config["krd_template_dir"]),
            str(config["krd_path"]),
            config["cluster"],
            args.recreate,
        )

    if args.mode in ["pipelinerun", "both"]:
        print(f"Generating pipelinerun templates to {config['gitlab_repo_path']}")
        render_pipelinerun_templates(
            merged_data,
            str(config["pipelinerun_template_dir"]),
            str(config["gitlab_repo_path"]),
        )

    print("Generation completed!")


if __name__ == "__main__":
    main()
