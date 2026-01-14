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
    return Environment(
        loader=FileSystemLoader(template_dir),
        variable_start_string="[[",
        variable_end_string="]]",
    )


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

        for component in definition.get("components", []):
            base_component_name = component["name"]
            component_name = get_component_name(base_component_name, branch)
            component_url = component["url"]

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
                else:
                    raise ValueError(
                        f"Unknown pipeline type '{pipeline}' for component '{component_name}'. Supported types: 'full-container', 'disk-image'"
                    )

                pipeline_template = env.get_template(template_name)

                for pr_type in ["pull", "push"]:
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
                    }

                    # Add parameters specific to full-container pipeline
                    if pipeline == "full-container":
                        template_params.update(
                            {
                                "build_args_file": build_args_file,
                                "additional_build_secret": additional_build_secret,
                                "variant": variant,
                                "skip_checks": skip_checks,
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

    for definition in data.get("definitions", []):
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

        # Remove base_path if recreate flag is set
        if recreate and os.path.exists(base_path):
            print(f"Removing existing directory: {base_path}")
            shutil.rmtree(base_path)

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
        for i, rp in enumerate(definition.get("release_plan", [])):
            base_rp_name = rp["name"]
            if branch == "main":
                rp_name = base_rp_name
            else:
                rp_name = f"{base_rp_name}-{normalized_branch}"

            base_rpa_name = definition.get("release_plan_admission")[i]["name"]
            if branch == "main":
                rpa_name = base_rpa_name
            else:
                rpa_name = f"{base_rpa_name}-{normalized_branch}"

            rp_content = rp_template.render(
                application_name=versioned_app_name,
                release_plan_name=rp_name,
                release_plan_autorelease=str(rp.get("autorelease", False)).lower(),
                release_plan_grace_period=rp["grace_period"],
                release_plan_admission_name=rpa_name,
                tenant_name=tenant,
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

        for rpa in definition.get("release_plan_admission", []):
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

                # For prod RPAs (non-stage), skip components without prod_repository
                if not is_stage_rpa and "prod_repository" not in component:
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
            )
            rpa_filename = f"{rpa_name}.yaml"
            rpa_filepath = os.path.join(rpa_base_path, rpa_filename)
            write_with_newline(rpa_filepath, rpa_content)
            releaseplanadmission_files.append(rpa_filename)

            print(f"Generated ReleasePlanAdmission '{rpa_name}' at {rpa_filepath}")

            # Generate IntegrationTestScenario if configured
            its_config = rpa.get("integration_test_scenario")
            if its_config and its_config.get("enabled", False):
                its_template = env.get_template("integrationtestscenario.yaml.j2")

                # Determine stage/prod from RPA name for the ITS name suffix
                if "stage" in base_rpa_name.lower() or "staging" in base_rpa_name.lower():
                    its_suffix = "check-stage-ecp"
                elif "prod" in base_rpa_name.lower():
                    its_suffix = "check-prod-ecp"
                else:
                    its_suffix = "check-ecp"

                if branch == "main":
                    its_name = f"{base_rpa_name}-{its_suffix}"
                else:
                    its_name = f"{base_rpa_name}-{normalized_branch}-{its_suffix}"

                # Build policy_configuration from tenant and policy
                policy_configuration = f"rhtap-releng-tenant/{rpa['policy']}"

                # Prepare component list with just names for ITS contexts
                its_components = [{"name": comp["name"]} for comp in updated_components]

                its_content = its_template.render(
                    its_name=its_name,
                    application_name=versioned_app_name,
                    optional=its_config.get("optional", False),
                    policy_configuration=policy_configuration,
                    timeout=its_config.get("timeout", "40m0s"),
                    single_component=str(its_config.get("single_component", True)).lower(),
                    components=its_components,
                )

                # Create integrationtests directory only when needed
                ensure_dirs(integrationtests_dir)

                its_filename = f"{its_name}.yaml"
                its_filepath = os.path.join(integrationtests_dir, its_filename)
                write_with_newline(its_filepath, its_content)
                integrationtest_files.append(its_filename)

                print(f"Generated IntegrationTestScenario '{its_name}' at {its_filepath}")

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

    # Required arguments
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Path to the product configuration YAML file",
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

    # Load product data from YAML
    with open(args.config) as f:
        data = yaml.load(f)

    # Generate resources based on mode
    if args.mode in ["krd", "both"]:
        print(f"Generating KRD templates to {config['krd_path']}")
        render_krd_templates(
            data,
            str(config["krd_template_dir"]),
            str(config["krd_path"]),
            config["cluster"],
            args.recreate,
        )

    if args.mode in ["pipelinerun", "both"]:
        print(f"Generating pipelinerun templates to {config['gitlab_repo_path']}")
        render_pipelinerun_templates(
            data,
            str(config["pipelinerun_template_dir"]),
            str(config["gitlab_repo_path"]),
        )

    print("Generation completed!")


if __name__ == "__main__":
    main()
