"""
Property-based validation tests for onboard-product.py generated output.

These tests validate structural invariants of generated YAML files — required
fields, consistent naming, valid references — independently of snapshot
content. They catch malformed output even after snapshot regeneration.
"""

import importlib.util
import os
from pathlib import Path

import pytest
from ruamel.yaml import YAML

spec = importlib.util.spec_from_file_location(
    "onboard_product",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "onboard-product.py"),
)
onboard_product = importlib.util.module_from_spec(spec)
spec.loader.exec_module(onboard_product)

yaml = YAML()
yaml.preserve_quotes = True

TESTS_DIR = Path(__file__).parent
CONFIGS_DIR = TESTS_DIR / "configs"
TEMPLATES_KRD = Path(__file__).parent.parent / "templates" / "KRD"
TEMPLATES_PIPELINERUN = Path(__file__).parent.parent / "templates" / "pipelinerun"


def load_yaml(path):
    with open(path) as f:
        return yaml.load(f)


def load_all_yaml(path):
    """Load a potentially multi-document YAML file, return first doc."""
    with open(path) as f:
        docs = list(yaml.load_all(f))
    return [d for d in docs if d is not None]


def iter_yaml_files(directory, exclude=None):
    """Yield (path, parsed_doc) for every non-kustomization YAML file."""
    exclude = exclude or set()
    for root, _dirs, files in os.walk(directory):
        for fname in sorted(files):
            if fname.endswith(".yaml") and fname not in exclude:
                p = Path(root) / fname
                for doc in load_all_yaml(p):
                    if doc is not None:
                        yield p, doc


def generate_krd(config_file, tmp_dir):
    with open(config_file) as f:
        data = yaml.load(f)
    onboard_product.render_krd_templates(
        data, str(TEMPLATES_KRD), str(tmp_dir), "stone-prod-p02", recreate=False
    )
    return data


def generate_pipelinerun(config_file, tmp_dir):
    with open(config_file) as f:
        data = yaml.load(f)
    onboard_product.render_pipelinerun_templates(data, str(TEMPLATES_PIPELINERUN), str(tmp_dir))
    return data


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def full_container_krd(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("fc_krd")
    data = generate_krd(CONFIGS_DIR / "test-full-container.yaml", tmp)
    return tmp, data


@pytest.fixture(scope="module")
def disk_image_krd(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("di_krd")
    data = generate_krd(CONFIGS_DIR / "test-disk-image.yaml", tmp)
    return tmp, data


@pytest.fixture(scope="module")
def full_container_pipelinerun(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("fc_pr")
    data = generate_pipelinerun(CONFIGS_DIR / "test-full-container.yaml", tmp)
    return tmp, data


@pytest.fixture(scope="module")
def disk_image_pipelinerun(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("di_pr")
    data = generate_pipelinerun(CONFIGS_DIR / "test-disk-image.yaml", tmp)
    return tmp, data


@pytest.fixture(scope="module")
def stage_only_pipelinerun(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("stage_only_pr")
    data = generate_pipelinerun(CONFIGS_DIR / "test-stage-only-container.yaml", tmp)
    return tmp, data


# ---------------------------------------------------------------------------
# KRD: Application resources
# ---------------------------------------------------------------------------


class TestKRDApplicationResources:
    def test_application_required_fields(self, full_container_krd):
        krd_dir, _ = full_container_krd
        apps = list(iter_yaml_files(krd_dir, exclude={"kustomization.yaml"}))
        app_docs = [(p, d) for p, d in apps if d.get("kind") == "Application"]
        assert app_docs, "No Application resources found"
        for path, doc in app_docs:
            assert "apiVersion" in doc, f"{path}: missing apiVersion"
            assert doc["kind"] == "Application"
            assert "metadata" in doc and "name" in doc["metadata"], f"{path}: missing metadata.name"
            assert "spec" in doc and "displayName" in doc["spec"], (
                f"{path}: missing spec.displayName"
            )

    def test_application_name_matches_versioned(self, full_container_krd):
        krd_dir, data = full_container_krd
        definition = data["definitions"][0]
        _, _, versioned = onboard_product.get_branch_info(definition)
        apps = [
            (p, d)
            for p, d in iter_yaml_files(krd_dir, exclude={"kustomization.yaml"})
            if d.get("kind") == "Application"
        ]
        for _, doc in apps:
            assert doc["metadata"]["name"] == versioned


# ---------------------------------------------------------------------------
# KRD: Component resources
# ---------------------------------------------------------------------------


class TestKRDComponentResources:
    def test_component_required_fields(self, full_container_krd):
        krd_dir, _ = full_container_krd
        comp_docs = [
            (p, d)
            for p, d in iter_yaml_files(krd_dir, exclude={"kustomization.yaml"})
            if d.get("kind") == "Component"
        ]
        assert comp_docs, "No Component resources found"
        for path, doc in comp_docs:
            assert "apiVersion" in doc, f"{path}: missing apiVersion"
            assert "metadata" in doc, f"{path}: missing metadata"
            assert "annotations" in doc["metadata"], f"{path}: missing metadata.annotations"
            assert "name" in doc["metadata"], f"{path}: missing metadata.name"
            spec = doc.get("spec", {})
            assert "application" in spec, f"{path}: missing spec.application"
            assert "componentName" in spec, f"{path}: missing spec.componentName"
            src = spec.get("source", {}).get("git", {})
            assert "url" in src, f"{path}: missing spec.source.git.url"
            assert "revision" in src, f"{path}: missing spec.source.git.revision"

    def test_component_revision_matches_branch(self, full_container_krd):
        krd_dir, data = full_container_krd
        branch = data["definitions"][0].get("branch", "main")
        comp_docs = [
            (p, d)
            for p, d in iter_yaml_files(krd_dir, exclude={"kustomization.yaml"})
            if d.get("kind") == "Component"
        ]
        for path, doc in comp_docs:
            revision = doc["spec"]["source"]["git"]["revision"]
            assert revision == branch, f"{path}: revision '{revision}' != branch '{branch}'"

    def test_component_spec_application_matches_versioned(self, full_container_krd):
        krd_dir, data = full_container_krd
        definition = data["definitions"][0]
        _, _, versioned = onboard_product.get_branch_info(definition)
        comp_docs = [
            (p, d)
            for p, d in iter_yaml_files(krd_dir, exclude={"kustomization.yaml"})
            if d.get("kind") == "Component"
        ]
        for path, doc in comp_docs:
            assert doc["spec"]["application"] == versioned, f"{path}: spec.application mismatch"


# ---------------------------------------------------------------------------
# KRD: ImageRepository resources
# ---------------------------------------------------------------------------


class TestKRDImageRepositoryResources:
    def test_imagerepository_required_fields(self, full_container_krd):
        krd_dir, _ = full_container_krd
        ir_docs = [
            (p, d)
            for p, d in iter_yaml_files(krd_dir, exclude={"kustomization.yaml"})
            if d.get("kind") == "ImageRepository"
        ]
        assert ir_docs, "No ImageRepository resources found"
        for path, doc in ir_docs:
            assert "apiVersion" in doc, f"{path}: missing apiVersion"
            assert "metadata" in doc and "name" in doc["metadata"], f"{path}: missing metadata.name"
            assert "labels" in doc["metadata"], f"{path}: missing metadata.labels"


# ---------------------------------------------------------------------------
# KRD: ReleasePlan resources
# ---------------------------------------------------------------------------


class TestKRDReleasePlanResources:
    def test_releaseplan_required_fields(self, full_container_krd):
        krd_dir, _ = full_container_krd
        rp_docs = [
            (p, d)
            for p, d in iter_yaml_files(krd_dir, exclude={"kustomization.yaml"})
            if d.get("kind") == "ReleasePlan"
        ]
        assert rp_docs, "No ReleasePlan resources found"
        for path, doc in rp_docs:
            assert "apiVersion" in doc, f"{path}: missing apiVersion"
            assert "metadata" in doc and "name" in doc["metadata"], f"{path}: missing metadata.name"
            spec = doc.get("spec", {})
            assert "application" in spec, f"{path}: missing spec.application"
            assert "target" in spec, f"{path}: missing spec.target"

    def test_releaseplan_spec_application_matches_versioned(self, full_container_krd):
        krd_dir, data = full_container_krd
        definition = data["definitions"][0]
        _, _, versioned = onboard_product.get_branch_info(definition)
        rp_docs = [
            (p, d)
            for p, d in iter_yaml_files(krd_dir, exclude={"kustomization.yaml"})
            if d.get("kind") == "ReleasePlan"
        ]
        for path, doc in rp_docs:
            assert doc["spec"]["application"] == versioned, f"{path}: spec.application mismatch"


# ---------------------------------------------------------------------------
# KRD: ReleasePlanAdmission resources
# ---------------------------------------------------------------------------


class TestKRDReleasePlanAdmissionResources:
    def test_rpa_required_fields(self, full_container_krd):
        krd_dir, _ = full_container_krd
        rpa_docs = [
            (p, d)
            for p, d in iter_yaml_files(krd_dir, exclude={"kustomization.yaml"})
            if d.get("kind") == "ReleasePlanAdmission"
        ]
        assert rpa_docs, "No ReleasePlanAdmission resources found"
        for path, doc in rpa_docs:
            assert "apiVersion" in doc, f"{path}: missing apiVersion"
            assert "metadata" in doc and "name" in doc["metadata"], f"{path}: missing metadata.name"
            spec = doc.get("spec", {})
            assert "applications" in spec, f"{path}: missing spec.applications"
            assert "policy" in spec, f"{path}: missing spec.policy"
            assert "data" in spec, f"{path}: missing spec.data"


# ---------------------------------------------------------------------------
# KRD: Kustomization files
# ---------------------------------------------------------------------------


class TestKRDKustomizationFiles:
    def test_kustomization_required_fields(self, full_container_krd):
        krd_dir, _ = full_container_krd
        for root, _dirs, files in os.walk(krd_dir):
            if "kustomization.yaml" in files:
                path = Path(root) / "kustomization.yaml"
                doc = load_yaml(path)
                assert "apiVersion" in doc, f"{path}: missing apiVersion"
                assert doc.get("kind") == "Kustomization", f"{path}: kind is not Kustomization"
                assert "resources" in doc, f"{path}: missing resources"

    def test_kustomization_resources_sorted_no_duplicates(self, full_container_krd):
        krd_dir, _ = full_container_krd
        for root, _dirs, files in os.walk(krd_dir):
            if "kustomization.yaml" in files:
                path = Path(root) / "kustomization.yaml"
                doc = load_yaml(path)
                resources = doc.get("resources", [])
                assert resources == sorted(resources), f"{path}: resources not sorted"
                assert len(resources) == len(set(resources)), f"{path}: duplicate resources"

    def test_kustomization_resources_exist_on_disk(self, full_container_krd):
        krd_dir, _ = full_container_krd
        for root, _dirs, files in os.walk(krd_dir):
            if "kustomization.yaml" in files:
                path = Path(root) / "kustomization.yaml"
                doc = load_yaml(path)
                for resource in doc.get("resources", []):
                    resource_path = Path(root) / resource
                    assert resource_path.exists(), (
                        f"{path}: resource '{resource}' does not exist on disk"
                    )


# ---------------------------------------------------------------------------
# KRD: Branch-aware naming consistency
# ---------------------------------------------------------------------------


class TestKRDBranchNamingConsistency:
    def _collect_names_by_kind(self, krd_dir, kind):
        return [
            doc["metadata"]["name"]
            for _, doc in iter_yaml_files(krd_dir, exclude={"kustomization.yaml"})
            if doc.get("kind") == kind
        ]

    @pytest.fixture(scope="class")
    def main_branch_krd(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("main_krd")
        data = {
            "definitions": [
                {
                    "application": "my-app",
                    "tenant": "my-tenant",
                    "branch": "main",
                    "components": {
                        "common": {},
                        "items": [
                            {
                                "name": "my-comp",
                                "url": "https://gitlab.com/org/repo/comp",
                                "pipelinerun": [
                                    {
                                        "pipeline": "full-container",
                                        "build_args_file": "b.conf",
                                        "additional_build_secret": "sec",
                                    }
                                ],
                            }
                        ],
                    },
                    "release_plan": [{"name": "stage", "grace_period": 7}],
                    "release_plan_admission": {
                        "common": {},
                        "rpas": [
                            {
                                "name": "stage",
                                "policy": "p",
                                "service_account": "sa",
                                "pipeline_path": "pipe.yaml",
                                "intention": "staging",
                                "product_name": "P",
                                "product_version": "1.0.0",
                            }
                        ],
                    },
                }
            ]
        }
        onboard_product.render_krd_templates(data, str(TEMPLATES_KRD), str(tmp), "stone-prod-p02")
        return tmp, data

    def test_main_branch_resources_have_no_suffix(self, main_branch_krd):
        krd_dir, data = main_branch_krd
        app_name = data["definitions"][0]["application"]
        comp_name = data["definitions"][0]["components"]["items"][0]["name"]

        app_names = self._collect_names_by_kind(krd_dir, "Application")
        assert app_names, "No Application resources found"
        assert all(n == app_name for n in app_names), (
            f"Main branch Application should be '{app_name}', got: {app_names}"
        )

        comp_names = self._collect_names_by_kind(krd_dir, "Component")
        assert comp_names, "No Component resources found"
        assert all(n == comp_name for n in comp_names), (
            f"Main branch Component should be '{comp_name}', got: {comp_names}"
        )

        rp_names = self._collect_names_by_kind(krd_dir, "ReleasePlan")
        assert rp_names, "No ReleasePlan resources found"
        assert all("-main" not in n for n in rp_names), (
            f"Main branch ReleasePlan should not contain '-main' suffix: {rp_names}"
        )

    def test_all_resources_use_versioned_app_name(self, full_container_krd):
        krd_dir, data = full_container_krd
        definition = data["definitions"][0]
        _, normalized_branch, versioned = onboard_product.get_branch_info(definition)

        app_names = self._collect_names_by_kind(krd_dir, "Application")
        assert all(n == versioned for n in app_names), f"Application name mismatch: {app_names}"

        comp_names = self._collect_names_by_kind(krd_dir, "Component")
        assert all(normalized_branch in n for n in comp_names), (
            f"Component names missing branch suffix: {comp_names}"
        )

        rp_names = self._collect_names_by_kind(krd_dir, "ReleasePlan")
        assert all(normalized_branch in n for n in rp_names), (
            f"ReleasePlan names missing branch suffix: {rp_names}"
        )


# ---------------------------------------------------------------------------
# Pipelinerun: Tekton structure
# ---------------------------------------------------------------------------


class TestPipelinerunTektonStructure:
    def test_pipelinerun_required_fields(self, full_container_pipelinerun):
        pr_dir, _ = full_container_pipelinerun
        pr_docs = list(iter_yaml_files(pr_dir))
        assert pr_docs, "No pipelinerun files found"
        for path, doc in pr_docs:
            assert doc.get("apiVersion") == "tekton.dev/v1", f"{path}: wrong apiVersion"
            assert doc.get("kind") == "PipelineRun", f"{path}: wrong kind"
            meta = doc.get("metadata", {})
            assert "name" in meta, f"{path}: missing metadata.name"
            assert "namespace" in meta, f"{path}: missing metadata.namespace"
            assert "labels" in meta, f"{path}: missing metadata.labels"
            assert "annotations" in meta, f"{path}: missing metadata.annotations"
            spec = doc.get("spec", {})
            assert "pipelineRef" in spec, f"{path}: missing spec.pipelineRef"
            assert "params" in spec, f"{path}: missing spec.params"


# ---------------------------------------------------------------------------
# Pipelinerun: Disabled component and placeholder tests
# ---------------------------------------------------------------------------


class TestDisabledComponent:
    """Invariant tests for disabled components and placeholder generation."""

    def test_cel_expression_disabled_full_container(self, tmp_path):
        config_data = {
            "definitions": [
                {
                    "application": "app",
                    "tenant": "tenant",
                    "branch": "main",
                    "components": {
                        "items": [
                            {
                                "name": "comp-tags",
                                "url": "https://gitlab.com/org/repo/comp-tags",
                                "disabled": True,
                                "pipelinerun": [
                                    {
                                        "pipeline": "full-container",
                                        "build_args_file": "args.conf",
                                        "cel_push_tag_prefixes": ["v"],
                                    }
                                ],
                            },
                            {
                                "name": "comp-plain",
                                "url": "https://gitlab.com/org/repo/comp-plain",
                                "disabled": True,
                                "pipelinerun": [
                                    {
                                        "pipeline": "full-container",
                                        "build_args_file": "args.conf",
                                    }
                                ],
                            },
                        ]
                    },
                }
            ]
        }
        onboard_product.render_pipelinerun_templates(
            config_data, str(TEMPLATES_PIPELINERUN), str(tmp_path)
        )

        files = list(iter_yaml_files(tmp_path))
        assert len(files) == 4, f"Expected 4 pipelinerun files, got {len(files)}"
        for pr_path, doc in files:
            cel = doc["metadata"]["annotations"]["pipelinesascode.tekton.dev/on-cel-expression"]
            assert cel.rstrip().endswith(") && false"), (
                f"{pr_path}: CEL expression does not end with ') && false': {cel!r}"
            )

    def test_cel_expression_non_disabled_no_false(self, full_container_pipelinerun):
        pr_dir, _ = full_container_pipelinerun
        non_disabled_files = [
            (p, d) for p, d in iter_yaml_files(pr_dir) if "test-component-2" in p.name
        ]
        assert non_disabled_files, "No non-disabled component files found"
        for path, doc in non_disabled_files:
            cel = (
                doc.get("metadata", {})
                .get("annotations", {})
                .get("pipelinesascode.tekton.dev/on-cel-expression", "")
            )
            assert "&& false" not in cel, f"{path}: found '&& false' in non-disabled CEL expression"

    def test_cel_expression_disabled_disk_image(self, tmp_path):
        config_data = {
            "definitions": [
                {
                    "application": "app",
                    "tenant": "tenant",
                    "branch": "main",
                    "components": {
                        "items": [
                            {
                                "name": "disk-comp",
                                "url": "https://gitlab.com/org/repo/disk-comp",
                                "disabled": True,
                                "pipelinerun": [
                                    {
                                        "pipeline": "disk-image",
                                        "image_type": "qcow2",
                                        "config_toml": "config.toml",
                                    }
                                ],
                            }
                        ]
                    },
                }
            ]
        }
        onboard_product.render_pipelinerun_templates(
            config_data, str(TEMPLATES_PIPELINERUN), str(tmp_path)
        )
        files = list(iter_yaml_files(tmp_path))
        assert files, "No disk-image pipelinerun files generated"
        for path, doc in files:
            cel = doc["metadata"]["annotations"]["pipelinesascode.tekton.dev/on-cel-expression"]
            assert cel.rstrip().endswith(") && false"), (
                f"{path}: disk-image CEL expression does not end with ') && false': {cel!r}"
            )

    def test_placeholder_creation_context_prefixed(self, tmp_path):
        config_data = {
            "definitions": [
                {
                    "application": "app",
                    "tenant": "tenant",
                    "branch": "main",
                    "components": {
                        "items": [
                            {
                                "name": "comp-1",
                                "context": "./sub/dir",
                                "dockerfile": "CustomDockerfile",
                                "url": "https://gitlab.com/org/repo/comp-1",
                                "disabled": True,
                                "pipelinerun": [
                                    {
                                        "pipeline": "full-container",
                                        "build_args_file": "build-args/custom.conf",
                                    }
                                ],
                            }
                        ]
                    },
                }
            ]
        }
        onboard_product.render_pipelinerun_templates(
            config_data, str(TEMPLATES_PIPELINERUN), str(tmp_path)
        )

        containerfile_path = tmp_path / "org" / "repo/comp-1" / "sub" / "dir" / "CustomDockerfile"
        argfile_path = (
            tmp_path / "org" / "repo/comp-1" / "sub" / "dir" / "build-args" / "custom.conf"
        )

        assert containerfile_path.exists(), f"Containerfile missing at {containerfile_path}"
        assert argfile_path.exists(), f"argfile missing at {argfile_path}"

        containerfile_content = containerfile_path.read_text()
        argfile_content = argfile_path.read_text()

        assert "PLACEHOLDER — generated by PMT" in containerfile_content
        assert "FROM scratch" in containerfile_content
        assert "ARG PLACEHOLDER" in containerfile_content

        assert "PLACEHOLDER — generated by PMT" in argfile_content
        assert "PLACEHOLDER=placeholder" in argfile_content

    def test_placeholder_no_overwrite(self, tmp_path):
        repo_dir = tmp_path / "org" / "repo/comp-1" / "sub" / "dir"
        repo_dir.mkdir(parents=True, exist_ok=True)
        containerfile_path = repo_dir / "Containerfile"
        argfile_path = repo_dir / "args.conf"

        sentinel_cfile = "FROM alpine\n# Existing"
        sentinel_argfile = "MY_ARG=value"
        containerfile_path.write_text(sentinel_cfile)
        argfile_path.write_text(sentinel_argfile)

        config_data = {
            "definitions": [
                {
                    "application": "app",
                    "tenant": "tenant",
                    "branch": "main",
                    "components": {
                        "items": [
                            {
                                "name": "comp-1",
                                "context": "./sub/dir",
                                "url": "https://gitlab.com/org/repo/comp-1",
                                "disabled": True,
                                "pipelinerun": [
                                    {
                                        "pipeline": "full-container",
                                        "build_args_file": "args.conf",
                                    }
                                ],
                            }
                        ]
                    },
                }
            ]
        }
        onboard_product.render_pipelinerun_templates(
            config_data, str(TEMPLATES_PIPELINERUN), str(tmp_path)
        )

        assert containerfile_path.read_text() == sentinel_cfile
        assert argfile_path.read_text() == sentinel_argfile

    def test_placeholder_not_created_when_not_disabled_or_disk_image(self, tmp_path):
        config_data = {
            "definitions": [
                {
                    "application": "app",
                    "tenant": "tenant",
                    "branch": "main",
                    "components": {
                        "items": [
                            {
                                "name": "active-comp",
                                "context": "./sub1",
                                "url": "https://gitlab.com/org/repo/active",
                                "disabled": False,
                                "pipelinerun": [
                                    {
                                        "pipeline": "full-container",
                                        "build_args_file": "args1.conf",
                                    }
                                ],
                            },
                            {
                                "name": "disabled-disk",
                                "context": "./sub2",
                                "url": "https://gitlab.com/org/repo/disk",
                                "disabled": True,
                                "pipelinerun": [
                                    {
                                        "pipeline": "disk-image",
                                        "image_type": "qcow2",
                                        "config_toml": "config.toml",
                                    }
                                ],
                            },
                        ]
                    },
                }
            ]
        }
        onboard_product.render_pipelinerun_templates(
            config_data, str(TEMPLATES_PIPELINERUN), str(tmp_path)
        )

        active_dir = tmp_path / "org" / "repo/active" / "sub1"
        disk_dir = tmp_path / "org" / "repo/disk" / "sub2"

        assert not (active_dir / "Containerfile").exists()
        assert not (active_dir / "args1.conf").exists()

        assert not (disk_dir / "Containerfile").exists()
        assert not (disk_dir / "config.toml").exists()

    def test_krd_output_unchanged_for_disabled_component(self, tmp_path_factory):
        tmp1 = tmp_path_factory.mktemp("krd_enabled")
        tmp2 = tmp_path_factory.mktemp("krd_disabled")

        def make_config(disabled):
            return {
                "definitions": [
                    {
                        "application": "app",
                        "tenant": "tenant",
                        "branch": "main",
                        "components": {
                            "items": [
                                {
                                    "name": "comp-1",
                                    "url": "https://gitlab.com/org/repo/comp-1",
                                    "disabled": disabled,
                                    "pipelinerun": [
                                        {
                                            "pipeline": "full-container",
                                            "build_args_file": "args.conf",
                                        }
                                    ],
                                }
                            ]
                        },
                    }
                ]
            }

        onboard_product.render_krd_templates(make_config(False), str(TEMPLATES_KRD), str(tmp1))
        onboard_product.render_krd_templates(make_config(True), str(TEMPLATES_KRD), str(tmp2))

        files1 = {p.relative_to(tmp1): load_yaml(p) for p, _ in iter_yaml_files(tmp1)}
        files2 = {p.relative_to(tmp2): load_yaml(p) for p, _ in iter_yaml_files(tmp2)}

        assert files1 == files2


# ---------------------------------------------------------------------------
# Pipelinerun: CEL expressions
# ---------------------------------------------------------------------------


class TestPipelinerunCELExpressions:
    def _get_cel(self, doc):
        return (
            doc.get("metadata", {})
            .get("annotations", {})
            .get("pipelinesascode.tekton.dev/on-cel-expression", "")
        )

    def test_pull_request_cel_references_branch(self, full_container_pipelinerun):
        pr_dir, data = full_container_pipelinerun
        branch = data["definitions"][0].get("branch", "main")
        pr_files = [(p, d) for p, d in iter_yaml_files(pr_dir) if "on-pull-request" in p.name]
        assert pr_files, "No pull-request pipelinerun files found"
        for path, doc in pr_files:
            cel = self._get_cel(doc)
            assert branch in cel, f"{path}: branch '{branch}' not in CEL: {cel[:200]}"

    def test_push_without_tag_prefixes_references_branch(self, disk_image_pipelinerun):
        # disk-image config has no cel_push_tag_prefixes
        pr_dir, data = disk_image_pipelinerun
        branch = data["definitions"][0].get("branch", "main")
        push_files = [(p, d) for p, d in iter_yaml_files(pr_dir) if "on-push" in p.name]
        assert push_files, "No push pipelinerun files found"
        for path, doc in push_files:
            cel = self._get_cel(doc)
            assert branch in cel, f"{path}: branch '{branch}' not in push CEL"

    def test_cel_path_changed_entries_present(self, full_container_pipelinerun):
        pr_dir, data = full_container_pipelinerun
        # The first component has cel_path_changed: ["ci", "context/app/***", ...]
        pr_files = [
            (p, d)
            for p, d in iter_yaml_files(pr_dir)
            if "test-component-1-on-pull-request" in p.name
        ]
        assert pr_files, "test-component-1-on-pull-request not found"
        for path, doc in pr_files:
            cel = self._get_cel(doc)
            assert "pathChanged()" in cel, f"{path}: pathChanged() not in CEL"
            assert '"ci".pathChanged()' in cel, f"{path}: 'ci' pathChanged not in CEL"

    def test_cel_path_changed_is_not_context_prefixed(self, full_container_pipelinerun):
        # cel_path_changed entries are repo-root-relative and must be emitted
        # verbatim, even when the component has a non-"." context. Only
        # context_cel_path_changed gets the prefix.
        pr_dir, _ = full_container_pipelinerun
        pr_files = [
            (p, d)
            for p, d in iter_yaml_files(pr_dir)
            if "test-component-1-on-pull-request" in p.name
        ]
        assert pr_files, "test-component-1-on-pull-request not found"
        for path, doc in pr_files:
            cel = self._get_cel(doc)
            for entry in ("ci", "context/app/***", "context/test-variant/repo/*"):
                assert f'"{entry}".pathChanged()' in cel, (
                    f"{path}: root-relative '{entry}' should be verbatim in CEL"
                )
                assert f'"test-context/{entry}".pathChanged()' not in cel, (
                    f"{path}: root-relative '{entry}' must NOT be context-prefixed"
                )

    def test_context_cel_path_changed_is_prefixed(self, full_container_pipelinerun):
        # context_cel_path_changed entries are relative to the component context
        # (./test-context) and must be prefixed, with {variant} still expanded.
        pr_dir, _ = full_container_pipelinerun
        pr_files = [
            (p, d)
            for p, d in iter_yaml_files(pr_dir)
            if "test-component-1-on-pull-request" in p.name
        ]
        assert pr_files, "test-component-1-on-pull-request not found"
        for path, doc in pr_files:
            cel = self._get_cel(doc)
            assert '"test-context/scripts/***".pathChanged()' in cel, (
                f"{path}: context_cel_path_changed entry not context-prefixed"
            )
            assert '"test-context/test-variant/overlay/***".pathChanged()' in cel, (
                f"{path}: context_cel_path_changed {{variant}} entry not prefixed/expanded"
            )
            assert "{variant}" not in cel, f"{path}: literal {{variant}} left in CEL"

    def test_disk_image_context_prefix_applied_everywhere(self, disk_image_pipelinerun):
        # test-disk-image.yaml uses a non-"." context (./test-disk-context), so
        # every repo-root-relative param AND every CEL pathChanged() path that
        # points at the component's own tree must carry the context prefix.
        # Guards against prefixing some paths (dockerfile/path-context) but not
        # others (config-toml); a regenerated golden fixture cannot catch this.
        pr_dir, _ = disk_image_pipelinerun
        prefix = "test-disk-context/"
        # Params that resolve against the git checkout root (task-resolved).
        prefixed_params = ("path-context", "config-toml", "bib-file")
        files = list(iter_yaml_files(pr_dir))
        assert files, "No disk-image pipelinerun files found"
        for path, doc in files:
            params = {
                p["name"]: p["value"] for p in doc.get("spec", {}).get("params", []) if "name" in p
            }
            for name in prefixed_params:
                assert name in params, f"{path}: expected param '{name}'"
                assert params[name].startswith(prefix), (
                    f"{path}: param '{name}' not context-prefixed: {params[name]!r}"
                )
            # config_toml and dockerfile also appear in the CEL expression.
            cel = self._get_cel(doc)
            assert f'"{prefix}config/config-test-iso.toml".pathChanged()' in cel, (
                f"{path}: config_toml pathChanged not context-prefixed in CEL"
            )
            assert f'"{prefix}TestDiskContainerfile".pathChanged()' in cel, (
                f"{path}: dockerfile pathChanged not context-prefixed in CEL"
            )

    def test_variant_placeholder_replaced(self, full_container_pipelinerun):
        pr_dir, _ = full_container_pipelinerun
        for path, doc in iter_yaml_files(pr_dir):
            cel = self._get_cel(doc)
            assert "{variant}" not in cel, f"{path}: literal {{variant}} found in CEL"


# ---------------------------------------------------------------------------
# Pipelinerun: Labels
# ---------------------------------------------------------------------------


class TestPipelinerunLabels:
    def _get_pipelinerun_labels_annotation(self, doc):
        # Labels are in the YAML labels section under metadata
        return doc.get("metadata", {}).get("labels", {})

    def test_pr_labels_contain_application_and_component(self, full_container_pipelinerun):
        pr_dir, data = full_container_pipelinerun
        definition = data["definitions"][0]
        _, _, versioned = onboard_product.get_branch_info(definition)
        for path, doc in iter_yaml_files(pr_dir):
            labels = doc.get("metadata", {}).get("labels", {})
            assert labels.get("appstudio.openshift.io/application") == versioned, (
                f"{path}: missing or wrong application label"
            )
            assert "appstudio.openshift.io/component" in labels, f"{path}: missing component label"

    def test_use_build_args_removes_name_component_labels(self, full_container_pipelinerun):
        # test-component-1 has use_build_args=true; name/component labels should not be in build-args param
        pr_dir, _ = full_container_pipelinerun
        for path, doc in iter_yaml_files(pr_dir):
            if "test-component-1" not in path.name:
                continue
            # Check image-label param does not contain name= or com.redhat.component=
            params = {
                p["name"]: p["value"] for p in doc.get("spec", {}).get("params", []) if "name" in p
            }
            if "image-labels" in params:
                label_val = params["image-labels"]
                assert "name=" not in label_val, (
                    f"{path}: name= label should not appear when use_build_args=true"
                )
                assert "com.redhat.component=" not in label_val, (
                    f"{path}: com.redhat.component= should not appear when use_build_args=true"
                )

    def test_cpe_label_format(self, full_container_pipelinerun):
        # The test-full-container config has cpe config and a prod RPA with product_version 1.0.0
        pr_dir, _ = full_container_pipelinerun
        for path, doc in iter_yaml_files(pr_dir):
            params = {
                p["name"]: p["value"] for p in doc.get("spec", {}).get("params", []) if "name" in p
            }
            if "image-labels" in params:
                label_val = str(params["image-labels"])
                if "cpe=" in label_val:
                    # Extract the cpe value
                    for part in label_val.split():
                        if part.startswith("cpe="):
                            cpe = part[4:]
                            assert cpe.startswith("cpe:/a:redhat:"), (
                                f"{path}: CPE format wrong: {cpe}"
                            )
                            # Should have major.minor not full version
                            parts = cpe.split(":")
                            assert len(parts) >= 6, (
                                f"{path}: CPE has wrong number of segments: {cpe}"
                            )
        # CPE label may not appear in all generated files, that's ok
        # We just verify format when it appears

    def test_cpe_label_generated_without_prod_rpa(self, stage_only_pipelinerun):
        """CPE label must be generated even when only stage RPAs exist."""
        pr_dir, _ = stage_only_pipelinerun
        found_cpe = False
        for path, doc in iter_yaml_files(pr_dir):
            params = {
                p["name"]: p["value"] for p in doc.get("spec", {}).get("params", []) if "name" in p
            }
            if "labels" in params:
                label_list = params["labels"]
                cpe_labels = [label for label in label_list if label.startswith("cpe=")]
                if cpe_labels:
                    found_cpe = True
                    assert cpe_labels[0] == "cpe=cpe:/a:redhat:test_product:1.0::el9", (
                        f"{path}: wrong CPE value: {cpe_labels[0]}"
                    )
        assert found_cpe, "No CPE label found in any stage-only pipelinerun"

    def test_name_component_labels_from_prod_repository_without_prod_rpa(
        self, stage_only_pipelinerun
    ):
        """name/com.redhat.component labels derived from prod_repository, even without prod RPA."""
        pr_dir, _ = stage_only_pipelinerun
        found = False
        for path, doc in iter_yaml_files(pr_dir):
            if "test-comp-with-prod-repo" not in path.name:
                continue
            params = {
                p["name"]: p["value"] for p in doc.get("spec", {}).get("params", []) if "name" in p
            }
            assert "labels" in params, f"{path}: missing labels param"
            label_list = params["labels"]
            assert "name=test-ns/test-comp" in label_list, (
                f"{path}: missing name label: {label_list}"
            )
            assert "com.redhat.component=test-ns/test-comp-container" in label_list, (
                f"{path}: missing com.redhat.component label: {label_list}"
            )
            found = True
        assert found, "No pipelinerun found for test-comp-with-prod-repo"

    def test_name_component_labels_from_stage_repository_fallback(self, stage_only_pipelinerun):
        """Without prod_repository, name/component derived from stage_repository."""
        pr_dir, _ = stage_only_pipelinerun
        found = False
        for path, doc in iter_yaml_files(pr_dir):
            if "test-comp-no-prod-repo" not in path.name:
                continue
            params = {
                p["name"]: p["value"] for p in doc.get("spec", {}).get("params", []) if "name" in p
            }
            assert "labels" in params, f"{path}: missing labels param"
            label_list = params["labels"]
            # stage_repository quay.io/test-org/test-comp-2-stage → test-org/test-comp-2-stage
            assert "name=test-org/test-comp-2-stage" in label_list, (
                f"{path}: missing name label from stage_repository: {label_list}"
            )
            assert "com.redhat.component=test-org/test-comp-2-stage-container" in label_list, (
                f"{path}: missing com.redhat.component label from stage_repository: {label_list}"
            )
            # CPE should also be there
            cpe_labels = [label for label in label_list if label.startswith("cpe=")]
            assert cpe_labels, f"{path}: CPE label missing"
            found = True
        assert found, "No pipelinerun found for test-comp-no-prod-repo"

    def test_config_labels_appear_in_output(self, full_container_pipelinerun):
        """Config-defined labels (common + per-component) appear in generated pipelineruns."""
        pr_dir, _ = full_container_pipelinerun
        for path, doc in iter_yaml_files(pr_dir):
            params = {
                p["name"]: p["value"] for p in doc.get("spec", {}).get("params", []) if "name" in p
            }
            if "labels" not in params:
                continue
            label_list = params["labels"]
            # Common label from common.pipelinerun.labels
            assert "maintainer=Test Vendor" in label_list, (
                f"{path}: missing common label 'maintainer=Test Vendor': {label_list}"
            )

    def test_per_component_labels_override_common(self, full_container_pipelinerun):
        """Per-component labels appear and merge with common labels."""
        pr_dir, _ = full_container_pipelinerun
        found = False
        for path, doc in iter_yaml_files(pr_dir):
            if "test-component-2" not in path.name:
                continue
            params = {
                p["name"]: p["value"] for p in doc.get("spec", {}).get("params", []) if "name" in p
            }
            assert "labels" in params, f"{path}: missing labels param"
            label_list = params["labels"]
            assert "io.openshift.tags=test component tags" in label_list, (
                f"{path}: missing per-component label: {label_list}"
            )
            assert "summary=Test Component 2 Summary" in label_list, (
                f"{path}: missing per-component summary label: {label_list}"
            )
            # Common label should still be present
            assert "maintainer=Test Vendor" in label_list, (
                f"{path}: common label missing after merge: {label_list}"
            )
            found = True
        assert found, "No pipelinerun found for test-component-2"

    def test_config_label_overrides_auto_generated_label(self, tmp_path):
        """Config-defined label with same key as auto-generated label wins."""
        config_data = {
            "definitions": [
                {
                    "application": "label-collision-test",
                    "tenant": "test-tenant",
                    "branch": "main",
                    "components": {
                        "common": {
                            "pipelinerun": {
                                "pipeline": "full-container",
                                "labels": ["cpe=custom-cpe-override"],
                            }
                        },
                        "items": [
                            {
                                "name": "collision-comp",
                                "url": "https://gitlab.com/test-org/collision-repo",
                                "stage_repository": "quay.io/test/collision-stage",
                                "prod_repository": "quay.io/test/collision-prod",
                                "pipelinerun": [{"build_args_file": "build.conf"}],
                            }
                        ],
                    },
                }
            ]
        }
        config_file = tmp_path / "label-collision.yaml"
        yaml.dump(config_data, config_file)
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        onboard_product.render_pipelinerun_templates(
            config_data, str(TEMPLATES_PIPELINERUN), str(out_dir)
        )
        for path, doc in iter_yaml_files(out_dir):
            params = {
                p["name"]: p["value"] for p in doc.get("spec", {}).get("params", []) if "name" in p
            }
            if "labels" not in params:
                continue
            label_list = params["labels"]
            cpe_labels = [label for label in label_list if label.startswith("cpe=")]
            assert len(cpe_labels) == 1, (
                f"{path}: expected exactly one cpe label, got: {cpe_labels}"
            )
            assert cpe_labels[0] == "cpe=custom-cpe-override", (
                f"{path}: config cpe should override auto-generated, got: {cpe_labels[0]}"
            )


# ---------------------------------------------------------------------------
# Pipelinerun: File pairs
# ---------------------------------------------------------------------------


class TestPipelinerunFilePairs:
    def test_both_pull_and_push_files_generated(self, full_container_pipelinerun):
        pr_dir, data = full_container_pipelinerun
        components = onboard_product.normalize_component_config(
            data["definitions"][0].get("components", [])
        )
        for component in components:
            base_name = component["name"]
            # Find the .tekton dirs
            tekton_files = set()
            for _root, _dirs, files in os.walk(pr_dir):
                for fname in files:
                    if base_name in fname:
                        tekton_files.add(fname)
            assert any("on-pull-request" in f for f in tekton_files), (
                f"Missing on-pull-request file for component '{base_name}'"
            )
            assert any("on-push" in f for f in tekton_files), (
                f"Missing on-push file for component '{base_name}'"
            )

    def test_both_pull_and_push_files_for_disk_image(self, disk_image_pipelinerun):
        pr_dir, data = disk_image_pipelinerun
        components = onboard_product.normalize_component_config(
            data["definitions"][0].get("components", [])
        )
        for component in components:
            base_name = component["name"]
            tekton_files = set()
            for _root, _dirs, files in os.walk(pr_dir):
                for fname in files:
                    if base_name in fname:
                        tekton_files.add(fname)
            assert any("on-pull-request" in f for f in tekton_files), (
                f"Missing on-pull-request for '{base_name}'"
            )
            assert any("on-push" in f for f in tekton_files), f"Missing on-push for '{base_name}'"


# ---------------------------------------------------------------------------
# Developer portal
# ---------------------------------------------------------------------------


class TestDeveloperPortalProperties:
    @pytest.fixture(scope="class")
    def dp_output(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("dp")
        config_file = CONFIGS_DIR / "test-developer-portal.yaml"
        with open(config_file) as f:
            data = yaml.load(f)
        onboard_product.render_developer_portal_templates(data, str(TEMPLATES_KRD), str(tmp))
        return tmp

    def test_version_files_required_camelcase_fields(self, dp_output):
        version_files = list(dp_output.rglob("*.yaml"))
        assert version_files, "No developer portal version files generated"
        for path in version_files:
            doc = load_yaml(path)
            assert "versionName" in doc, f"{path}: missing versionName"
            assert "ga" in doc, f"{path}: missing ga"
            assert "hidden" in doc, f"{path}: missing hidden"
            assert "releaseDate" in doc, f"{path}: missing releaseDate"

    def test_common_fields_inherited(self, tmp_path):
        """Common fields flow through to output when not overridden by the version entry.

        This is distinct from test_developer_portal_common_override in test_generation.py,
        which tests that version-level fields WIN over common. This test verifies the
        inheritance direction: common fields appear in output when the version doesn't override.
        """
        data = {
            "developer_portal_versions": [
                {
                    "product_slug": "my-product",
                    "common": {"ga": True, "hidden": False},
                    "versions": [
                        {"version_name": "1.0", "release_date": "2025-01-01"},
                    ],
                }
            ]
        }
        onboard_product.render_developer_portal_templates(data, str(TEMPLATES_KRD), str(tmp_path))
        version_file = (
            tmp_path / "data" / "external" / "developer-portal" / "my-product" / "1.0.yaml"
        )
        assert version_file.exists()
        doc = load_yaml(version_file)
        assert doc["ga"] is True
        assert doc["hidden"] is False


# ---------------------------------------------------------------------------
# Integration Test Scenarios (ITS)
# ---------------------------------------------------------------------------


class TestITSProperties:
    def test_its_required_fields(self, full_container_krd):
        krd_dir, _ = full_container_krd
        its_docs = [
            (p, d)
            for p, d in iter_yaml_files(krd_dir, exclude={"kustomization.yaml"})
            if d.get("kind") == "IntegrationTestScenario"
        ]
        assert its_docs, "No IntegrationTestScenario resources found"
        for path, doc in its_docs:
            assert "apiVersion" in doc, f"{path}: missing apiVersion"
            assert "metadata" in doc and "name" in doc["metadata"], f"{path}: missing metadata.name"
            spec = doc.get("spec", {})
            assert "application" in spec, f"{path}: missing spec.application"
            assert "contexts" in spec, f"{path}: missing spec.contexts"

    def test_its_branch_aware_naming(self, full_container_krd):
        krd_dir, data = full_container_krd
        definition = data["definitions"][0]
        app_name = definition["application"]
        branch = definition.get("branch", "main")
        normalized = onboard_product.canonicalize(branch)
        its_docs = [
            d
            for _, d in iter_yaml_files(krd_dir, exclude={"kustomization.yaml"})
            if d.get("kind") == "IntegrationTestScenario"
        ]
        for doc in its_docs:
            name = doc["metadata"]["name"]
            assert name.startswith(app_name), f"ITS name '{name}' doesn't start with app name"
            if branch != "main":
                assert normalized in name, f"ITS name '{name}' missing branch suffix '{normalized}'"

    def test_its_release_plan_admission_name_suffixed(self, full_container_krd):
        krd_dir, data = full_container_krd
        branch = data["definitions"][0].get("branch", "main")
        normalized = onboard_product.canonicalize(branch)
        its_docs = [
            (p, d)
            for p, d in iter_yaml_files(krd_dir, exclude={"kustomization.yaml"})
            if d.get("kind") == "IntegrationTestScenario"
        ]
        for path, doc in its_docs:
            params = doc.get("spec", {}).get("params", [])
            for param in params:
                if param.get("name") == "releasePlanAdmissionName":
                    value = str(param.get("value", ""))
                    if branch != "main":
                        assert value.endswith(f"-{normalized}"), (
                            f"{path}: releasePlanAdmissionName '{value}' missing branch suffix '-{normalized}'"
                        )
                        # Must not be doubled
                        assert not value.endswith(f"-{normalized}-{normalized}"), (
                            f"{path}: releasePlanAdmissionName '{value}' has doubled suffix"
                        )


# ---------------------------------------------------------------------------
# Tech-preview component filtering
# ---------------------------------------------------------------------------


class TestTechPreviewFiltering:
    def _make_data(self, components, rpas):
        return {
            "definitions": [
                {
                    "application": "test-app",
                    "tenant": "test-tenant",
                    "branch": "main",
                    "components": {"common": {}, "items": components},
                    "release_plan": [{"name": rpa["name"], "grace_period": 7} for rpa in rpas],
                    "release_plan_admission": {"common": {}, "rpas": rpas},
                }
            ]
        }

    def _get_rpa_component_names(self, krd_dir, rpa_name):
        for _, doc in iter_yaml_files(krd_dir, exclude={"kustomization.yaml"}):
            if doc.get("kind") == "ReleasePlanAdmission" and doc["metadata"]["name"] == rpa_name:
                components = (
                    doc.get("spec", {}).get("data", {}).get("mapping", {}).get("components") or []
                )
                return [c["name"] for c in components]
        return None

    def _base_component(self, name, tech_preview=False):
        return {
            "name": name,
            "url": f"https://gitlab.com/org/repo/{name}",
            "prod_repository": f"registry.io/org/{name}",
            "pipelinerun": [
                {
                    "pipeline": "full-container",
                    "build_args_file": "b.conf",
                    "additional_build_secret": "sec",
                }
            ],
            "tech_preview": tech_preview,
        }

    def test_stage_rpa_includes_all_components(self, tmp_path):
        components = [
            self._base_component("comp-regular"),
            self._base_component("comp-tp", tech_preview=True),
        ]
        rpas = [
            {
                "name": "stage",
                "policy": "p",
                "service_account": "sa",
                "pipeline_path": "pipe.yaml",
                "intention": "staging",
                "product_name": "P",
                "product_version": "1.0.0",
            }
        ]
        data = self._make_data(components, rpas)
        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02"
        )
        comp_names = self._get_rpa_component_names(tmp_path, "stage")
        assert comp_names is not None, "stage RPA not found"
        assert "comp-regular" in comp_names
        assert "comp-tp" in comp_names

    def test_regular_prod_rpa_excludes_tech_preview(self, tmp_path):
        components = [
            self._base_component("comp-regular"),
            self._base_component("comp-tp", tech_preview=True),
        ]
        rpas = [
            {
                "name": "prod",
                "policy": "p",
                "service_account": "sa",
                "pipeline_path": "pipe.yaml",
                "intention": "production",
                "product_name": "P",
                "product_version": "1.0.0",
            }
        ]
        data = self._make_data(components, rpas)
        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02"
        )
        comp_names = self._get_rpa_component_names(tmp_path, "prod")
        assert comp_names is not None, "prod RPA not found"
        assert "comp-regular" in comp_names
        assert "comp-tp" not in comp_names

    def test_tech_preview_prod_rpa_only_includes_tp_components(self, tmp_path):
        components = [
            self._base_component("comp-regular"),
            self._base_component("comp-tp", tech_preview=True),
        ]
        rpas = [
            {
                "name": "tech-preview-prod",
                "policy": "p",
                "service_account": "sa",
                "pipeline_path": "pipe.yaml",
                "intention": "production",
                "product_name": "P",
                "product_version": "1.0.0",
            }
        ]
        data = self._make_data(components, rpas)
        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02"
        )
        comp_names = self._get_rpa_component_names(tmp_path, "tech-preview-prod")
        assert comp_names is not None, "tech-preview-prod RPA not found"
        assert "comp-tp" in comp_names
        assert "comp-regular" not in comp_names

    def test_prod_rpa_skips_full_container_without_prod_repository(self, tmp_path):
        components = [
            {
                "name": "comp-no-repo",
                "url": "https://gitlab.com/org/repo/comp",
                "pipelinerun": [
                    {
                        "pipeline": "full-container",
                        "build_args_file": "b.conf",
                        "additional_build_secret": "sec",
                    }
                ],
            }
        ]
        rpas = [
            {
                "name": "prod",
                "policy": "p",
                "service_account": "sa",
                "pipeline_path": "pipe.yaml",
                "intention": "production",
                "product_name": "P",
                "product_version": "1.0.0",
            }
        ]
        data = self._make_data(components, rpas)
        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02"
        )
        comp_names = self._get_rpa_component_names(tmp_path, "prod")
        assert comp_names is not None
        assert "comp-no-repo" not in comp_names


# ---------------------------------------------------------------------------
# Recreate mode
# ---------------------------------------------------------------------------


class TestRecreateMode:
    def _base_data(self):
        return {
            "definitions": [
                {
                    "application": "my-app",
                    "tenant": "my-tenant",
                    "branch": "main",
                    "components": {
                        "common": {},
                        "items": [
                            {
                                "name": "my-comp",
                                "url": "https://gitlab.com/org/repo/comp",
                                "pipelinerun": [
                                    {
                                        "pipeline": "full-container",
                                        "build_args_file": "b.conf",
                                        "additional_build_secret": "sec",
                                    }
                                ],
                            }
                        ],
                    },
                    "release_plan": [{"name": "stage", "grace_period": 7}],
                    "release_plan_admission": {
                        "common": {},
                        "rpas": [
                            {
                                "name": "stage",
                                "policy": "p",
                                "service_account": "sa",
                                "pipeline_path": "pipe.yaml",
                                "intention": "staging",
                                "product_name": "P",
                                "product_version": "1.0.0",
                            }
                        ],
                    },
                }
            ]
        }

    def test_managed_subdirectories_removed_on_recreate(self, tmp_path):
        data = self._base_data()
        # First generation
        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02"
        )

        base = (
            tmp_path
            / "tenants-config"
            / "cluster"
            / "stone-prod-p02"
            / "tenants"
            / "my-tenant"
            / "my-app"
            / "main"
        )
        assert base.exists()
        # Create a stale file in applications/
        stale = base / "applications" / "stale-resource.yaml"
        stale.write_text("stale: true\n")

        # Recreate
        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02", recreate=True
        )
        assert not stale.exists(), "Stale file in managed directory should be removed on recreate"

    def test_non_managed_files_preserved_on_recreate(self, tmp_path):
        data = self._base_data()
        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02"
        )

        base = (
            tmp_path
            / "tenants-config"
            / "cluster"
            / "stone-prod-p02"
            / "tenants"
            / "my-tenant"
            / "my-app"
            / "main"
        )
        # Create a custom (non-managed) subdirectory
        custom_dir = base / "custom-resources"
        custom_dir.mkdir()
        custom_file = custom_dir / "custom.yaml"
        custom_file.write_text("custom: true\n")

        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02", recreate=True
        )
        assert custom_file.exists(), "Non-managed directory should be preserved on recreate"

    def test_stale_rpa_files_removed_on_recreate_rpa(self, tmp_path):
        data = self._base_data()
        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02"
        )

        rpa_dir = (
            tmp_path
            / "config"
            / "stone-prod-p02.hjvn.p1"
            / "product"
            / "ReleasePlanAdmission"
            / "my"
        )
        assert rpa_dir.exists()
        stale = rpa_dir / "old-stale-rpa.yaml"
        stale.write_text("stale: true\n")

        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02", recreate_rpa=True
        )
        assert not stale.exists(), "Stale RPA file should be removed on --recreate-rpa"
        rpa_files = list(rpa_dir.glob("*.yaml"))
        assert len(rpa_files) > 0, (
            "Freshly generated RPA files should be present after --recreate-rpa"
        )

    def test_recreate_without_recreate_rpa_preserves_rpa(self, tmp_path):
        data = self._base_data()
        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02"
        )

        rpa_dir = (
            tmp_path
            / "config"
            / "stone-prod-p02.hjvn.p1"
            / "product"
            / "ReleasePlanAdmission"
            / "my"
        )
        stale = rpa_dir / "old-stale-rpa.yaml"
        stale.write_text("stale: true\n")

        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02", recreate=True
        )
        assert stale.exists(), (
            "RPA files should be preserved when only --recreate is used (not --recreate-rpa)"
        )


class TestPipelinerunRecreateMode:
    def _base_data(self):
        return {
            "definitions": [
                {
                    "application": "my-app",
                    "tenant": "my-tenant",
                    "branch": "main",
                    "components": {
                        "common": {},
                        "items": [
                            {
                                "name": "my-comp",
                                "url": "https://gitlab.com/org/repo/comp",
                                "pipelinerun": [
                                    {
                                        "pipeline": "full-container",
                                        "build_args_file": "b.conf",
                                        "additional_build_secret": "sec",
                                    }
                                ],
                            }
                        ],
                    },
                    "release_plan": [{"name": "stage", "grace_period": 7}],
                    "release_plan_admission": {
                        "common": {},
                        "rpas": [
                            {
                                "name": "stage",
                                "policy": "p",
                                "service_account": "sa",
                                "pipeline_path": "pipe.yaml",
                                "intention": "staging",
                                "product_name": "P",
                                "product_version": "1.0.0",
                            }
                        ],
                    },
                }
            ]
        }

    def test_stale_tekton_files_removed_on_recreate(self, tmp_path):
        data = self._base_data()
        onboard_product.render_pipelinerun_templates(
            data, str(TEMPLATES_PIPELINERUN), str(tmp_path)
        )

        tekton_dir = tmp_path / "org" / "repo" / "comp" / ".tekton"
        assert tekton_dir.exists()
        stale = tekton_dir / "old-removed-component-on-push.yaml"
        stale.write_text("stale: true\n")

        onboard_product.render_pipelinerun_templates(
            data, str(TEMPLATES_PIPELINERUN), str(tmp_path), recreate=True
        )
        assert not stale.exists(), "Stale .yaml file in .tekton/ should be removed on recreate"
        generated_files = list(tekton_dir.glob("*.yaml"))
        assert len(generated_files) > 0, (
            "Freshly generated pipelinerun files should be present after recreate"
        )

    def test_tekton_non_yaml_files_preserved_on_recreate(self, tmp_path):
        data = self._base_data()
        onboard_product.render_pipelinerun_templates(
            data, str(TEMPLATES_PIPELINERUN), str(tmp_path)
        )

        tekton_dir = tmp_path / "org" / "repo" / "comp" / ".tekton"
        non_yaml = tekton_dir / "README.md"
        non_yaml.write_text("# Pipeline docs\n")

        onboard_product.render_pipelinerun_templates(
            data, str(TEMPLATES_PIPELINERUN), str(tmp_path), recreate=True
        )
        assert non_yaml.exists(), "Non-YAML files in .tekton/ should be preserved on recreate"

    def test_tekton_without_recreate_preserves_stale_files(self, tmp_path):
        data = self._base_data()
        onboard_product.render_pipelinerun_templates(
            data, str(TEMPLATES_PIPELINERUN), str(tmp_path)
        )

        tekton_dir = tmp_path / "org" / "repo" / "comp" / ".tekton"
        stale = tekton_dir / "old-component-on-push.yaml"
        stale.write_text("stale: true\n")

        onboard_product.render_pipelinerun_templates(
            data, str(TEMPLATES_PIPELINERUN), str(tmp_path), recreate=False
        )
        assert stale.exists(), "Stale files should be preserved when recreate is not set"


class TestRPARecreateMultiApp:
    """Tests for --recreate-rpa with multiple apps sharing a tenant."""

    def _two_app_data(self):
        """Two apps sharing 'my-tenant' — both produce RPAs in the same directory."""
        return {
            "definitions": [
                {
                    "application": "app-one",
                    "tenant": "my-tenant",
                    "branch": "main",
                    "components": {
                        "common": {},
                        "items": [
                            {
                                "name": "comp-one",
                                "url": "https://gitlab.com/org/repo/comp-one",
                                "pipelinerun": [
                                    {
                                        "pipeline": "full-container",
                                        "build_args_file": "b.conf",
                                        "additional_build_secret": "sec",
                                    }
                                ],
                            }
                        ],
                    },
                    "release_plan": [{"name": "app-one-stage", "grace_period": 7}],
                    "release_plan_admission": {
                        "common": {},
                        "rpas": [
                            {
                                "name": "app-one-stage",
                                "policy": "p",
                                "service_account": "sa",
                                "pipeline_path": "pipe.yaml",
                                "intention": "staging",
                                "product_name": "P1",
                                "product_version": "1.0.0",
                            }
                        ],
                    },
                },
                {
                    "application": "app-two",
                    "tenant": "my-tenant",
                    "branch": "main",
                    "components": {
                        "common": {},
                        "items": [
                            {
                                "name": "comp-two",
                                "url": "https://gitlab.com/org/repo/comp-two",
                                "pipelinerun": [
                                    {
                                        "pipeline": "full-container",
                                        "build_args_file": "b.conf",
                                        "additional_build_secret": "sec",
                                    }
                                ],
                            }
                        ],
                    },
                    "release_plan": [{"name": "app-two-stage", "grace_period": 7}],
                    "release_plan_admission": {
                        "common": {},
                        "rpas": [
                            {
                                "name": "app-two-stage",
                                "policy": "p",
                                "service_account": "sa",
                                "pipeline_path": "pipe.yaml",
                                "intention": "staging",
                                "product_name": "P2",
                                "product_version": "2.0.0",
                            }
                        ],
                    },
                },
            ]
        }

    def test_recreate_rpa_with_all_configs_regenerates_both(self, tmp_path):
        """When both apps are in the same run, --recreate-rpa cleans and regenerates all RPAs."""
        data = self._two_app_data()
        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02"
        )

        rpa_dir = (
            tmp_path
            / "config"
            / "stone-prod-p02.hjvn.p1"
            / "product"
            / "ReleasePlanAdmission"
            / "my"
        )
        stale = rpa_dir / "old-orphan.yaml"
        stale.write_text("stale: true\n")

        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02", recreate_rpa=True
        )
        assert not stale.exists(), "Stale RPA should be removed"
        rpa_files = sorted(f.name for f in rpa_dir.glob("*.yaml"))
        assert "app-one-stage.yaml" in rpa_files, "app-one RPA should be regenerated"
        assert "app-two-stage.yaml" in rpa_files, "app-two RPA should be regenerated"

    def test_recreate_rpa_single_app_removes_other_apps_rpas(self, tmp_path):
        """Documents the tenant-wide blast radius: running with one app's config deletes the other's RPAs."""
        both = self._two_app_data()
        onboard_product.render_krd_templates(
            both, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02"
        )

        rpa_dir = (
            tmp_path
            / "config"
            / "stone-prod-p02.hjvn.p1"
            / "product"
            / "ReleasePlanAdmission"
            / "my"
        )
        assert (rpa_dir / "app-two-stage.yaml").exists()

        single_app = {"definitions": [both["definitions"][0]]}
        onboard_product.render_krd_templates(
            single_app, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02", recreate_rpa=True
        )
        assert not (rpa_dir / "app-two-stage.yaml").exists(), (
            "--recreate-rpa with single app config removes other app's RPAs (tenant-wide scope)"
        )
        assert (rpa_dir / "app-one-stage.yaml").exists(), "Current app's RPA should be regenerated"


# ---------------------------------------------------------------------------
# Release plan / RPA name matching
# ---------------------------------------------------------------------------


class TestReleasePlanRPAMatching:
    def _base_data(self, release_plans, rpas):
        return {
            "definitions": [
                {
                    "application": "my-app",
                    "tenant": "my-tenant",
                    "branch": "main",
                    "components": {"common": {}, "items": []},
                    "release_plan": release_plans,
                    "release_plan_admission": {"common": {}, "rpas": rpas},
                }
            ]
        }

    def test_release_plan_without_matching_rpa_raises(self, tmp_path):
        data = self._base_data(
            release_plans=[{"name": "prod", "grace_period": 7}],
            rpas=[
                {
                    "name": "stage",
                    "policy": "p",
                    "service_account": "sa",
                    "pipeline_path": "p.yaml",
                    "intention": "staging",
                    "product_name": "P",
                    "product_version": "1.0.0",
                }
            ],
        )
        with pytest.raises(ValueError, match="no matching RPA"):
            onboard_product.render_krd_templates(
                data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02"
            )

    def test_orphaned_rpa_generates_warning(self, tmp_path, capsys):
        data = self._base_data(
            release_plans=[{"name": "stage", "grace_period": 7}],
            rpas=[
                {
                    "name": "stage",
                    "policy": "p",
                    "service_account": "sa",
                    "pipeline_path": "p.yaml",
                    "intention": "staging",
                    "product_name": "P",
                    "product_version": "1.0.0",
                },
                {
                    "name": "extra-rpa",
                    "policy": "p",
                    "service_account": "sa",
                    "pipeline_path": "p.yaml",
                    "intention": "staging",
                    "product_name": "P",
                    "product_version": "1.0.0",
                },
            ],
        )
        onboard_product.render_krd_templates(
            data, str(TEMPLATES_KRD), str(tmp_path), "stone-prod-p02"
        )
        captured = capsys.readouterr()
        assert "extra-rpa" in captured.out
        assert "no matching release plan" in captured.out.lower()


# ---------------------------------------------------------------------------
# Value assertion tests: config fields → generated output values
# ---------------------------------------------------------------------------


class TestKRDValueAssertions:
    """Verify that specific config values appear correctly in generated output.

    These tests catch regressions like "branch changed from 3.3 to 3.4 but the
    generated component still has revision: 3.3", or "policy name changed but
    the RPA still has the old value". They map config fields to output fields
    directly, independent of snapshot content.
    """

    def _find_docs_by_kind(self, krd_dir, kind):
        return [
            (p, d)
            for p, d in iter_yaml_files(krd_dir, exclude={"kustomization.yaml"})
            if d.get("kind") == kind
        ]

    def _find_rpa_by_exact_name(self, krd_dir, exact_name):
        for p, d in self._find_docs_by_kind(krd_dir, "ReleasePlanAdmission"):
            if d["metadata"]["name"] == exact_name:
                return p, d
        return None, None

    def _rpa_generated_name(self, cfg_rpa_name, normalized_branch):
        if normalized_branch == "main":
            return cfg_rpa_name
        return f"{cfg_rpa_name}-{normalized_branch}"

    def test_component_url_matches_config(self, full_container_krd):
        krd_dir, data = full_container_krd
        components = onboard_product.normalize_component_config(
            data["definitions"][0].get("components", [])
        )
        comp_docs = self._find_docs_by_kind(krd_dir, "Component")
        for cfg_comp in components:
            matching = [(p, d) for p, d in comp_docs if cfg_comp["name"] in d["metadata"]["name"]]
            assert matching, f"No Component found for '{cfg_comp['name']}'"
            for path, doc in matching:
                got_url = doc["spec"]["source"]["git"]["url"]
                assert got_url == cfg_comp["url"], (
                    f"{path}: url '{got_url}' != config url '{cfg_comp['url']}'"
                )

    def test_component_revision_matches_branch_value(self, full_container_krd):
        krd_dir, data = full_container_krd
        branch = data["definitions"][0].get("branch", "main")
        comp_docs = self._find_docs_by_kind(krd_dir, "Component")
        assert comp_docs, "No Component resources found"
        for path, doc in comp_docs:
            got = doc["spec"]["source"]["git"]["revision"]
            assert got == branch, f"{path}: revision '{got}' != branch '{branch}'"

    def test_rpa_policy_matches_config(self, full_container_krd):
        krd_dir, data = full_container_krd
        definition = data["definitions"][0]
        _, normalized, _ = onboard_product.get_branch_info(definition)
        rpas = onboard_product.normalize_rpa_config(definition.get("release_plan_admission", []))
        checked = 0
        for cfg_rpa in rpas:
            exact_name = self._rpa_generated_name(cfg_rpa["name"], normalized)
            _, doc = self._find_rpa_by_exact_name(krd_dir, exact_name)
            assert doc is not None, f"RPA '{exact_name}' not found in generated output"
            got = doc["spec"]["policy"]
            assert got == cfg_rpa["policy"], (
                f"RPA '{exact_name}': policy '{got}' != config '{cfg_rpa['policy']}'"
            )
            checked += 1
        assert checked > 0, "No RPAs were checked"

    def test_rpa_service_account_matches_config(self, full_container_krd):
        krd_dir, data = full_container_krd
        definition = data["definitions"][0]
        _, normalized, _ = onboard_product.get_branch_info(definition)
        rpas = onboard_product.normalize_rpa_config(definition.get("release_plan_admission", []))
        checked = 0
        for cfg_rpa in rpas:
            exact_name = self._rpa_generated_name(cfg_rpa["name"], normalized)
            _, doc = self._find_rpa_by_exact_name(krd_dir, exact_name)
            assert doc is not None, f"RPA '{exact_name}' not found in generated output"
            got = doc["spec"]["pipeline"]["serviceAccountName"]
            assert got == cfg_rpa["service_account"], (
                f"RPA '{exact_name}': serviceAccountName '{got}' != config '{cfg_rpa['service_account']}'"
            )
            checked += 1
        assert checked > 0, "No RPAs were checked"

    def test_rpa_intention_matches_config(self, full_container_krd):
        krd_dir, data = full_container_krd
        definition = data["definitions"][0]
        _, normalized, _ = onboard_product.get_branch_info(definition)
        rpas = onboard_product.normalize_rpa_config(definition.get("release_plan_admission", []))
        checked = 0
        for cfg_rpa in rpas:
            exact_name = self._rpa_generated_name(cfg_rpa["name"], normalized)
            _, doc = self._find_rpa_by_exact_name(krd_dir, exact_name)
            assert doc is not None, f"RPA '{exact_name}' not found in generated output"
            got = doc["spec"]["data"]["intention"]
            assert got == cfg_rpa["intention"], (
                f"RPA '{exact_name}': intention '{got}' != config '{cfg_rpa['intention']}'"
            )
            checked += 1
        assert checked > 0, "No RPAs were checked"

    def test_rpa_product_name_and_version_match_config(self, full_container_krd):
        krd_dir, data = full_container_krd
        definition = data["definitions"][0]
        _, normalized, _ = onboard_product.get_branch_info(definition)
        rpas = onboard_product.normalize_rpa_config(definition.get("release_plan_admission", []))
        checked = 0
        for cfg_rpa in rpas:
            exact_name = self._rpa_generated_name(cfg_rpa["name"], normalized)
            _, doc = self._find_rpa_by_exact_name(krd_dir, exact_name)
            assert doc is not None, f"RPA '{exact_name}' not found in generated output"
            release_notes = doc["spec"]["data"]["releaseNotes"]
            assert release_notes["product_name"] == cfg_rpa["product_name"], (
                f"RPA '{exact_name}': product_name mismatch"
            )
            assert str(release_notes["product_version"]) == str(cfg_rpa["product_version"]), (
                f"RPA '{exact_name}': product_version mismatch"
            )
            checked += 1
        assert checked > 0, "No RPAs were checked"

    def test_rpa_stage_repository_matches_config(self, full_container_krd):
        krd_dir, data = full_container_krd
        definition = data["definitions"][0]
        components = onboard_product.normalize_component_config(definition.get("components", []))
        branch, normalized, _ = onboard_product.get_branch_info(definition)

        stage_rpa_name = self._rpa_generated_name("test-release-plan-stage", normalized)
        _, stage_doc = self._find_rpa_by_exact_name(krd_dir, stage_rpa_name)
        assert stage_doc is not None, f"Stage RPA '{stage_rpa_name}' not found"

        rpa_components = stage_doc["spec"]["data"]["mapping"]["components"]
        rpa_by_name = {c["name"]: c for c in rpa_components}

        for cfg_comp in components:
            stage_repo = cfg_comp.get("stage_repository")
            if not stage_repo:
                continue
            comp_name = onboard_product.get_component_name(cfg_comp["name"], branch)
            assert comp_name in rpa_by_name, f"Component '{comp_name}' not in stage RPA"
            repos = [r["url"] for r in rpa_by_name[comp_name].get("repositories", [])]
            assert stage_repo in repos, (
                f"stage_repository '{stage_repo}' not found in RPA for '{comp_name}': {repos}"
            )

    def test_rpa_prod_repository_matches_config(self, full_container_krd):
        krd_dir, data = full_container_krd
        definition = data["definitions"][0]
        components = onboard_product.normalize_component_config(definition.get("components", []))
        branch, normalized, _ = onboard_product.get_branch_info(definition)

        prod_rpa_name = self._rpa_generated_name("test-release-plan-prod", normalized)
        _, prod_doc = self._find_rpa_by_exact_name(krd_dir, prod_rpa_name)
        assert prod_doc is not None, f"Prod RPA '{prod_rpa_name}' not found"

        rpa_components = prod_doc["spec"]["data"]["mapping"]["components"]
        rpa_by_name = {c["name"]: c for c in rpa_components}

        for cfg_comp in components:
            prod_repo = cfg_comp.get("prod_repository")
            if not prod_repo:
                continue
            comp_name = onboard_product.get_component_name(cfg_comp["name"], branch)
            assert comp_name in rpa_by_name, f"Component '{comp_name}' not in prod RPA"
            repos = [r["url"] for r in rpa_by_name[comp_name].get("repositories", [])]
            assert prod_repo in repos, (
                f"prod_repository '{prod_repo}' not found in RPA for '{comp_name}': {repos}"
            )

    def test_its_param_values_match_config(self, full_container_krd):
        krd_dir, data = full_container_krd
        its_configs = data["definitions"][0].get("integration_test_scenarios", [])
        its_docs = self._find_docs_by_kind(krd_dir, "IntegrationTestScenario")

        for cfg_its in its_configs:
            matching = [(p, d) for p, d in its_docs if cfg_its["name"] in d["metadata"]["name"]]
            assert matching, f"No ITS found for '{cfg_its['name']}'"
            for path, doc in matching:
                generated_params = {
                    p["name"]: p["value"] for p in doc.get("spec", {}).get("params", [])
                }
                for cfg_param in cfg_its.get("params", []):
                    param_name = cfg_param["name"]
                    expected = str(cfg_param["value"])
                    got = str(generated_params.get(param_name, ""))
                    assert got == expected, (
                        f"{path}: ITS param '{param_name}': got '{got}' != expected '{expected}'"
                    )
