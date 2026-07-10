"""Git worktree helpers used by the sidetrack CLI."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class GitError(RuntimeError):
    """Raised when a git command fails in a way the CLI should surface."""


@dataclass(frozen=True)
class Worktree:
    path: Path
    branch: str | None
    head: str | None
    is_bare: bool = False
    is_detached: bool = False
    is_locked: bool = False
    lock_reason: str | None = None
    is_prunable: bool = False
    is_main: bool = False


def run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    cmd = ["git", *args]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=capture,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc

    if check and result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or f"git {' '.join(args)} failed"
        raise GitError(detail)
    return result


def ensure_git_repo(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    result = run_git(["rev-parse", "--show-toplevel"], cwd=start, check=False)
    if result.returncode != 0:
        raise GitError("not inside a git repository")
    return Path(result.stdout.strip()).resolve()


def common_git_dir(repo: Path) -> Path:
    result = run_git(["rev-parse", "--git-common-dir"], cwd=repo)
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = (repo / path).resolve()
    return path.resolve()


def main_worktree_path(repo: Path) -> Path:
    """Return the primary worktree path for this repository."""
    git_common = common_git_dir(repo)
    if git_common.name == ".git":
        return git_common.parent.resolve()
    trees = list_worktrees(repo)
    if not trees:
        return repo.resolve()
    return trees[0].path


def current_branch(repo: Path) -> str | None:
    result = run_git(["branch", "--show-current"], cwd=repo, check=False)
    branch = (result.stdout or "").strip()
    return branch or None


def current_head(repo: Path) -> str:
    result = run_git(["rev-parse", "HEAD"], cwd=repo)
    return result.stdout.strip()


def branch_exists(repo: Path, branch: str) -> bool:
    result = run_git(
        ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=repo,
        check=False,
    )
    return result.returncode == 0


def remote_branch_exists(repo: Path, branch: str, remote: str = "origin") -> bool:
    result = run_git(
        ["show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}"],
        cwd=repo,
        check=False,
    )
    return result.returncode == 0


def default_base_branch(repo: Path) -> str:
    for candidate in ("main", "master", "trunk", "develop"):
        if branch_exists(repo, candidate):
            return candidate
    result = run_git(
        ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
        cwd=repo,
        check=False,
    )
    if result.returncode == 0:
        ref = result.stdout.strip()
        prefix = "refs/remotes/origin/"
        if ref.startswith(prefix):
            return ref[len(prefix):]
    current = current_branch(repo)
    if current:
        return current
    return "main"


def parse_worktree_porcelain(output: str, main_path: Path) -> list[Worktree]:
    entries: list[Worktree] = []
    blocks = [b for b in output.split("\n\n") if b.strip()]
    for block in blocks:
        path: Path | None = None
        branch: str | None = None
        head: str | None = None
        is_bare = False
        is_detached = False
        is_locked = False
        lock_reason: str | None = None
        is_prunable = False

        for line in block.splitlines():
            if line.startswith("worktree "):
                path = Path(line[len("worktree "):]).resolve()
            elif line.startswith("HEAD "):
                head = line[len("HEAD "):].strip()
            elif line.startswith("branch "):
                ref = line[len("branch "):].strip()
                if ref.startswith("refs/heads/"):
                    branch = ref[len("refs/heads/"):]
                else:
                    branch = ref
            elif line == "bare":
                is_bare = True
            elif line == "detached":
                is_detached = True
            elif line.startswith("locked"):
                is_locked = True
                if line.startswith("locked "):
                    lock_reason = line[len("locked "):]
            elif line.startswith("prunable"):
                is_prunable = True

        if path is None:
            continue
        entries.append(
            Worktree(
                path=path,
                branch=branch,
                head=head,
                is_bare=is_bare,
                is_detached=is_detached,
                is_locked=is_locked,
                lock_reason=lock_reason,
                is_prunable=is_prunable,
                is_main=(path.resolve() == main_path.resolve()),
            )
        )
    return entries


def list_worktrees(repo: Path) -> list[Worktree]:
    main_path = main_worktree_path(repo)
    result = run_git(["worktree", "list", "--porcelain"], cwd=repo)
    return parse_worktree_porcelain(result.stdout, main_path)


def find_worktree(
    repo: Path,
    query: str,
    *,
    trees: list[Worktree] | None = None,
) -> Worktree:
    trees = trees if trees is not None else list_worktrees(repo)
    query = query.strip()
    if not query:
        raise GitError("empty worktree query")

    qpath = Path(query).expanduser()
    try:
        qpath_resolved = qpath.resolve()
    except OSError:
        qpath_resolved = qpath

    for tree in trees:
        if tree.path == qpath_resolved or str(tree.path) == query:
            return tree

    matches = [t for t in trees if t.branch == query]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        paths = ", ".join(str(t.path) for t in matches)
        raise GitError(f"branch '{query}' is checked out in multiple worktrees: {paths}")

    basenames = [t for t in trees if t.path.name == query]
    if len(basenames) == 1:
        return basenames[0]

    prefix_matches = [
        t
        for t in trees
        if (t.branch and t.branch.startswith(query)) or t.path.name.startswith(query)
    ]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if len(prefix_matches) > 1:
        names = ", ".join(t.branch or t.path.name for t in prefix_matches)
        raise GitError(f"ambiguous worktree '{query}': {names}")

    raise GitError(f"no worktree matching '{query}'")


def slugify(value: str) -> str:
    value = value.strip().replace(" ", "-")
    value = re.sub(r"[^A-Za-z0-9._/-]+", "-", value)
    value = re.sub(r"/+", "/", value)
    value = value.strip("/.-")
    return value or "work"


def default_worktree_root(repo: Path) -> Path:
    """Sibling directory next to the main worktree: <repo>-worktrees/"""
    main = main_worktree_path(repo)
    configured = run_git(
        ["config", "--get", "sidetrack.worktreeRoot"],
        cwd=repo,
        check=False,
    )
    if configured.returncode == 0 and configured.stdout.strip():
        root = Path(configured.stdout.strip()).expanduser()
        if not root.is_absolute():
            root = (main / root).resolve()
        return root
    return Path(f"{main}-worktrees").resolve()


def worktree_path_for(repo: Path, branch: str, path: Path | None = None) -> Path:
    if path is not None:
        return path.expanduser().resolve()
    root = default_worktree_root(repo)
    safe = slugify(branch).replace("/", "-")
    return (root / safe).resolve()


def add_worktree(
    repo: Path,
    branch: str,
    *,
    path: Path | None = None,
    base: str | None = None,
    create_branch: bool = True,
    force: bool = False,
) -> Worktree:
    branch = branch.strip()
    if not branch:
        raise GitError("branch name is required")

    target = worktree_path_for(repo, branch, path)
    if target.exists() and any(target.iterdir()) and not force:
        raise GitError(f"path already exists and is not empty: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)

    args = ["worktree", "add"]
    if force:
        args.append("--force")

    if branch_exists(repo, branch):
        existing = [t for t in list_worktrees(repo) if t.branch == branch]
        if existing and not force:
            raise GitError(
                f"branch '{branch}' is already checked out at {existing[0].path}"
            )
        args.extend([str(target), branch])
    elif remote_branch_exists(repo, branch):
        args.extend(["--track", "-b", branch, str(target), f"origin/{branch}"])
    elif create_branch:
        start = base or default_base_branch(repo)
        args.extend(["-b", branch, str(target), start])
    else:
        raise GitError(f"branch '{branch}' does not exist")

    run_git(args, cwd=repo)
    return find_worktree(repo, str(target))


def remove_worktree(
    repo: Path,
    query: str,
    *,
    force: bool = False,
    delete_branch: bool = False,
) -> tuple[Worktree, str | None]:
    tree = find_worktree(repo, query)
    if tree.is_main:
        raise GitError("refusing to remove the main worktree")

    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(tree.path))
    run_git(args, cwd=repo)

    deleted_branch = None
    if delete_branch and tree.branch:
        remaining = list_worktrees(repo)
        if not any(t.branch == tree.branch for t in remaining):
            result = run_git(["branch", "-d", tree.branch], cwd=repo, check=False)
            if result.returncode != 0:
                if force:
                    run_git(["branch", "-D", tree.branch], cwd=repo)
                    deleted_branch = tree.branch
                else:
                    raise GitError(
                        (result.stderr or result.stdout or "failed to delete branch").strip()
                    )
            else:
                deleted_branch = tree.branch
    return tree, deleted_branch


def prune_worktrees(repo: Path) -> str:
    result = run_git(["worktree", "prune", "-v"], cwd=repo, check=False)
    return (result.stdout or result.stderr or "").strip()


def shell_command_for(path: Path, shell: str | None = None) -> list[str]:
    shell = shell or os.environ.get("SHELL") or shutil.which("bash") or "bash"
    return [shell, "-i"]


def open_in_editor(path: Path, editor: str | None = None) -> list[str]:
    editor = editor or os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        for candidate in ("cursor", "code", "nvim", "vim", "nano"):
            found = shutil.which(candidate)
            if found:
                editor = found
                break
    if not editor:
        raise GitError("no editor found; set $EDITOR or pass --editor")
    parts = editor.split()
    return [*parts, str(path)]


def status_summary(repo: Path, tree: Worktree) -> dict[str, str | int | bool]:
    """Collect a compact status summary for one worktree."""
    result = run_git(["status", "--porcelain=2", "--branch"], cwd=tree.path, check=False)
    lines = (result.stdout or "").splitlines()
    branch = tree.branch or "?"
    upstream = ""
    ahead = 0
    behind = 0
    staged = 0
    unstaged = 0
    untracked = 0

    for line in lines:
        if line.startswith("# branch.head "):
            branch = line.split(" ", 2)[2]
        elif line.startswith("# branch.upstream "):
            upstream = line.split(" ", 2)[2]
        elif line.startswith("# branch.ab "):
            m = re.search(r"\+(\d+)\s+-(\d+)", line)
            if m:
                ahead = int(m.group(1))
                behind = int(m.group(2))
        elif line.startswith("?"):
            untracked += 1
        elif line.startswith("1 ") or line.startswith("2 "):
            try:
                xy = line.split(" ", 2)[1]
            except IndexError:
                continue
            if xy[0] != ".":
                staged += 1
            if len(xy) > 1 and xy[1] != ".":
                unstaged += 1
        elif line.startswith("u "):
            unstaged += 1

    dirty = staged + unstaged + untracked > 0
    return {
        "branch": branch,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "dirty": dirty,
        "path": str(tree.path),
        "is_main": tree.is_main,
        "detached": tree.is_detached,
        "locked": tree.is_locked,
    }


def iter_unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
