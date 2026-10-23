# Security and privacy

CoverWorkbench listens on `127.0.0.1`, validates Host/Origin for browser requests and expects a trusted local user. It can read selected local files, write working copies, run configured media executables and open local applications. It has no authentication, tenant isolation or remote deployment mode. Do not bind it to a LAN/public address, tunnel it, or share the entire machine session with untrusted users.

Only use SVPs, Songs, model code and plugins you trust. Registration and parser checks are compatibility checks, not a hostile-file sandbox. The settings page intentionally allows choosing local executable paths. Software/voice-bank activation stays in the vendor application; the workbench does not collect activation keys.

Local songs, media, lyrics, derived data, reports, settings and models are excluded from source control. Online lyric searches contact the selected provider when explicitly requested; optional package/model downloads also use the network. No analytics is included. Logs may contain local paths: inspect and redact them before sharing bug reports.

Private vulnerability reporting is enabled for this repository. Use [Report a vulnerability](https://github.com/FeiyangHong/CoverWorkbench/security/advisories/new) to contact the maintainer privately. Do not put exploit-ready reports, private songs or credentials into public issues.
