"""Tests for sidetrack gitops helpers (no network)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sidetrack import gitops


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "app"
    root.mkdir()
    _run(["git", "init", "-b", "main"], root)
    _run(["git", "config", "user.email", "test@example.com"], root)
    _run(["git", "config", "user.name", "Test User"], root)
    (root / "README.md").write_text("hello\n")
    _run(["git", "add", "README.md"], root)
    _run(["git", "commit", "-m", "init"], root)
    return root


def test_list_main_worktree(repo: Path) -> None:
    trees = gitops.list_worktrees(repo)
    assert len(trees) == 1
    assert trees[0].is_main
    assert trees[0].branch == "main"


def test_add_and_find_worktree(repo: Path) -> None:
    tree = gitops.add_worktree(repo, "feature/demo")
    assert tree.branch == "feature/demo"
    assert tree.path.exists()
    found = gitops.find_worktree(repo, "feature/demo")
    assert found.path == tree.path
    # unique prefix
    found2 = gitops.find_worktree(repo, "feature/d")
    assert found2.path == tree.path


def test_status_summary_clean(repo: Path) -> None:
    tree = gitops.list_worktrees(repo)[0]
    summary = gitops.status_summary(repo, tree)
    assert summary["dirty"] is False
    assert summary["branch"] == "main"


def test_remove_worktree(repo: Path) -> None:
    tree = gitops.add_worktree(repo, "tmp-branch")
    removed, deleted = gitops.remove_worktree(repo, "tmp-branch", delete_branch=True)
    assert removed.path == tree.path
    assert deleted == "tmp-branch"
    assert not tree.path.exists()
    remaining = gitops.list_worktrees(repo)
    assert len(remaining) == 1


def test_slugify() -> None:
    assert gitops.slugify("feature/login flow") == "feature/login-flow"


def test_default_root(repo: Path) -> None:
    root = gitops.default_worktree_root(repo)
    assert root.name.endswith("-worktrees")
