#!/usr/bin/env python3
"""
Tests for repository health checks in onboard-product.py.

Covers expected-branch enforcement, dirty-tree detection, KRD wiring, and
non-interactive warning behavior.
"""

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from onboard-product.py (need to use importlib for dash in filename)
spec = importlib.util.spec_from_file_location(
    "onboard_product",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "onboard-product.py"),
)
onboard_product = importlib.util.module_from_spec(spec)
spec.loader.exec_module(onboard_product)


def make_repo(tmp_path, branch="main", dirty=False):
    """Create a temp git repo with one commit, optionally with an untracked file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", branch], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "README.md").write_text("seed\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, capture_output=True)
    if dirty:
        (repo / "untracked.txt").write_text("x\n")
    return repo


def test_branch_mismatch_is_error_when_requested(tmp_path):
    repo = make_repo(tmp_path, branch="feature/x")
    errors, warnings = onboard_product.check_repo_health(
        str(repo),
        "KRD repository",
        expected_branch="main",
        branch_mismatch_is_error=True,
    )
    assert any("feature/x" in e and "main" in e for e in errors)
    assert warnings == []


def test_branch_mismatch_is_warning_by_default(tmp_path):
    repo = make_repo(tmp_path, branch="feature/x")
    errors, warnings = onboard_product.check_repo_health(
        str(repo),
        "component",
        expected_branch="main",
    )
    assert errors == []
    assert any("feature/x" in w and "main" in w for w in warnings)


def test_detached_head_counts_as_mismatch(tmp_path):
    repo = make_repo(tmp_path)
    subprocess.run(["git", "checkout", "--detach"], cwd=repo, check=True, capture_output=True)
    errors, warnings = onboard_product.check_repo_health(
        str(repo),
        "KRD repository",
        expected_branch="main",
        branch_mismatch_is_error=True,
    )
    assert any("detached" in e and "main" in e for e in errors)
    assert warnings == []


def test_branch_match_no_findings(tmp_path):
    repo = make_repo(tmp_path)
    errors, warnings = onboard_product.check_repo_health(
        str(repo),
        "KRD repository",
        expected_branch="main",
        branch_mismatch_is_error=True,
        check_dirty=True,
    )
    assert errors == []
    assert warnings == []


def test_dirty_tree_warns_with_check_dirty(tmp_path):
    repo = make_repo(tmp_path)
    with open(repo / "README.md", "a") as f:
        f.write("modified\n")
    errors, warnings = onboard_product.check_repo_health(
        str(repo),
        "KRD repository",
        check_dirty=True,
    )
    assert errors == []
    assert any("dirty" in w and "uncommitted" in w for w in warnings)


def test_untracked_files_count_as_dirty(tmp_path):
    repo = make_repo(tmp_path, dirty=True)
    errors, warnings = onboard_product.check_repo_health(
        str(repo),
        "KRD repository",
        check_dirty=True,
    )
    assert errors == []
    assert any("dirty" in w for w in warnings)


def test_untracked_files_flagged_despite_git_config(tmp_path):
    repo = make_repo(tmp_path, dirty=True)
    subprocess.run(
        ["git", "config", "status.showUntrackedFiles", "no"],
        cwd=repo,
        check=True,
    )
    errors, warnings = onboard_product.check_repo_health(
        str(repo),
        "KRD repository",
        check_dirty=True,
    )
    assert errors == []
    assert any("dirty" in w for w in warnings)


def test_git_status_failure_is_error(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".git" / "index").write_text("corrupt")
    errors, warnings = onboard_product.check_repo_health(
        str(repo),
        "KRD repository",
        check_dirty=True,
    )
    assert any("git status failed" in e for e in errors)
    assert warnings == []


def test_dirty_tree_ignored_without_check_dirty(tmp_path):
    repo = make_repo(tmp_path, dirty=True)
    errors, warnings = onboard_product.check_repo_health(str(repo), "KRD repository")
    assert errors == []
    assert warnings == []


def test_no_expected_branch_no_branch_finding(tmp_path):
    repo = make_repo(tmp_path, branch="feature/x")
    errors, warnings = onboard_product.check_repo_health(
        str(repo),
        "KRD repository",
        expected_branch=None,
        branch_mismatch_is_error=True,
    )
    assert errors == []
    assert warnings == []


def test_collect_krd_uses_declared_branch(tmp_path):
    repo = make_repo(tmp_path, branch="feature/x")
    config = {
        "krd_path": str(repo),
        "krd_branch": "main",
        "definitions": [],
    }
    errors, warnings = onboard_product.collect_repo_warnings({"definitions": []}, config, "krd")
    assert any("feature/x" in e and "main" in e for e in errors)
    assert warnings == []


def test_collect_krd_no_branch_check_when_unset(tmp_path):
    repo = make_repo(tmp_path, branch="feature/x")
    config = {
        "krd_path": str(repo),
        "definitions": [],
    }
    errors, warnings = onboard_product.collect_repo_warnings({"definitions": []}, config, "krd")
    assert errors == []
    assert warnings == []


def test_collect_pipelinerun_skips_krd_checks(tmp_path):
    repo = make_repo(tmp_path, branch="feature/x")
    config = {
        "krd_path": str(repo),
        "krd_branch": "main",
        "gitlab_repo_path": str(tmp_path / "pipelinerun"),
        "definitions": [],
    }
    errors, warnings = onboard_product.collect_repo_warnings(
        {"definitions": []}, config, "pipelinerun"
    )
    assert errors == []
    assert warnings == []


def test_collect_krd_flags_dirty_tree(tmp_path):
    repo = make_repo(tmp_path, dirty=True)
    config = {
        "krd_path": str(repo),
        "definitions": [],
    }
    errors, warnings = onboard_product.collect_repo_warnings({"definitions": []}, config, "krd")
    assert errors == []
    assert any("dirty" in w for w in warnings)


class FakeStdin:
    def __init__(self, tty):
        self._tty = tty

    def isatty(self):
        return self._tty


def test_noninteractive_aborts_on_warnings(monkeypatch):
    def fail_input(*args, **kwargs):
        raise AssertionError("input() must not be called in non-interactive mode")

    monkeypatch.setattr(sys, "stdin", FakeStdin(tty=False))
    monkeypatch.setattr("builtins.input", fail_input)
    assert onboard_product.prompt_continue_with_warnings(["w"]) is False


def test_interactive_prompt_unchanged(monkeypatch):
    monkeypatch.setattr(sys, "stdin", FakeStdin(tty=True))
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "n")
    assert onboard_product.prompt_continue_with_warnings(["w"]) is False
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "y")
    assert onboard_product.prompt_continue_with_warnings(["w"]) is True


TEST_CONFIG = Path(__file__).parent / "configs" / "test-full-container.yaml"


def test_non_empty_str_rejects_empty():
    with pytest.raises(argparse.ArgumentTypeError):
        onboard_product.non_empty_str("")
    with pytest.raises(argparse.ArgumentTypeError):
        onboard_product.non_empty_str("   ")
    assert onboard_product.non_empty_str("main") == "main"


def test_main_rejects_empty_krd_branch(monkeypatch, tmp_path):
    repo = make_repo(tmp_path, branch="feature/x")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "onboard-product.py",
            "--config",
            str(TEST_CONFIG),
            "--mode",
            "krd",
            "--krd-path",
            str(repo),
            "--krd-branch",
            "",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        onboard_product.main()
    assert exc.value.code == 2


def test_main_noninteractive_warnings_exit_1(monkeypatch, tmp_path):
    repo = make_repo(tmp_path, dirty=True)
    monkeypatch.setattr(sys, "stdin", FakeStdin(tty=False))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "onboard-product.py",
            "--config",
            str(TEST_CONFIG),
            "--mode",
            "krd",
            "--krd-path",
            str(repo),
            "--krd-branch",
            "main",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        onboard_product.main()
    assert exc.value.code == 1


def test_main_interactive_decline_exit_0(monkeypatch, tmp_path):
    repo = make_repo(tmp_path, dirty=True)
    monkeypatch.setattr(sys, "stdin", FakeStdin(tty=True))
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "onboard-product.py",
            "--config",
            str(TEST_CONFIG),
            "--mode",
            "krd",
            "--krd-path",
            str(repo),
            "--krd-branch",
            "main",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        onboard_product.main()
    assert exc.value.code == 0
