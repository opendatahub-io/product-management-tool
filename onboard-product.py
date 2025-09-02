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
    python3 onboard-product.py --config configs/llama-stack.yaml --mode krd          # Generate only KRD resources
    python3 onboard-product.py --config configs/llama-stack.yaml --mode pipelinerun  # Generate only pipelinerun resources
    python3 onboard-product.py --config configs/llama-stack.yaml --mode both         # Generate both types

Configuration:
    Product configurations are stored in configs/ directory
    Templates are loaded from templates/ directory (configurable via env vars)
    Output paths are configurable via environment variables
"""

import os
import argparse
from urllib.parse import urlparse
from ruamel.yaml import YAML
from jinja2 import Environment, FileSystemLoader

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
        with open(kustomization_file, "r") as f:
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
        item_path = os.path.join(directory, item)
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


def load_config_and_data(config_file_path):
    """
    Load configuration from environment variables and product data from YAML.

    All paths and settings can be overridden via environment variables,
    making the script flexible for different deployment environments.

    Args:
        config_file_path (str): Path to the product configuration YAML file

    Environment Variables:
        TEMPLATES_DIR: Directory containing KRD templates
        KRD_PATH: Output path for KRD resources (konflux-release-data repo)
        CLUSTER: Target Kubernetes cluster name
        PIPELINERUN_TEMPLATE_DIR: Directory containing pipelinerun templates
        GITLAB_REPO_PATH: Base path for GitLab repository checkouts

    Returns:
        tuple: (config_dict, product_data)
    """
    config = {
        "krd_template_dir": os.environ.get("TEMPLATES_DIR", "templates/KRD"),
        "krd_path": os.environ.get("KRD_PATH", "/home/jrusz/repos/konflux-release-data/"),
        "cluster": os.environ.get("CLUSTER", "stone-prod-p02"),
        "pipelinerun_template_dir": os.environ.get(
            "PIPELINERUN_TEMPLATE_DIR", "templates/pipelinerun"
        ),
        "gitlab_repo_path": os.environ.get("GITLAB_REPO_PATH", "/home/jrusz/other-repos/"),
    }

    with open(config_file_path, "r") as f:
        data = yaml.load(f)

    return config, data


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

    unified_template = env.get_template("unified.yaml.j2")

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
                build_args_file = pipelinerun_config["build_args_file"]
                pipeline = pipelinerun_config["pipeline"]
                build_platforms = pipelinerun_config.get("build_platforms", [])
                additional_build_secret = pipelinerun_config["additional_build_secret"]
                variant = pipelinerun_config.get("variant", "")
                skip_checks = pipelinerun_config.get("skip-checks", False)
                timeouts = pipelinerun_config.get("timeouts", {})
                path_context = pipelinerun_config.get("path_context", "./context/")
                snyk_project_name = pipelinerun_config.get("snyk_project_name", "ai-red-hat-inference-server")
                snyk_org = pipelinerun_config.get("snyk_org", "98e4f46e-334c-414b-b444-43361f404b2f")

                for pr_type in ["pull", "push"]:
                    pr_content = unified_template.render(
                        application_name=versioned_app_name,
                        component_name=component_name,
                        base_component_name=base_component_name,
                        component_url=component_url,
                        component_dockerfile=component.get("dockerfile", "Containerfile"),
                        tenant_name=tenant,
                        pipelinerun_type=pr_type,
                        build_args_file=build_args_file,
                        build_platforms=build_platforms,
                        pipelinerun_pipeline=pipeline,
                        additional_build_secret=additional_build_secret,
                        branch=branch,
                        variant=variant,
                        skip_checks=skip_checks,
                        timeouts=timeouts,
                        path_context=path_context,
                        snyk_project_name=snyk_project_name,
                        snyk_org=snyk_org,
                    )

                    pr_filename = f"{base_component_name}-on-{pr_type}{'-request' if pr_type == 'pull' else ''}.yaml"
                    pr_filepath = os.path.join(tekton_dir, pr_filename)
                    write_with_newline(pr_filepath, pr_content)

                    print(
                        f"Generated {pr_type} pipelinerun for '{component_name}' at {pr_filepath}"
                    )


def render_krd_templates(data, template_dir, krd_path, cluster="stone-prod-p02"):
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

        apps_dir = os.path.join(base_path, "applications")
        components_dir = os.path.join(base_path, "components")
        imagerepos_dir = os.path.join(base_path, "imagerepositories")
        releaseplans_dir = os.path.join(base_path, "releaseplans")
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

            comp_content = comp_template.render(
                application_name=versioned_app_name,
                component_name=component_name,
                component_context=component.get("context", component.get("contenxt", ".")),
                component_dockerfile=component.get("dockerfile", "Containerfile"),
                component_url=component["url"],
                component_revision=branch,
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

            updated_components = []
            for component in definition.get("components", []):
                base_component_name = component["name"]
                component_name = get_component_name(base_component_name, branch)
                updated_component = component.copy()
                updated_component["name"] = component_name
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
            )
            rpa_filename = f"{rpa_name}.yaml"
            rpa_filepath = os.path.join(rpa_base_path, rpa_filename)
            write_with_newline(rpa_filepath, rpa_content)
            releaseplanadmission_files.append(rpa_filename)

            print(f"Generated ReleasePlanAdmission '{rpa_name}' at {rpa_filepath}")

        if releaseplan_files:
            create_kustomization(releaseplans_dir, releaseplan_files, tenant)

        app_version_directories = [
            "applications",
            "components",
            "imagerepositories",
            "releaseplans",
        ]
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

    Command Line Arguments:
        --config: Path to the product configuration YAML file (required)
        --mode: Generation mode (krd, pipelinerun, or both) - defaults to 'both'

    Environment Variables:
        See load_config_and_data() for complete list of configurable paths
    """
    parser = argparse.ArgumentParser(description="Generate KRD templates and/or pipelinerun files")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the product configuration YAML file (e.g., configs/llama-stack.yaml)",
    )
    parser.add_argument(
        "--mode",
        choices=["krd", "pipelinerun", "both"],
        default="both",
        help="Generation mode: krd, pipelinerun, or both (default: both)",
    )
    args = parser.parse_args()

    config, data = load_config_and_data(args.config)

    if args.mode in ["krd", "both"]:
        print(f"Generating KRD templates...")
        render_krd_templates(
            data, config["krd_template_dir"], config["krd_path"], config["cluster"]
        )

    if args.mode in ["pipelinerun", "both"]:
        print(f"Generating pipelinerun templates...")
        render_pipelinerun_templates(
            data, config["pipelinerun_template_dir"], config["gitlab_repo_path"]
        )

    print("Generation completed!")


if __name__ == "__main__":
    main()
