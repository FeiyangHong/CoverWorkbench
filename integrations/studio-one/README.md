# Local Studio One templates

All files in this directory except this README are local-only and ignored by Git. No commercial plugin state or user Song is distributed.

In Environment settings, register your own SV1 base Song template and capture your own SV2 host state from a saved Song. Capture accepts exactly one supported SV2 VST3 instance. It creates a unique local preset and updates `sv2-host.json`; previous registration is backed up under `runtime/sv2-host-backups`. The JSON `preset` path is relative to the workbench root.

Custom base-template registrations live in `config/daw-templates.local.json`. Legacy installations may also have template metadata under `data/projects`. Keep those records and external Song resources in private backups.

See [Deployment](../../docs/Deployment.md) for supported template structure and native validation limits. Install your own licensed applications, plugins and voice banks before using generated Songs.
