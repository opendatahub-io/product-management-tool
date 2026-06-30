"""
Unit tests for pure functions in onboard-product.py and config.py.

These tests validate correctness of individual functions independently of
template rendering or file I/O, catching regressions that snapshot tests miss.
"""

import importlib.util
import os
from pathlib import Path

import pytest

from config import Config

spec = importlib.util.spec_from_file_location(
    "onboard_product",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "onboard-product.py"),
)
onboard_product = importlib.util.module_from_spec(spec)
spec.loader.exec_module(onboard_product)

# ---------------------------------------------------------------------------
# canonicalize
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        ("rhoai-2.23", "rhoai-2-23"),
        ("MyApp.V2", "myapp-v2"),
        ("already-canonical", "already-canonical"),
        ("a.b.c.d", "a-b-c-d"),
        ("UPPER", "upper"),
        ("no-dots", "no-dots"),
        ("1.2.3", "1-2-3"),
    ],
)
def test_canonicalize(value, expected):
    assert onboard_product.canonicalize(value) == expected


# ---------------------------------------------------------------------------
# get_application_name / get_component_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base_name, branch, expected",
    [
        ("llama-stack", "main", "llama-stack"),
        ("llama-stack", "rhoai-2.23", "llama-stack-rhoai-2-23"),
        ("my-app", "release-1.0", "my-app-release-1-0"),
        ("my-app", "feature-branch", "my-app-feature-branch"),
    ],
)
def test_get_application_name(base_name, branch, expected):
    assert onboard_product.get_application_name(base_name, branch) == expected


@pytest.mark.parametrize(
    "base_name, branch, expected",
    [
        ("bootc-cuda", "main", "bootc-cuda"),
        ("bootc-cuda", "rhoai-2.23", "bootc-cuda-rhoai-2-23"),
        ("my-component", "release-1.0", "my-component-release-1-0"),
    ],
)
def test_get_component_name(base_name, branch, expected):
    assert onboard_product.get_component_name(base_name, branch) == expected


# ---------------------------------------------------------------------------
# get_branch_info
# ---------------------------------------------------------------------------


def test_get_branch_info_explicit_branch():
    definition = {"application": "my-app", "branch": "rhoai-2.23"}
    branch, normalized, versioned = onboard_product.get_branch_info(definition)
    assert branch == "rhoai-2.23"
    assert normalized == "rhoai-2-23"
    assert versioned == "my-app-rhoai-2-23"


def test_get_branch_info_defaults_to_main():
    definition = {"application": "my-app"}
    branch, normalized, versioned = onboard_product.get_branch_info(definition)
    assert branch == "main"
    assert normalized == "main"
    assert versioned == "my-app"


def test_get_branch_info_main_branch():
    definition = {"application": "my-app", "branch": "main"}
    branch, normalized, versioned = onboard_product.get_branch_info(definition)
    assert branch == "main"
    assert normalized == "main"
    assert versioned == "my-app"


# ---------------------------------------------------------------------------
# yaml_value
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        (True, "true"),
        (False, "false"),
        ("hello", '"hello"'),
        ("", '""'),
        (42, 42),
        (0, 0),
        (3.14, 3.14),
        (0.0, 0.0),
    ],
)
def test_yaml_value(value, expected):
    assert onboard_product.yaml_value(value) == expected


def test_yaml_value_other_type():
    result = onboard_product.yaml_value(["a", "b"])
    assert result == "\"['a', 'b']\""


# ---------------------------------------------------------------------------
# parse_gitlab_url
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected_org, expected_repo",
    [
        (
            "https://gitlab.com/redhat/rhel-ai/llama-stack/containers",
            "redhat",
            "rhel-ai/llama-stack/containers",
        ),
        ("https://gitlab.com/myorg/myrepo", "myorg", "myrepo"),
        ("https://gitlab.com/a/b/c/d/e", "a", "b/c/d/e"),
    ],
)
def test_parse_gitlab_url_valid(url, expected_org, expected_repo):
    org, repo = onboard_product.parse_gitlab_url(url)
    assert org == expected_org
    assert repo == expected_repo


def test_parse_gitlab_url_too_few_segments():
    with pytest.raises(ValueError, match="Invalid GitLab URL format"):
        onboard_product.parse_gitlab_url("https://gitlab.com/onlyone")


# ---------------------------------------------------------------------------
# extract_repository_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        ("registry.redhat.io/rhelai3/bootc-cuda-rhel9", "rhelai3/bootc-cuda-rhel9"),
        ("quay.io/test-org/my-image", "test-org/my-image"),
        ("https://quay.io/test-org/my-image", "test-org/my-image"),
        ("registry.io/a/b/c", "a/b/c"),
    ],
)
def test_extract_repository_name_valid(url, expected):
    assert onboard_product.extract_repository_name(url) == expected


def test_extract_repository_name_no_path():
    with pytest.raises(ValueError, match="Invalid registry URL format"):
        onboard_product.extract_repository_name("registry.redhat.io")


# ---------------------------------------------------------------------------
# resolve_repo_path
# ---------------------------------------------------------------------------


def test_resolve_repo_path_local_repo_path_wins():
    component = {
        "name": "my-comp",
        "url": "https://gitlab.com/org/repo",
        "local_repo_path": "/my/custom/path",
    }
    result = onboard_product.resolve_repo_path(component, "/base", {"org/repo": "/override"})
    assert result == "/my/custom/path"


def test_resolve_repo_path_override_wins_over_derived():
    component = {"name": "my-comp", "url": "https://gitlab.com/redhat/my-repo"}
    result = onboard_product.resolve_repo_path(
        component, "/base", {"redhat/my-repo": "/overridden/path"}
    )
    assert result == "/overridden/path"


def test_resolve_repo_path_default_derived():
    component = {"name": "my-comp", "url": "https://gitlab.com/redhat/my-repo"}
    result = onboard_product.resolve_repo_path(component, "/base/path", {})
    assert result == "/base/path/redhat/my-repo"


def test_resolve_repo_path_no_overrides():
    component = {"name": "my-comp", "url": "https://gitlab.com/redhat/my-repo"}
    result = onboard_product.resolve_repo_path(component, "/base", None)
    assert result == "/base/redhat/my-repo"


# ---------------------------------------------------------------------------
# normalize_rpa_config
# ---------------------------------------------------------------------------


def test_normalize_rpa_config_new_format_merges_common():
    config = {
        "common": {"policy": "common-policy", "service_account": "sa"},
        "rpas": [
            {"name": "stage", "intention": "staging"},
            {"name": "prod", "policy": "prod-policy", "intention": "production"},
        ],
    }
    result = onboard_product.normalize_rpa_config(config)
    assert len(result) == 2
    # common fields merged
    assert result[0]["policy"] == "common-policy"
    assert result[0]["service_account"] == "sa"
    # RPA overrides common
    assert result[1]["policy"] == "prod-policy"
    assert result[1]["service_account"] == "sa"


def test_normalize_rpa_config_tags_append_both_sides():
    config = {
        "common": {"tags": ["v1", "v2"]},
        "rpas": [{"name": "stage", "tags": ["stage"]}],
    }
    result = onboard_product.normalize_rpa_config(config)
    assert result[0]["tags"] == ["v1", "v2", "stage"]


def test_normalize_rpa_config_tags_only_in_common():
    config = {
        "common": {"tags": ["v1"]},
        "rpas": [{"name": "stage"}],
    }
    result = onboard_product.normalize_rpa_config(config)
    assert result[0]["tags"] == ["v1"]


def test_normalize_rpa_config_tags_only_in_rpa():
    config = {
        "common": {},
        "rpas": [{"name": "stage", "tags": ["stage"]}],
    }
    result = onboard_product.normalize_rpa_config(config)
    assert result[0]["tags"] == ["stage"]


def test_normalize_rpa_config_empty_returns_empty():
    assert onboard_product.normalize_rpa_config(None) == []
    assert onboard_product.normalize_rpa_config([]) == []
    assert onboard_product.normalize_rpa_config({}) == []


def test_normalize_rpa_config_invalid_format_raises():
    with pytest.raises(ValueError):
        onboard_product.normalize_rpa_config("invalid")
    with pytest.raises(ValueError):
        onboard_product.normalize_rpa_config({"common": {}})


# ---------------------------------------------------------------------------
# normalize_component_config
# ---------------------------------------------------------------------------


def test_normalize_component_config_new_format_merges_common_fields():
    config = {
        "common": {"context": "./common-ctx", "dockerfile": "CommonFile"},
        "items": [
            {"name": "comp1", "url": "https://example.com"},
            {"name": "comp2", "url": "https://example.com/2", "dockerfile": "Override"},
        ],
    }
    result = onboard_product.normalize_component_config(config)
    assert len(result) == 2
    # common field inherited
    assert result[0]["context"] == "./common-ctx"
    assert result[0]["dockerfile"] == "CommonFile"
    # component overrides common
    assert result[1]["dockerfile"] == "Override"
    assert result[1]["context"] == "./common-ctx"


def test_normalize_component_config_pipelinerun_defaults_merge():
    config = {
        "common": {
            "pipelinerun": {"build_platforms": ["linux/x86_64"], "image_expires_after": "5d"}
        },
        "items": [
            {
                "name": "comp1",
                "url": "https://example.com",
                "pipelinerun": [
                    {
                        "pipeline": "full-container",
                        "build_args_file": "build.conf",
                        "image_expires_after": "10d",
                    }
                ],
            }
        ],
    }
    result = onboard_product.normalize_component_config(config)
    pr = result[0]["pipelinerun"][0]
    # common default inherited
    assert pr["build_platforms"] == ["linux/x86_64"]
    # component override wins
    assert pr["image_expires_after"] == "10d"
    assert pr["pipeline"] == "full-container"


def test_normalize_component_config_pipelinerun_from_common_only():
    config = {
        "common": {"pipelinerun": {"pipeline": "full-container", "build_args_file": "build.conf"}},
        "items": [{"name": "comp1", "url": "https://example.com"}],
    }
    result = onboard_product.normalize_component_config(config)
    assert len(result[0]["pipelinerun"]) == 1
    assert result[0]["pipelinerun"][0]["pipeline"] == "full-container"


def test_normalize_component_config_params_lists_combined():
    config = {
        "common": {
            "pipelinerun": {
                "pipeline": "full-container",
                "params": [
                    {"name": "snyk-project-name", "value": "my-project"},
                    {"name": "snyk-org", "value": "org-123"},
                    {"name": "additional-build-secret", "value": "global-pull-secret"},
                ],
            }
        },
        "items": [
            {
                "name": "comp-with-own-params",
                "url": "https://example.com",
                "pipelinerun": [
                    {
                        "build_args_file": "build.conf",
                        "params": [{"name": "privileged-nested", "value": "true"}],
                    }
                ],
            },
            {
                "name": "comp-override-common",
                "url": "https://example.com",
                "pipelinerun": [
                    {
                        "build_args_file": "build.conf",
                        "params": [
                            {"name": "snyk-org", "value": "override-org"},
                            {"name": "cloud-provider", "value": "aws"},
                        ],
                    }
                ],
            },
            {
                "name": "comp-no-own-params",
                "url": "https://example.com",
                "pipelinerun": [{"build_args_file": "build.conf"}],
            },
        ],
    }
    result = onboard_product.normalize_component_config(config)

    # Item with different params: all combined
    pr0 = result[0]["pipelinerun"][0]
    names0 = [p["name"] for p in pr0["params"]]
    assert "snyk-project-name" in names0
    assert "snyk-org" in names0
    assert "additional-build-secret" in names0
    assert "privileged-nested" in names0
    assert len(pr0["params"]) == 4

    # Item that overrides a common param: item wins, no duplicates
    pr1 = result[1]["pipelinerun"][0]
    names1 = [p["name"] for p in pr1["params"]]
    assert names1.count("snyk-org") == 1
    snyk_org = next(p for p in pr1["params"] if p["name"] == "snyk-org")
    assert snyk_org["value"] == "override-org"
    assert "snyk-project-name" in names1
    assert "cloud-provider" in names1
    assert len(pr1["params"]) == 4

    # Item with no own params: common params inherited as-is
    pr2 = result[2]["pipelinerun"][0]
    assert len(pr2["params"]) == 3
    assert pr2["params"] == config["common"]["pipelinerun"]["params"]


def test_normalize_component_config_rpa_values_merge():
    config = {
        "common": {
            "rpa_values": {
                "destination": "common-dest",
                "productName": "Common Product",
                "version": "1.0",
            }
        },
        "items": [
            {
                "name": "comp1",
                "url": "https://example.com",
                "rpa_values": {"version": "2.0", "filename": "file.iso"},
            }
        ],
    }
    result = onboard_product.normalize_component_config(config)
    rv = result[0]["rpa_values"]
    # common fields merged
    assert rv["destination"] == "common-dest"
    assert rv["productName"] == "Common Product"
    # component overrides
    assert rv["version"] == "2.0"
    assert rv["filename"] == "file.iso"


def test_normalize_component_config_invalid_format_raises():
    with pytest.raises(ValueError):
        onboard_product.normalize_component_config("invalid")
    with pytest.raises(ValueError):
        onboard_product.normalize_component_config({})
    with pytest.raises(ValueError):
        onboard_product.normalize_component_config({"common": {}})


# ---------------------------------------------------------------------------
# Config priority chain
# ---------------------------------------------------------------------------


def test_config_defaults():
    c = Config(config_file=Path("/nonexistent/path.toml"))
    assert str(c["krd_path"]).endswith("output/krd")
    assert c["cluster"] == "stone-prod-p02"


def test_config_env_overrides_defaults(monkeypatch):
    monkeypatch.setenv("KRD_PATH", "/env/krd/path")
    c = Config(config_file=Path("/nonexistent/path.toml"))
    assert str(c["krd_path"]) == "/env/krd/path"


def test_config_cli_overrides_env(monkeypatch):
    monkeypatch.setenv("KRD_PATH", "/env/path")
    c = Config(config_file=Path("/nonexistent/path.toml"), cli_overrides={"krd_path": "/cli/path"})
    assert str(c["krd_path"]) == "/cli/path"


def test_config_toml_overrides_defaults(tmp_path):
    toml_file = tmp_path / ".onboard-config.toml"
    toml_file.write_text('[paths]\nkrd_path = "/toml/path"\n')
    c = Config(config_file=toml_file)
    assert str(c["krd_path"]) == "/toml/path"


def test_config_env_overrides_toml(tmp_path, monkeypatch):
    toml_file = tmp_path / ".onboard-config.toml"
    toml_file.write_text('[paths]\nkrd_path = "/toml/path"\n')
    monkeypatch.setenv("KRD_PATH", "/env/path")
    c = Config(config_file=toml_file)
    assert str(c["krd_path"]) == "/env/path"


# ---------------------------------------------------------------------------
# to_yaml_filter
# ---------------------------------------------------------------------------


def test_to_yaml_filter_exact_indent():
    data = [{"cloud": "aws", "name": "test-aws"}]
    result = onboard_product.to_yaml_filter(data, indent=12)
    first_line = result.split("\n")[0]
    stripped = first_line.lstrip(" ")
    leading_spaces = len(first_line) - len(stripped)
    assert leading_spaces == 12


def test_to_yaml_filter_no_indent():
    data = {"key": "value"}
    result = onboard_product.to_yaml_filter(data, indent=0)
    assert result.startswith("key:")


def test_to_yaml_filter_strips_comments():
    from ruamel.yaml import YAML as RuamelYAML

    y = RuamelYAML()
    commented = y.load("key: value  # this is a comment\n")
    result = onboard_product.to_yaml_filter(commented, indent=0)
    assert "#" not in result
    assert "key: value" in result


# ---------------------------------------------------------------------------
# collect_config_files (include_parent)
# ---------------------------------------------------------------------------


def test_collect_config_files_include_parent(tmp_path):
    parent = tmp_path / "product"
    parent.mkdir()
    branch = parent / "3.3"
    branch.mkdir()
    (branch / "config.yaml").write_text("branch: '3.3'\n")
    (parent / "developer-portal.yaml").write_text("versions: []\n")
    result = onboard_product.collect_config_files(None, branch, include_parent=True)
    names = [f.name for f in result]
    assert "config.yaml" in names
    assert "developer-portal.yaml" in names


def test_collect_config_files_no_parent_by_default(tmp_path):
    parent = tmp_path / "product"
    parent.mkdir()
    branch = parent / "3.3"
    branch.mkdir()
    (branch / "config.yaml").write_text("branch: '3.3'\n")
    (parent / "developer-portal.yaml").write_text("versions: []\n")
    result = onboard_product.collect_config_files(None, branch)
    names = [f.name for f in result]
    assert "config.yaml" in names
    assert "developer-portal.yaml" not in names
