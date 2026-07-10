"""sidetrack CLI — everyday git worktree manager."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from . import gitops

app = typer.Typer(
    name="sidetrack",
    help=(
        "Sensible git worktree manager for everyday multi-branch work. "
        "Create, switch, list, and clean up worktrees without memorizing "
        "git worktree plumbing."
    ),
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode="rich",
)
console = Console(stderr=False)
err_console = Console(stderr=True)


def _die(message: str, code: int = 1) -> None:
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(code)


def _repo() -> Path:
    try:
        return gitops.ensure_git_repo()
    except gitops.GitError as exc:
        _die(str(exc))
        raise


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"sidetrack {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Sensible git worktree manager."""


@app.command("list")
def list_cmd(
    paths: bool = typer.Option(False, "--paths", "-p", help="Print only paths."),
    porcelain: bool = typer.Option(False, "--porcelain", help="Machine-readable output."),
) -> None:
    """List worktrees for the current repository."""
    repo = _repo()
    try:
        trees = gitops.list_worktrees(repo)
    except gitops.GitError as exc:
        _die(str(exc))

    if not trees:
        console.print("No worktrees found.")
        return

    if porcelain:
        for tree in trees:
            branch = tree.branch or ("detached" if tree.is_detached else "?")
            flags = []
            if tree.is_main:
                flags.append("main")
            if tree.is_locked:
                flags.append("locked")
            if tree.is_prunable:
                flags.append("prunable")
            flag_s = ",".join(flags)
            console.print(f"{tree.path}\t{branch}\t{tree.head or ''}\t{flag_s}")
        return

    if paths:
        for tree in trees:
            console.print(str(tree.path))
        return

    table = Table(title="Worktrees", show_lines=False)
    table.add_column("Branch", style="cyan", no_wrap=True)
    table.add_column("Path")
    table.add_column("HEAD", style="dim", no_wrap=True)
    table.add_column("Flags", style="yellow")

    cwd = Path.cwd().resolve()
    for tree in trees:
        branch = tree.branch or ("(detached)" if tree.is_detached else "?")
        head = (tree.head or "")[:8]
        flags = []
        if tree.is_main:
            flags.append("main")
        try:
            if tree.path == cwd or cwd.is_relative_to(tree.path):
                flags.append("current")
        except AttributeError:
            if tree.path == cwd or str(cwd).startswith(str(tree.path) + os.sep):
                flags.append("current")
        if tree.is_locked:
            flags.append("locked")
        if tree.is_prunable:
            flags.append("prunable")
        table.add_row(branch, str(tree.path), head, " ".join(flags))

    console.print(table)


@app.command("add")
def add_cmd(
    branch: str = typer.Argument(..., help="Branch name to create or attach."),
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        "-p",
        help="Custom worktree path (default: <repo>-worktrees/<branch>).",
    ),
    base: Optional[str] = typer.Option(
        None,
        "--base",
        "-b",
        help="Base branch/commit for new branches (default: main/master).",
    ),
    existing: bool = typer.Option(
        False,
        "--existing",
        "-e",
        help="Require branch to already exist (do not create).",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Force add if needed."),
    shell: bool = typer.Option(
        False,
        "--shell",
        "-s",
        help="Open an interactive shell in the new worktree after creation.",
    ),
    print_path: bool = typer.Option(
        False,
        "--print-path",
        help="Print the worktree path only (useful for scripting / cd).",
    ),
) -> None:
    """Create a worktree for a branch (create branch if needed)."""
    repo = _repo()
    try:
        tree = gitops.add_worktree(
            repo,
            branch,
            path=path,
            base=base,
            create_branch=not existing,
            force=force,
        )
    except gitops.GitError as exc:
        _die(str(exc))

    if print_path:
        console.print(str(tree.path))
    else:
        console.print(
            f"[green]✓[/green] worktree ready  branch=[cyan]{tree.branch}[/cyan]  path={tree.path}"
        )

    if shell:
        _enter_shell(tree.path)


@app.command("rm")
def rm_cmd(
    target: str = typer.Argument(..., help="Branch name, path, or unique prefix."),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force removal of dirty worktrees / unmerged branches.",
    ),
    delete_branch: bool = typer.Option(
        False,
        "--delete-branch",
        "-d",
        help="Also delete the local branch if unused.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not prompt."),
) -> None:
    """Remove a worktree (optionally delete its branch)."""
    repo = _repo()
    try:
        tree = gitops.find_worktree(repo, target)
    except gitops.GitError as exc:
        _die(str(exc))

    if tree.is_main:
        _die("refusing to remove the main worktree")

    if not yes:
        label = tree.branch or str(tree.path)
        confirm = typer.confirm(f"Remove worktree '{label}' at {tree.path}?")
        if not confirm:
            raise typer.Abort()

    try:
        removed, deleted_branch = gitops.remove_worktree(
            repo,
            str(tree.path),
            force=force,
            delete_branch=delete_branch,
        )
    except gitops.GitError as exc:
        _die(str(exc))

    console.print(f"[green]✓[/green] removed {removed.path}")
    if deleted_branch:
        console.print(f"[green]✓[/green] deleted branch [cyan]{deleted_branch}[/cyan]")


@app.command("go")
def go_cmd(
    target: str = typer.Argument(..., help="Branch name, path, or unique prefix."),
    print_path: bool = typer.Option(
        False,
        "--print-path",
        "-p",
        help='Print path only (for: cd "$(sidetrack go feat -p)").',
    ),
    shell: bool = typer.Option(
        True,
        "--shell/--no-shell",
        help="Open a shell in the worktree (default: true unless --print-path).",
    ),
) -> None:
    """Jump into a worktree by branch name or path."""
    repo = _repo()
    try:
        tree = gitops.find_worktree(repo, target)
    except gitops.GitError as exc:
        _die(str(exc))

    if print_path:
        console.print(str(tree.path))
        return

    if shell:
        console.print(
            f"[dim]entering[/dim] [cyan]{tree.branch or tree.path.name}[/cyan]  {tree.path}"
        )
        _enter_shell(tree.path)
    else:
        console.print(str(tree.path))


@app.command("path")
def path_cmd(
    target: str = typer.Argument(..., help="Branch name, path, or unique prefix."),
) -> None:
    """Print the absolute path of a worktree."""
    repo = _repo()
    try:
        tree = gitops.find_worktree(repo, target)
    except gitops.GitError as exc:
        _die(str(exc))
    console.print(str(tree.path))


@app.command("status")
def status_cmd(
    short: bool = typer.Option(False, "--short", "-s", help="Compact one-line view."),
) -> None:
    """Show dirty/clean status for every worktree."""
    repo = _repo()
    try:
        trees = gitops.list_worktrees(repo)
    except gitops.GitError as exc:
        _die(str(exc))

    rows = []
    for tree in trees:
        if tree.is_bare:
            continue
        try:
            summary = gitops.status_summary(repo, tree)
        except gitops.GitError:
            summary = {
                "branch": tree.branch or "?",
                "path": str(tree.path),
                "dirty": False,
                "ahead": 0,
                "behind": 0,
                "staged": 0,
                "unstaged": 0,
                "untracked": 0,
                "is_main": tree.is_main,
                "detached": tree.is_detached,
                "locked": tree.is_locked,
                "upstream": "",
            }
        rows.append(summary)

    if short:
        for row in rows:
            mark = "*" if row["dirty"] else " "
            ab = ""
            if row["ahead"] or row["behind"]:
                ab = f" +{row['ahead']}/-{row['behind']}"
            flags = " main" if row["is_main"] else ""
            console.print(
                f"{mark} {row['branch']:<24} staged={row['staged']} "
                f"unstaged={row['unstaged']} untracked={row['untracked']}{ab}{flags}"
            )
        return

    table = Table(title="Worktree status")
    table.add_column("Branch", style="cyan")
    table.add_column("Dirty")
    table.add_column("Staged", justify="right")
    table.add_column("Unstaged", justify="right")
    table.add_column("Untracked", justify="right")
    table.add_column("Ahead", justify="right")
    table.add_column("Behind", justify="right")
    table.add_column("Path", style="dim")

    for row in rows:
        dirty = "[red]yes[/red]" if row["dirty"] else "[green]no[/green]"
        table.add_row(
            str(row["branch"]),
            dirty,
            str(row["staged"]),
            str(row["unstaged"]),
            str(row["untracked"]),
            str(row["ahead"]),
            str(row["behind"]),
            str(row["path"]),
        )
    console.print(table)


@app.command("prune")
def prune_cmd() -> None:
    """Prune stale worktree administrative files."""
    repo = _repo()
    try:
        out = gitops.prune_worktrees(repo)
    except gitops.GitError as exc:
        _die(str(exc))
    if out:
        console.print(out)
    console.print("[green]✓[/green] pruned")


@app.command("root")
def root_cmd(
    set_path: Optional[Path] = typer.Option(
        None,
        "--set",
        help="Set repo-local worktree root (git config sidetrack.worktreeRoot).",
    ),
) -> None:
    """Show or set the default directory for new worktrees."""
    repo = _repo()
    if set_path is not None:
        value = str(set_path.expanduser())
        try:
            gitops.run_git(["config", "sidetrack.worktreeRoot", value], cwd=repo)
        except gitops.GitError as exc:
            _die(str(exc))
        console.print(f"[green]✓[/green] sidetrack.worktreeRoot = {value}")
        return
    try:
        root = gitops.default_worktree_root(repo)
    except gitops.GitError as exc:
        _die(str(exc))
    console.print(str(root))


@app.command("open")
def open_cmd(
    target: str = typer.Argument(..., help="Branch name, path, or unique prefix."),
    editor: Optional[str] = typer.Option(
        None,
        "--editor",
        "-e",
        help="Editor command (default: $VISUAL / $EDITOR / cursor / code / nvim).",
    ),
) -> None:
    """Open a worktree in your editor."""
    repo = _repo()
    try:
        tree = gitops.find_worktree(repo, target)
        cmd = gitops.open_in_editor(tree.path, editor=editor)
    except gitops.GitError as exc:
        _die(str(exc))

    console.print(f"[dim]running[/dim] {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=False)
    except OSError as exc:
        _die(str(exc))


@app.command("cleanup")
def cleanup_cmd(
    merged: bool = typer.Option(
        True,
        "--merged/--all-gone",
        help="Only consider branches merged into the base branch.",
    ),
    base: Optional[str] = typer.Option(
        None, "--base", "-b", help="Base branch for merge checks."
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Force remove dirty trees."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not prompt per worktree."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be removed."),
) -> None:
    """Remove non-main worktrees whose branches are merged (or all non-main)."""
    repo = _repo()
    try:
        trees = gitops.list_worktrees(repo)
        base_branch = base or gitops.default_base_branch(repo)
    except gitops.GitError as exc:
        _die(str(exc))

    candidates = [t for t in trees if not t.is_main and not t.is_bare and t.branch]
    to_remove: list[gitops.Worktree] = []

    for tree in candidates:
        assert tree.branch is not None
        if merged:
            result = gitops.run_git(
                ["merge-base", "--is-ancestor", tree.branch, base_branch],
                cwd=repo,
                check=False,
            )
            if result.returncode == 0:
                to_remove.append(tree)
        else:
            to_remove.append(tree)

    if not to_remove:
        console.print("Nothing to clean up.")
        return

    for tree in to_remove:
        console.print(f" - {tree.branch} @ {tree.path}")

    if dry_run:
        console.print(f"[dim]dry-run: {len(to_remove)} worktree(s)[/dim]")
        return

    if not yes and not typer.confirm(f"Remove {len(to_remove)} worktree(s)?"):
        raise typer.Abort()

    for tree in to_remove:
        try:
            gitops.remove_worktree(
                repo,
                str(tree.path),
                force=force,
                delete_branch=False,
            )
            console.print(f"[green]✓[/green] removed {tree.branch}")
        except gitops.GitError as exc:
            err_console.print(f"[red]error:[/red] {tree.branch}: {exc}")


def _enter_shell(path: Path) -> None:
    cmd = gitops.shell_command_for(path)
    env = os.environ.copy()
    env["SIDETRACK_WORKTREE"] = str(path)
    env["SIDETRACK"] = "1"
    try:
        completed = subprocess.run(cmd, cwd=str(path), env=env, check=False)
    except OSError as exc:
        _die(str(exc))
    raise typer.Exit(completed.returncode)


if __name__ == "__main__":
    app()
