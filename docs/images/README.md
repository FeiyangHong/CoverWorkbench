# README visual assets

- `cover.svg`: original, code-authored brand illustration; it is not a product screenshot.
- `workflow-zh.svg` / `workflow-en.svg`: original bilingual five-step workflow illustrations. Regenerate with `python tools/render_workflow_diagram.py`; no user data or external dependencies.
- `workflow.png`: actual workflow UI using synthetic notes in an isolated checkout.
- `studio-one.png`: actual inspection of the same three-track synthetic SVP. No template is registered and no Song is generated. Visible paths are normalized to `C:\CoverWorkbench` examples in the browser after inspection.

These files contain no personal songs, lyrics, settings, voice-bank data or plugin state. All synthetic notes use `la`. Screenshots demonstrate UI behavior, not native synthesis or audio quality.

## Regenerate on Windows

From the repository root, with Python 3.11+, Node.js and Microsoft Edge installed:

```powershell
npm ci
$env:CW_BROWSER_CHANNEL='msedge'
python tools/capture_readme.py
```

Alternatively, run `npx playwright install chromium` and omit/unset `CW_BROWSER_CHANNEL` to use Playwright's Chromium. Node.js and Playwright are documentation-development dependencies, not normal app requirements.

The capture tool copies only Git-tracked/non-ignored source into a temporary folder under `work/`, creates an empty configuration and synthetic SVP, and starts a separate loopback server on a free port. It never connects to the user's running workbench, opens native applications or reads personal project settings. The server and temporary folder are cleaned up on completion. Output overwrites only the two PNG files beside this document.

Review the screenshots visually before committing: no personal paths, no real song names, no clipped controls, and no runtime errors. Update both README language versions when changing captions or capabilities.
