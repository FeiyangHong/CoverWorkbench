# Git workflow

The public repository is https://github.com/FeiyangHong/CoverWorkbench, with `main` as the default branch. Each checkout should run `tools/SetupGit.ps1` to activate repository-local hooks and settings. This does not modify global Git configuration.

## Commit titles

Use English `[TYPE]: Description` titles. Allowed types: FEAT, FIX, DOCS, STYLE, REFACTOR, PERF, TEST, BUILD, CI, CHORE, REVERT. Bodies may use English or Chinese. Examples:

- `[FIX]: Preserve existing mix sessions when creating versions`
- `[FEAT]: Add local template registration`
- `[DOCS]: Explain Windows installation`

Use a focused branch and stage only relevant files:

```powershell
git switch -c fix/project-paths
git add app/daw.py
git diff --cached
git commit -m "[FIX]: Validate local project paths"
git push -u origin fix/project-paths
```

The commit hook validates title format. The pre-push hook audits the full history of every ref being pushed, so old private snapshots cannot accidentally be published by pushing tags or extra branches. Both hooks require setup in each clone; the history check uses Python 3.11+.

## Public and local boundaries

Source, original product icons, configuration examples and synthetic tests belong in Git. Real `config/projects.json`, `config/*.local.*`, data, projects, media, model weights, environments, captured native presets and reports do not. Historical private pilot tools remain ignored on the maintainer's device and are not required to deploy the public application.

Git is not a backup for creative work. Back up recordings, working SVPs, generated Songs and native plugin state separately. Never force-add private files or push all branches/tags blindly.

## Initial public history

The public history starts from a reviewed source-only baseline. Earlier local development history is retained in an offline private bundle; it was not uploaded. Public commits use a GitHub noreply email on the maintainer's checkout. No private archive tags are included in the public branch.

## Checks

```powershell
python tests/git-conventions.py
python tests/portable-smoke.py
python tools/release_check.py --for-public-release --ref HEAD
```

See CONTRIBUTING.md for browser and Windows launcher tests. Protect originals and avoid running native application tests just to check repository status.
