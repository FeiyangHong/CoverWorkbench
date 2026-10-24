# Deployment / 部署指南

## Windows quick start

Install **Python 3.11+** from [python.org](https://www.python.org/downloads/windows/), with the Python launcher or `python` on PATH. Extract or clone into a writable local directory. Spaces in the checkout path are supported. Administrator access, Codex, MSST and Node.js are not required for ordinary use.

```powershell
cd 'C:\Music Tools\CoverWorkbench'
.\Setup.ps1
.\Start.ps1
```

If Python is not detected, use `Setup.ps1 -PythonExe 'C:\Path\To\python.exe'`. Setup creates `.venv` and empty local records, without replacing an existing project index. For Japanese readings/romaji, run `Setup.ps1 -WithLyrics`. The core service needs only the Python standard library; it does not automatically download models. If PowerShell blocks local scripts, follow your device's execution policy; an alternative is `python tools/setup.py` then `python app/server.py` (foreground, Ctrl+C to stop).

Open <http://127.0.0.1:8765/>. `Start.vbs` is the quiet Windows launcher. `Stop.ps1` stops only the recorded server process for this checkout. Do not close or stop a server while it is rendering delivery jobs. A second installation must use another port: set `$env:COVERWORKBENCH_PORT='8766'` before starting. Native SV bridging uses local files, not that port.

## First use / 首次使用

1. Open **环境设置 / Environment settings**. Select your FFmpeg and FFprobe executable files, Studio One executable, Songs directory and optional MusicLyricApp cache. Empty executable fields use PATH detection. Settings go to ignored `config/settings.local.json` and take effect on the next request.
2. Open **导入工程 / Import project**. Select a saved SVP, title, artist and language. Quoted Windows paths are accepted. A separated lead vocal is optional; inspecting supplied audio requires FFprobe. Use a supported browser audio format (WAV is recommended); AIFF playback depends on the browser.
3. The importer creates `projects/song-<id>/snapshots/sv/source.svp` and `working/sv/project.svp`. It registers the new project without replacing existing ones. Media files stay at their original locations, read-only. Save and edit the work copy in SV. You can use the DAW builder without importing a project first.
4. Use lyrics/subtitles and delivery tools as needed. Lyrics searches make explicit network requests to the provider; files are otherwise processed locally. Imported lyrics, readings and timings still need human review.

FFmpeg and FFprobe should come from the same installation; see the [official download page](https://ffmpeg.org/download.html). They are not bundled. Licensed SV/Studio One software, voice banks, plugins and media are supplied by the user.

## SV scripts

Use the script folder shown by your installed SV editor. The installer generates four scripts with this checkout's absolute path. It backs up changed installed scripts to `runtime/sv-script-backups`, and never changes the tracked templates.

```powershell
.\.venv\Scripts\python.exe tools/install_sv_tools.py --dest 'C:\Your\SV\scripts'
```

Repeat `--dest` for SV1 and SV2. Rescan scripts in SV. Do not copy the `.lua` templates directly: `__CW_ROOT__` is replaced by the installer. The bridge and editing scripts permit only registered work copies. After moving the workbench, reinstall scripts. Existing local installations are not silently reinstalled by Setup.

## Studio One templates

Two sanitized starter mixes, **Studio Vocal Plate** and **Studio Vocal Delay**, are available immediately in the Studio One builder. Install your own licensed SV1 and FabFilter Pro-Q 3, Pro-C 2, Pro-DS, Pro-R 2 and Timeless 3. The presets contain parameter state and routing, not plugin binaries, voice banks or media. SV2 still requires your own locally captured host state. See the [starter template guide](../assets/studio-one/README.md).

You can also register your **own local `.song`** in Environment settings. Current support is deliberately restricted to the layout already exercised by the builder:

- A saved Studio One 7 Song with exactly one SV1 instrument (`Inst01`) and its embedded Synthesizer V VST3 preset.
- Mixer outputs named `Lead` (or containing `主声`) and `Harmony` (or containing `和声`). Several Lead channels may supply different effect recipes. The template has a Harmony recipe even when a new song uses no harmony.
- Exactly one backing audio track, clip and event starting at zero; no unrelated tracks, takes or unused media. Preserve all referenced files. Plugin binaries and authorization must be installed on the destination computer.
- Use the desired vocal inserts, sends, FX returns and vocal bus in this template. There is no automatic substitute for missing commercial plugins.

Registration validates these basic conditions. It does not certify arbitrary Song variants or plugin compatibility. Generation still checks references, creates an independent directory and leaves the template intact. Constant tempo / one meter only; 1–16 vocal outputs. Always open and audition the generated Song before relying on it.

For **SV2**, a separately captured local host JSON and VST3 state are still required, as documented in [the integration README](../integrations/studio-one/README.md). The generic base template remains SV1. A fresh installation can inspect SV2 files but cannot build SV2 Songs until that native host state is configured. To capture it locally, save an empty Studio One Song with exactly one supported SV2 VST3 instrument, then enter that Song under Environment settings > 配置 SV2 宿主. The app extracts the actual component state and retains a backup of the prior registration. It does not synthesize vendor state or activate a voice bank. Unsupported plugin class IDs are rejected. Existing legacy local template registrations remain usable.

## Optional real FabFilter auditions

Run `tools/InstallNativeAudio.ps1` to install the optional Pedalboard host into the interpreter used by this checkout, then refresh the mixing guide. Configure FFmpeg/FFprobe and separately install and authorize FabFilter Pro-R 2, Timeless 3 and/or Pro-Q 3 in VST3 format. Standard Windows plugin paths are detected; `COVERWORKBENCH_VST3_DIR` can specify their containing directory before server startup. Plugins and host binaries are never included in Git or the source release. The guide works without this optional dependency and reports unavailable plugins explicitly. See [Mixing guide](MixingGuide.md) for source selection, intervals, rendering limits and private cache management.

The same host can read saved Studio One `.song` mixer state and audition mapped dry stems with backing audio. This requires the Song's actual FabFilter Pro-C 2 / Pro-DS inserts in addition to the three adjustable plugins when those inserts are present. Unsupported routing, automation and host-tempo synchronization are rejected explicitly; this is a static reconstruction, not an embedded Studio One instance or a guaranteed sample-identical export. See the mixing guide for channel mapping and source alignment.

## Moving to another computer

Source code alone is sufficient for a fresh empty workspace. Install tools and re-import your saved SVP on the new device; register your own templates and reinstall scripts. Existing working data includes absolute links and is **not automatically rebased** when copied. To continue previous work, back up its current SVP, media, lyrics/subtitles, `config/*.local.json`, `config/projects.json`, `data`, `projects`, and local integrations separately, then repair/re-import references on the destination. Do not copy `.venv`; recreate it with Setup.

The supported native deployment target is Windows. Starting the Python HTTP core elsewhere does not imply that Studio One, desktop shortcuts, Explorer or SV integrations work there. This is a trusted local desktop companion, not a multi-user/LAN/cloud service; never expose its port through a reverse proxy or public tunnel.

## Development and experimental tools

Historical pilot scripts and private native tests are excluded from the public repository. GAME/WhisperX were optional research experiments, with upstream provenance recorded in `config/dependencies.json`; their scripts, weights and scientific environments are not part of this distribution. Do not interpret source availability as one-click model deployment.

See [CONTRIBUTING](../CONTRIBUTING.md) for clean-checkout tests. A clean-clone test uses synthetic notes and no copyrighted audio. Native synthesis quality and arbitrary third-party DAW templates require separate manual validation.
