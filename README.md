# sidetrack

**Sensible git worktree manager for everyday multi-branch work.**

Git worktrees are perfect for reviewing a PR while mid-feature, shipping a hotfix without stashing, or running parallel agent/dev checkouts — but the raw UX is awkward:

```bash
git worktree add ../repo-fix-123 -b fix/123 main
cd ../repo-fix-123
# later...
git worktree remove ../repo-fix-123
git worktree prune
```

`sidetrack` turns that into muscle memory:

```bash
sidetrack add fix/login
sidetrack go fix/login
sidetrack list
sidetrack status
sidetrack rm fix/login -d -y
```

## Why this exists

Developers still stash/checkout-switch for context changes even though worktrees have existed since 2015. Common complaints:

- raw `git worktree` is easy to forget and path-clunky
- no opinionated default layout
- hard to see dirty state across all checkouts at a glance
- cleanup of merged sidecars is manual

`sidetrack` is a thin, local-first CLI focused on the weekly workflow — not a full git GUI.

## Install

```bash
pip install git+https://github.com/gowtham980/sidetrack.git
# or from a checkout:
pip install -e .
```

Requires Python 3.10+ and `git` on PATH.

Commands are available as both `sidetrack` and the short alias `st`.

## Quick start

Inside any git repo:

```bash
# Create a new branch + worktree under <repo>-worktrees/<branch>
sidetrack add feature/payments

# Jump into it (opens a shell)
sidetrack go feature/payments

# Or print the path for cd / scripts
cd "$(sidetrack path feature/payments)"

# See every checkout
sidetrack list
sidetrack status

# Remove when done (optionally delete the local branch)
sidetrack rm feature/payments --delete-branch --yes

# Clean merged sidecars
sidetrack cleanup --dry-run
sidetrack cleanup --yes
```

## Commands

| Command | Purpose |
|---------|---------|
| `sidetrack list` | Table of worktrees (branch, path, flags) |
| `sidetrack add <branch>` | Create/attach worktree; creates branch from main/master if needed |
| `sidetrack go <target>` | Enter worktree by branch, path, or unique prefix |
| `sidetrack path <target>` | Print absolute path |
| `sidetrack status` | Dirty/clean summary across all worktrees |
| `sidetrack rm <target>` | Remove a non-main worktree |
| `sidetrack cleanup` | Remove worktrees whose branches are merged into base |
| `sidetrack prune` | `git worktree prune` with friendly output |
| `sidetrack root` | Show/set default worktree parent directory |
| `sidetrack open <target>` | Open worktree in `$EDITOR` / cursor / code / nvim |

### Useful flags

```bash
sidetrack add hotfix/timeout --base main --shell
sidetrack add existing-branch --existing
sidetrack add demo --path /tmp/demo-tree
sidetrack rm demo --force --delete-branch --yes
sidetrack go feat --print-path
sidetrack status --short
sidetrack root --set ~/worktrees/myrepo
```

## Default layout

New worktrees land next to the main checkout:

```text
~/code/myapp/                 # main worktree
~/code/myapp-worktrees/
  feature-payments/
  fix-login/
```

Override per-repo:

```bash
sidetrack root --set .worktrees
# stores git config sidetrack.worktreeRoot
```

## Shell helper (optional)

Add to `~/.zshrc` / `~/.bashrc` if you want `cd` instead of a nested shell:

```bash
stw() { cd "$(sidetrack path "$1")" || return; }
```

## How it maps to git

| sidetrack | git equivalent |
|-----------|----------------|
| `add br` | `git worktree add -b br <path> <base>` (or attach existing) |
| `list` | `git worktree list` (richer table) |
| `rm br` | `git worktree remove <path>` |
| `prune` | `git worktree prune` |
| `status` | `git status --porcelain=2` per worktree |



## How it works

Flow diagram and visual overview of the command path, default layout, and weekly lifecycle:

- Interactive HTML: [`docs/how-it-works.html`](docs/how-it-works.html)
- SVG visual: [`docs/flow.svg`](docs/flow.svg)
- Use cases image: [`docs/use-cases.svg`](docs/use-cases.svg)

```text
You  →  sidetrack CLI  →  gitops  →  git worktree
                              ↓
              ~/code/app-worktrees/<branch>
```

Typical loop: mid-feature → `add`/`go` for hotfix or PR review → work isolated → ship → `rm`/`cleanup`.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
sidetrack --help
```

## License

MIT
