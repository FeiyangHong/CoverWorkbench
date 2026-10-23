# Contributing

CoverWorkbench is a Windows-first local media companion. Preserve source songs and use working copies. Review [Deployment](docs/Deployment.md) before touching native integrations.

## Development setup

```powershell
.\Setup.ps1
.\tools\SetupGit.ps1
python tests/git-conventions.py
python tests/portable-smoke.py
python tests/windows-launcher.py
```

Use Python 3.11+ and Node.js 22+ for optional browser tests:

```powershell
npm ci
npx playwright install chromium
python tests/portable-smoke.py --browser
```

The portable suite copies only version-controlled/non-ignored source into a fresh temporary directory with spaces in its path, starts an isolated loopback server, imports synthetic notes, verifies source preservation, exercises settings/lyrics and generates SV scripts into a temporary folder. It does not launch native applications or alter existing songs. Screenshots remain under ignored `reports/`.

Maintainer-only native tests and historical pilot scripts are not distributed because they depend on private projects. Public tests use synthetic fixtures. Do not add personal song files to make a test runnable.

## Commits and reviews

All commit **titles must be in English**, with `[TYPE]: Description` and one of FEAT, FIX, DOCS, STYLE, REFACTOR, PERF, TEST, BUILD, CI, CHORE, REVERT. Example: `[FIX]: Preserve source paths when importing an SV project`. The local hook rejects non-ASCII titles and invalid types; bodies can be Chinese or English. Keep a change reviewable, explain meaningful behavior and tests, and do not invent historical fix commits for a source import.

Use feature branches for substantial work. Include a UI screenshot when useful, and distinguish structural tests from native synthesis/listening tests. Never submit copyrighted songs, lyrics, proprietary presets, license keys, user-specific settings or large model weights. Tests should generate synthetic fixtures.

The project uses the [MIT License](LICENSE). Submit only contributions you have permission to distribute under those terms. Third-party material retains its own license and must be identified separately. See [Licensing](docs/Licensing.md).
