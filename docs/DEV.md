# Dev setup

This repo uses three standard dev tools, wired up but kept intentionally
non-intrusive:

| Tool         | Purpose                                 | Where it runs                 |
| ------------ | --------------------------------------- | ----------------------------- |
| `ruff`       | lint + auto-fix + format                | pre-commit (every `git commit`) |
| `mypy`       | static type checking                    | on demand (manual)            |
| `pre-commit` | orchestrates the hooks                  | `git commit`                  |

## First-time install

```bash
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install
```

After that every `git commit` will:

1. Run `ruff check --fix` (unused imports, undefined names, obvious bugs).
2. Run `ruff format` (quote style, blank lines, line endings).
3. Run the stock `pre-commit-hooks` suite (trailing whitespace, YAML/TOML
   validity, merge-conflict markers, no >500 KB files, no stray
   `breakpoint()`/`pdb` calls).

The `legacy/` tree and `data/` are excluded from every hook — they are
reference-only and data-only respectively.

## Config lives in

| File                        | Scope                                        |
| --------------------------- | -------------------------------------------- |
| `pyproject.toml`            | `[tool.ruff]` + `[tool.mypy]`                |
| `.pre-commit-config.yaml`   | which hooks run on `git commit`              |
| `requirements-dev.txt`      | pinned versions of ruff / mypy / pre-commit  |

## Expected clean state

```bash
ruff check .            # => All checks passed!
ruff format --check .   # => 0 files would be reformatted
python -m pytest        # => 35 passed
```

## mypy is deliberately not in pre-commit

`mypy core agents ui` currently surfaces ~45 pre-existing type issues
(mostly in `core/fetchers.py` and `core/wiki.py` — loose `dict` typing,
`loguru.Logger` vs stdlib `Logger` in `before_sleep_log`, optional-without-default
function args). They are **legitimate findings** that pre-date the tooling
and should be fixed incrementally; they are not an emergency. Reasons mypy
stays out of the commit hook for now:

1. `mypy` takes 30–90 s on this codebase cold-cache, which would make
   `git commit` feel broken.
2. Several of the errors come from third-party libs (`loguru`, `yfinance`,
   `praw`) that ship poor type info; chasing them leaks signal.
3. We want the hook to be 100 % green today so that contributors trust it
   and don't `--no-verify` past it out of habit.

Run mypy manually before pushing anything substantial:

```bash
mypy core agents ui
```

If you fix a file completely, consider flipping `disallow_untyped_defs = true`
for that specific module via a `[[tool.mypy.overrides]]` block in
`pyproject.toml`, so the check becomes a ratchet and can't regress.

## What if a hook fails?

- `ruff` auto-fixed your files → the commit is aborted, the fixes are staged
  for you; re-run `git commit` to pick them up.
- `ruff` found a lint error it can't fix → read the message; it prints the
  exact rule ID (e.g. `B023`) and a fix suggestion.
- `check-added-large-files` blocked a file → if it's a legitimate data asset,
  move it under `data/` (which is already excluded); if it's an artifact,
  delete it.
