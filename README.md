<div align="center">

![CoverWorkbench — Less repetition. More music.](docs/images/cover.svg)

# CoverWorkbench

**把时间，留给声音。**

面向 Synthesizer V 与 Studio One 的本地翻唱工作台。<br>
歌词准备、重复操作、混音工程搭建与交付整理，放在一个地方。

**简体中文** · [English](README.en.md)

[![Windows CI](https://github.com/FeiyangHong/CoverWorkbench/actions/workflows/ci.yml/badge.svg)](https://github.com/FeiyangHong/CoverWorkbench/actions/workflows/ci.yml)
[![MIT License](https://img.shields.io/badge/license-MIT-8b6ce0)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB)](https://www.python.org/downloads/windows/)

[快速开始](#快速开始) · [界面预览](#界面预览) · [部署指南](docs/Deployment.md)

</div>

## 它能帮你做什么

CoverWorkbench 把适合批量处理的步骤交给工具，让歌词、音符、发音和声线的精细调整继续留在你熟悉的 SV 中。网站是本机控制台，普通使用无需云端账号、Codex 或 Node.js；目前界面为中文。

| 环节 | 工作台提供的能力 | 仍由你决定 |
| --- | --- | --- |
| 工程准备 | 导入已保存的 SVP，建立原始快照与独立工作副本 | 曲目、语言与素材版本 |
| 歌词与字幕 | 导入本地歌词或主动搜索，生成可选日语罗马音与字幕草稿 | 歌词、读音、翻译与时间轴校正 |
| SV 重复操作 | 原生脚本：整段填词、重复乐句复用、音符组基础调声预设 | 音准、节奏、声库、逐句表情 |
| Studio One 建工程 | 从兼容的本机模板生成独立 Song，分配人声输出并复用效果器与路由 | 模板选择与新曲的混音微调 |
| 混音学习 | 按声音问题查找旋钮，插件实拍图可点击标注、放大查看 | 在 Studio One 中试听与调整 |
| 检查与交付 | 通过本机 FFmpeg 检查音频、整理交付包、替换视频音轨 | 最终试听、画面与发布 |

## 界面预览

### 流程控制台：准备素材，专注创作，整理交付

![流程控制台，展示整段填词、重复乐句复用和调声预设入口](docs/images/workflow.png)

### Studio One：读取声部，确认角色，选择初始混音模板

![Studio One 工程准备页，展示两条主声、一条和声及初始模板的效果器路由](docs/images/studio-one.png)

> 截图来自隔离环境中的虚构 **Moonlit Demo** 工程，仅含程序生成的 `la` 音符。路径已替换为通用示例；不包含真实歌曲或私人配置。截图展示实际网页和音轨读取结果，未执行原生合成或生成 Song；新设备已提供两套初始模板，仍需安装对应的正版插件。

<details>
<summary>三种桌面图标，选择你的工作台标记</summary>

| Signature | Vocal | Studio |
| :---: | :---: | :---: |
| <img src="assets/icons/cw-signature.png" width="120" alt="Signature 桌面图标"> | <img src="assets/icons/cw-vocal.png" width="120" alt="Vocal 桌面图标"> | <img src="assets/icons/cw-studio.png" width="120" alt="Studio 桌面图标"> |

在网页的「桌面图标」中选择并应用。仓库包含对应的 Windows ICO 文件。

</details>

## 工作流程

![五步制作流程：分离素材、SV 校对调声、工作台创建混音工程、Studio One 混音、工作台检查交付](docs/images/workflow-zh.svg)

已有调好的 SVP？直接从「Studio One 建工程」开始，无需重走提取与校对。

## 快速开始

支持的本机集成环境为 **Windows**，需要 **Python 3.11+**。

```powershell
git clone https://github.com/FeiyangHong/CoverWorkbench.git
cd CoverWorkbench
.\Setup.ps1
.\Start.ps1
```

打开 <http://127.0.0.1:8765/>：

1. 在 **环境设置** 中选择本机工具、Songs 目录。Studio One 页面可直接选择随附的初始模板，也可注册自己的混音模板。
2. 在 **导入工程** 中选择已保存的 SVP，填写标题与语言。也可直接使用 Studio One 建工程页。
3. 在 SV 中打开工作副本进行创作，保存后再让工作台读取；渲染完成后进入检查与交付流程。

安装会创建独立 `.venv` 和空白工作区，不会修改 SV、Studio One 或 MSST。日语读音与罗马音依赖可按需安装：

```powershell
.\Setup.ps1 -WithLyrics
```

SV 脚本需要另外安装到对应编辑器的脚本目录并重新扫描。工具配置、脚本安装、模板要求、PowerShell 启动替代方法和换机说明见 **[部署指南](docs/Deployment.md)**。

混音时可打开工作台的 **「混音指南」**，按“混响太多”“回声太长”“人声闷”等问题查找操作，详见 [指南说明](docs/MixingGuide.md)。

## 初始混音模板

新安装即可在「Studio One 建工程」中选择，无需先准备自己的 Song：

| 模板 | 混音结构 |
| --- | --- |
| **Studio Vocal Plate** | 三组主声处理、和声、Plate 混响与延迟发送，统一汇入人声总线 |
| **Studio Vocal Delay** | 主声与和声处理、Plate 混响及独立延迟返回；延迟返回默认静音，按需启用 |

两套模板均保留作者实际使用的 EQ、压缩、齿音、发送电平与路由，已移除歌曲内容、歌词、声库选择、个人路径与设备信息。导入新 SVP 后，声库与演唱内容来自你自己的工程。

需要自行安装 **Synthesizer V Studio Pro** 和 **FabFilter Pro-Q 3、Pro-C 2、Pro-DS、Pro-R 2、Timeless 3**。使用 SV2 时，仍需在环境设置配置本机 SV2 宿主。新曲的音量与效果参数请试听后微调。详见 [模板说明](assets/studio-one/README.md)。

## 使用前了解

- **软件与素材由你提供。** 仓库不附带歌曲、歌词库、声库、模型权重、商业插件程序。随附混音模板只包含清理后的效果器参数与路由。FFmpeg／FFprobe 需要自行安装；在线搜词会向提供方发送搜索请求。
- **Studio One 模板有结构要求。** 当前支持兼容的 Studio One 7 模板、固定速度与单一拍号、1–16 路人声，可有多条主声，也可没有和声。模板本身仍需包含和声处理配置；任意 Song 布局不保证兼容。
- **SV2 需要额外的本机宿主状态。** 新设备须在环境设置中配置自己的 SV2 宿主，之后才能生成 SV2 Song。详见 [Studio One 集成说明](integrations/studio-one/README.md)。
- **辅助结果需要试听确认。** 音高对比只提供排查线索；歌词、对齐、发音和混音没有自动正确性保证。GAME／WhisperX 实验脚本及模型不在便携发行范围内。
- **仅供可信的本机使用。** 不要将服务端口暴露到公网或作为多人服务。安全边界见 [SECURITY.md](SECURITY.md)。

## 文件与隐私

源码和创作数据分开管理。Git 忽略本地设置、工程索引、歌曲副本、歌词、报告、模型与运行环境；这些内容需要你另外备份。换机时应重新安装依赖、选择初始模板或注册自有模板，并导入素材；已有绝对路径不会自动迁移。

| 目录 | 内容 |
| --- | --- |
| `app/` | 本机服务与网页界面 |
| `integrations/sv/` | 可安装的 SV 脚本源文件 |
| `tools/`、`tests/` | 安装、发布检查与验证工具 |
| `docs/`、`assets/` | 文档、示例截图与产品图标 |
| `config/` | 公开示例配置；个人配置被忽略 |
| `projects/`、`data/`、`runtime/` | 本机创作与运行数据，不上传 Git |

## 许可证

CoverWorkbench 的原创代码、文档与产品图标采用 **[MIT License](LICENSE)**，允许商业使用及闭源修改，但须保留版权与许可声明。第三方组件、音乐、声库及用户素材遵循各自条款，见 [许可说明](docs/Licensing.md) 与 [第三方声明](THIRD_PARTY_NOTICES.md)。
