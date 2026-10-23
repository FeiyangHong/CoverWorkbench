# Publication and validation

## Public source boundary

The public repository starts from a source-only baseline under MIT. Private local development history, historical project-specific scripts/guides, song files, lyrics, model weights, configurations and private native plugin state are excluded. Two owner-authorized, sanitized starter mix bundles are now distributed under assets/studio-one/, with media-free archive validation and preserved DSP component hashes. The original files remain on the maintainer's machine. Public mixing assets contain empty SV host state, effect parameters and routing; no song content or device configuration.

All public commit titles follow the English `[TYPE]: Description` convention. A pre-push audit checks every commit in the refs being pushed, not just the latest working tree. This is a bounded filename/content-pattern audit, not a comprehensive security or legal certification.

## Validation performed locally

- Clean relocated source, without local projects/templates: startup, synthetic SVP import, source-hash preservation, English lyric import, settings, cross-origin rejection and SV script generation passed.
- Browser onboarding, environment settings, desktop/390px layouts and no page runtime errors passed.
- PowerShell 5.1: isolated virtual environment setup, first/repeated startup and shutdown passed, including Windows venv child-PID handling.
- Private native-template regression checked plugin-state bytes, notes/curves, output mapping, isolated references, version collisions and original hashes. Its fixtures are not distributed; native rendering/listening was not repeated for publication.

GitHub Actions runs the public synthetic and launcher suites. Check the repository's Actions tab for the actual hosted result; local validation does not imply a hosted run passed.

## Scope and licensing

MIT applies to original source, documentation and product icons. Third-party dependencies retain their licenses; optional pykakasi is GPL-3.0-or-later. No dependency binaries are vendored. Users supply licensed native applications, voice banks, plugins, media and any additional custom templates.

Windows is the native target. Existing media/template references are not automatically rebased between devices. Model experiments and an English UI are outside this release. Public-host multi-user operation is unsupported.
