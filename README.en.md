<div align="center">

![CoverWorkbench — Less repetition. More music.](docs/images/cover.svg)

# CoverWorkbench

**Less repetition. More music.**

A local cover-production workbench for Synthesizer V and Studio One.<br>
Bring lyric preparation, repetitive tasks, mix-session setup and delivery into one place.

[简体中文](README.md) · **English**

[![Windows CI](https://github.com/FeiyangHong/CoverWorkbench/actions/workflows/ci.yml/badge.svg)](https://github.com/FeiyangHong/CoverWorkbench/actions/workflows/ci.yml)
[![MIT License](https://img.shields.io/badge/license-MIT-8b6ce0)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB)](https://www.python.org/downloads/windows/)

[Quick start](#quick-start) · [Preview](#preview) · [Deployment](docs/Deployment.md)

</div>

## What it helps with

CoverWorkbench handles repeatable preparation and delivery tasks while detailed lyric, note, pronunciation and voice editing stays in SV. The website is a local control panel: normal use requires no cloud account, Codex or Node.js. **The application UI is currently Chinese.**

| Stage | What the workbench provides | What you decide |
| --- | --- | --- |
| Project preparation | Import a saved SVP into an original snapshot and a separate work copy | Song, language and source version |
| Lyrics and subtitles | Import local lyrics or explicitly search, prepare optional Japanese romaji and subtitle drafts | Lyrics, readings, translation and timing |
| Repetitive SV tasks | Native scripts for phrase lyrics, phrase reuse and group-level base voice presets | Pitch, rhythm, voice bank and expressive details |
| Studio One setup | Build an independent Song from a compatible local template, mapping vocal outputs and preserving effects and routing | Template choice and mix adjustments for the new song |
| Mixing reference | Find controls by sound goal, with clear control maps, cropped references and reverb/delay/EQ A/B demos | Audition and adjust in Studio One |
| Checks and delivery | Use local FFmpeg for audio checks, delivery packages and video audio replacement | Final listening, visuals and publication |

## Preview

### Workflow desk: prepare materials, focus on music, organize delivery

![Workflow desk with phrase lyrics, phrase reuse and voice preset tools](docs/images/workflow.png)

### Studio One: inspect parts, assign roles, choose a starter mix template

![Studio One preparation with two leads, one harmony and the starter template effect routing](docs/images/studio-one.png)

> Screenshots use an isolated, fictional **Moonlit Demo** project containing only programmatically generated `la` notes. Paths are normalized to generic examples. No real songs or personal settings are included. These are actual UI and track-inspection results; no native synthesis or Song generation was performed. Fresh installations include two starter templates; their licensed plugins must be installed separately.

<details>
<summary>Three desktop icons for your workspace</summary>

| Signature | Vocal | Studio |
| :---: | :---: | :---: |
| <img src="assets/icons/cw-signature.png" width="120" alt="Signature desktop icon"> | <img src="assets/icons/cw-vocal.png" width="120" alt="Vocal desktop icon"> | <img src="assets/icons/cw-studio.png" width="120" alt="Studio desktop icon"> |

Select and apply an icon from **桌面图标 / Desktop icons** in the app. Windows ICO versions are included in the repository.

</details>

## Workflow

![Five steps: separate media, edit in SV, build a mix session, mix in Studio One, check and package](docs/images/workflow-en.svg)

Already have a finished SVP? Start with the Studio One builder; there is no need to repeat extraction or correction.

## Quick start

Native integrations target **Windows** and require **Python 3.11+**.

```powershell
git clone https://github.com/FeiyangHong/CoverWorkbench.git
cd CoverWorkbench
.\Setup.ps1
.\Start.ps1
```

Open <http://127.0.0.1:8765/>:

1. Use **环境设置 / Environment settings** to select local tools and your Songs directory. Choose a bundled starter in the Studio One page, or register your own mix template.
2. Use **导入工程 / Import project** to select a saved SVP, title and language. You can also use the Studio One builder directly.
3. Open the work copy in SV, edit and save before reading it from the workbench. After rendering, use the checks and delivery tools.

Setup creates an isolated `.venv` and an empty workspace without modifying SV, Studio One or MSST. Japanese readings and romaji are optional:

```powershell
.\Setup.ps1 -WithLyrics
```

SV scripts must be installed separately into the editor's script directory and rescanned. See **[Deployment](docs/Deployment.md)** for tool configuration, scripts, template requirements, alternatives when PowerShell scripts are blocked, and migration.

Open **混音指南 / Mixing guide** to find controls by sound goal. With the optional host installed, choose your own vocal file and interval for real local **FabFilter Pro-R 2 / Timeless 3 / Pro-Q 3** A/B renders. Plugin-free browser teaching examples remain available. See the [guide overview](docs/MixingGuide.md) for setup and limits.

## Starter mix templates

A fresh installation offers these directly in the Studio One builder, without registering a Song first:

| Template | Mix structure |
| --- | --- |
| **Studio Vocal Plate** | Three lead recipes, harmony processing, plate reverb and delay sends, routed through a vocal bus |
| **Studio Vocal Delay** | Lead and harmony processing, plate reverb and a separate delay return; the delay return starts muted and can be enabled as needed |

Both preserve the author's actual EQ, compression, de-essing, send levels and routing. Song content, lyrics, voice selection, personal paths and device metadata have been removed. Voices and performance come from your imported SVP.

Install your own licensed **Synthesizer V Studio Pro** and **FabFilter Pro-Q 3, Pro-C 2, Pro-DS, Pro-R 2 and Timeless 3**. SV2 still needs local host configuration in Environment settings. Audition and adjust levels and effects for each new song. See the [template guide](assets/studio-one/README.md).

## Before you start

- **Bring your own software and materials.** Songs, lyric libraries, voice banks, model weights and commercial plugin binaries are not bundled. The starter templates contain sanitized effect parameters and routing only. Install FFmpeg/FFprobe yourself. Online lyric searches send requests to the provider.
- **Studio One templates have structural requirements.** The builder supports compatible Studio One 7 templates, constant tempo, a single meter and 1–16 vocal outputs. Multiple leads and songs without harmony are supported; the template itself still needs a harmony recipe. Arbitrary Song layouts are not guaranteed to work.
- **SV2 needs additional local host state.** Configure your own SV2 host in Environment settings before generating SV2 Songs on a fresh installation. See the [Studio One integration guide](integrations/studio-one/README.md).
- **Assisted results need human review.** Pitch comparisons provide diagnostic clues, not correctness scores. Lyrics, alignment, pronunciation and mix quality need checking. Experimental GAME/WhisperX scripts and models are outside the portable distribution.
- **Trusted local use only.** Do not expose the server publicly or use it as a multi-user service. See [SECURITY.md](SECURITY.md).

## Files and privacy

Source code is managed separately from creative work. Git ignores local settings, project indexes, song copies, lyrics, reports, models and runtime environments; back these up separately. On another computer, reinstall dependencies, select a starter or register your own templates, and re-import materials. Existing absolute references are not automatically migrated.

| Directory | Contents |
| --- | --- |
| `app/` | Local service and web interface |
| `integrations/sv/` | Installable SV script sources |
| `tools/`, `tests/` | Setup, release checks and validation tools |
| `docs/`, `assets/` | Documentation, demo screenshots and product icons |
| `config/` | Public example configuration; personal settings are ignored |
| `projects/`, `data/`, `runtime/` | Local creative and runtime data, excluded from Git |

## License

CoverWorkbench's original source, documentation and product icons use the **[MIT License](LICENSE)**. Commercial use and proprietary modifications are permitted, subject to retaining the copyright and license notice. Third-party components, music, voice banks and user materials retain their own terms; see the [license policy](docs/Licensing.md) and [third-party notices](THIRD_PARTY_NOTICES.md).
