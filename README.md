# CoverWorkbench

A local cover-production workbench for Synthesizer V and Studio One. Keep note correction and voice editing in SV; use the workbench for lyrics, project setup and delivery.

**Windows-first · Python 3.11+ · local files · no cloud account required**

Repository: [FeiyangHong/CoverWorkbench](https://github.com/FeiyangHong/CoverWorkbench)

## Quick start

```powershell
.\Setup.ps1
.\Start.ps1
```

Open <http://127.0.0.1:8765/>. Use **环境设置 / Environment settings**, then **导入工程 / Import project**. Setup creates an isolated `.venv` and an empty workspace. It does not modify SV, Studio One or MSST. Japanese romaji is optional: `Setup.ps1 -WithLyrics`.

Read **[Deployment / 部署指南](docs/Deployment.md)** for prerequisites, templates, SV scripts and migration. Codex and Node.js are not required to run the app. The UI is currently Chinese; English UI translation is not implemented.

## Features and boundaries

- Import a saved SVP into a snapshot and separate work copy.
- Prepare local or explicitly searched lyrics, optional Japanese romaji and editable subtitles.
- Generate an independent Studio One Song from your compatible local template, with 1–16 vocal outputs, multiple leads or no harmony.
- Queue audio checks, delivery packaging and video audio replacement through user-installed FFmpeg.
- Install SV scripts for repeated phrase/voice operations and optional live review of registered work copies.
- Choose one of three Windows desktop icons.

You supply your own media, lyrics, licensed applications, voice banks, plugins and Song templates. No original songs, captured plugin presets or model weights are distributed. SV2 generation still requires a separately captured local host preset. Arbitrary Song layouts and non-Windows native integrations are not supported.

Pitch comparisons are diagnostic clues, not correctness scores. Lyrics, timing, plugin compatibility and rendered sound still need human review. Experimental GAME/WhisperX tools are not part of the portable baseline.

## Source and data

Local settings, project indexes, song copies, reports, environments and models are ignored by Git. Back up creative work separately. Existing absolute media/template references are not automatically rebased when changing devices; fresh setup and re-import are supported.

See [CONTRIBUTING](CONTRIBUTING.md), [Git workflow](docs/GitWorkflow.md), [security boundaries](SECURITY.md) and [third-party notices](THIRD_PARTY_NOTICES.md).

All commit titles use **English** `[FEAT]: ...`, `[FIX]: ...`, `[DOCS]: ...`, etc. Run `tools/SetupGit.ps1` in each clone.

```powershell
python tests/portable-smoke.py
python tests/git-conventions.py
python tools/release_check.py
```

CI is configured for clean Windows checkouts using Python 3.11/3.13, synthetic fixtures and a browser flow. Configured CI is not a claim that a hosted run has passed. Native synthesis requires separate checks.

## License

CoverWorkbench's original source, documentation and product icons are available under the **[MIT License](LICENSE)**. Commercial use and proprietary modifications are permitted, subject to retaining the copyright and license notice. Third-party components and user-owned media retain their own terms; see [License policy](docs/Licensing.md) and [third-party notices](THIRD_PARTY_NOTICES.md).
