# Starter vocal mixes / 初始混音模板

新安装的工作台会自动提供这两套模板，不需要手动注册或解压。

| Name | Vocal recipes | FX routing |
| --- | --- | --- |
| Studio Vocal Plate | Three lead recipes: Pro-Q 3 → Pro-C 2 → Pro-DS; harmony uses the same chain | Plate and delay sends return to the vocal bus |
| Studio Vocal Delay | Lead: Pro-Q 3 → Pro-C 2 → Pro-DS; harmony: Pro-Q 3 → Pro-DS | Plate and delay return to Main; delay starts muted |

Both include backing-track EQ and preserve the author's actual DSP parameters, channel gains, send levels and routing. Multiple leads and songs without harmony are supported. The backing fader starts at **−15 dB**, which is a starting point to adjust by ear.

需要自行安装 **Studio One 7、Synthesizer V Studio Pro、FabFilter Pro-Q 3、Pro-C 2、Pro-DS、Pro-R 2 和 Timeless 3**。使用 SV2 时仍需在环境设置中捕获本机 SV2 宿主。模板不提供软件、插件或声库授权；缺少插件时请安装对应插件或使用自己的兼容模板。

## What is distributed

The owner authorized these reusable mixes for publication. `.cwmix` is a ZIP-based, media-free recipe containing the supported Song XML structure, sanitized effect parameter presets and one empty SV1 host state. It is **not a song to open directly**. The builder materializes a local `.song` under ignored `runtime/starter-templates/`, then replaces placeholder media and SVP links when generating your own session. No archive files are extracted into arbitrary directories.

The public recipes contain **no audio, notes, lyrics, voice selection, original song names, original paths, user identities, machine identifiers, hardware assignments, authorization data or plugin binaries**. Controller/UI metadata is reset; effect component/DSP bytes are retained unchanged. The single one-second backing event is a structural placeholder and contains no audio.

The channel settings and routing are covered by this repository's MIT license. Third-party software and file formats retain their own terms. New songs still require listening and mix adjustments. File-structure validation is not a claim about native rendering or sound quality.

## Maintenance

`index.json` records generic names, required plugins, archive SHA-256 values and effect-component hashes. `app/mix_bundle.py` validates archive structure, allowed attachments, empty host state and placeholder-only links. Release checks also inspect these compressed assets, including historical versions.

To export another owner-authorized source locally:

```powershell
python tools/export_mix_starter.py --song 'C:\Music\My Template.song' --id my-starter --name 'My Starter' --output 'work/my-starter.cwmix'
```

Review every exported entry before adding a public asset, update the manifest and release allowlist, and run `python tests/starter-templates.py`. Keep source Songs and export provenance reports private. Original projects must never be overwritten.
