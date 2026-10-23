# CoverWorkbench development conventions

- Commit titles must use `[TYPE]: description`, with an uppercase type from FEAT, FIX, DOCS, STYLE, REFACTOR, PERF, TEST, BUILD, CI, CHORE, REVERT. Match the actual scope; do not invent historical fixes when importing a baseline.
- Use concise English-only commit titles. Commit bodies may use Chinese or English. Prefer one reviewable concern per commit, and explain meaningful behavior and validation in the body when needed.
- This is a local Windows application. Keep user song projects, original audio, lyrics, model weights, generated DAW templates/presets, runtime dependencies and reports out of Git. Preserve existing originals and use copies for project edits.
- Source belongs in app/, tools/, tests/, integrations/sv/, docs/, and assets/. config/projects.json and integrations/studio-one/ hold local settings; consult their examples/README before rebuilding another checkout.
- Never run tools/bootstrap.py or old UI patch/install scripts just to validate repository changes: they write pilot records or interface files. Use the focused checks documented in docs/GitWorkflow.md.
- Follow docs/GitWorkflow.md for setup and commit workflow. Do not change global Git configuration. Keep new directory names in English.
