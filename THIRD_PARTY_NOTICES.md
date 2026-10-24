# Third-party components and excluded material

The distributed source tree does not include any original song/audio/video, user lyrics, Synthesizer V voice bank, personal Studio One Song, model weight or vendor checkout. The owner-authorized starter mix bundles include sanitized effect parameter state and an empty SV1 host state; they contain no plugin binaries, authorization data or media. Product icons are original code-authored SVGs and their rendered PNG/ICO variants; they do not include vendor product logos.

| Component | Use / distribution boundary |
| --- | --- |
| Python | Installed independently; core app uses its standard library. [License](https://docs.python.org/3/license.html). |
| pykakasi | Optional GPL-3.0-or-later pip dependency for Japanese readings. Its own license and transitive dependency notices apply; inspect the installed distribution before bundling it. The release archive does not vendor it. [Upstream](https://github.com/miurahr/pykakasi). |
| Playwright | Development-only browser tests, installed by npm. Browser binaries are separate downloads. [Upstream](https://github.com/microsoft/playwright). |
| FFmpeg / FFprobe | User-installed executables. Licensing depends on the chosen build and enabled components; no binaries are bundled. [Legal page](https://ffmpeg.org/legal.html). |
| GAME / WhisperX / CTC models | Optional, legacy experiments; code/weights are excluded. Recorded upstream commits/checkpoint hashes are in `config/dependencies.json`; check each upstream license/model card before downloading or redistribution. |
| Synthesizer V / Studio One / voice banks / VST plugins | Independently licensed commercial software. The workbench grants no rights to these products or the user's recordings. Native project generation uses sanitized bundled starter mixes or user-supplied local templates; the corresponding licensed plugins remain required. |
| FabFilter interface illustrations | Cropped local screenshots of Pro-Q 3, Pro-C 2, Pro-DS, Pro-R 2 and Timeless 3 are included solely to illustrate the mixing guide. Interfaces, logos and product names remain the property of FabFilter; the repository MIT license does not grant rights to those third-party designs or marks. No plugin binaries or license information are included. See [guide sources](docs/MixingGuide.md). |
| Lyric providers / MusicLyricApp cache | User-selected text/cache or explicit provider queries; lyric rights remain with their respective holders. Do not bundle cached lyrics or provider credentials. |

The main code license cannot override these third-party terms. Optional dependency installation does not mean permission to redistribute a bundled application under the main code license alone. In particular, comply with pykakasi's GPL terms when distributing a combined package; this source archive contains no such combined binary/package.
