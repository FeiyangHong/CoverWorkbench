# PyMSS 与旧 MSST

素材分离页可以选择 **PyMSS · App / 源码** 或 **MSST · 旧版备选**。两个引擎独立配置；切换不会改动旧 MSST、SVP、混音或视频工程。普通分离任务只有在全部预期输出存在、时长校验通过后才登记到歌曲；运行期间手动改变过的素材路径会保留。

## 连接现有 App

工作台在 Windows 上尝试从桌面 / 开始菜单快捷方式识别 Pymss Studio。也可展开 PyMSS 连接设置，选择 App 的安装目录。它会只读解析活动运行环境 `python-runtime/runtime-envs/active-runtime.json`，包括相对路径、核心 overlay，并读取 App 数据根目录中的 `settings/app.json` → `modelDir`。便携标记、自定义数据根目录和显式 Python / 模型目录设置同样支持。

任务直接调用活动环境里的 `pymss`，不启动第二个 App、不修改其 Python/Torch、不安装或升级其环境包。App 更新或切换环境后，刷新任务可重新识别。App 内独立发起的 GPU 任务不属于工作台队列，请避免同时运行。

## 连接源码

选择 PyMSS 或 Studio 源码仓库目录；自动尝试 `.venv/Scripts/python.exe`、`venv/Scripts/python.exe` 等位置。自定义环境请显式选择 Python。模型目录可以继续选 App 的模型目录，共享权重；源码包目录和活动 overlay 在独立工作进程中加载，不进入工作台网页服务的 Python 环境。

命令行也可连接并验证已有环境：

```powershell
python tools/ConnectPyMSS.py --directory 'D:\Apps\Pymss Studio'
python tools/ConnectPyMSS.py --directory 'D:\Source\pymss' --python 'D:\Source\pymss\.venv\Scripts\python.exe' --models 'D:\Apps\Pymss Studio\models'
```

## 模型共享与安装

点击 **准备缺少的推荐模型（联网）**，后台准备 Big7、DeUX、HyperACE v2 的 Vocals/Instrumental、Leap Xe 的 Vocals/Instrumental，以及三款 Karaoke。也可在上述连接命令后加 `--download`。

普通目录模型使用 PyMSS catalog 的标准相对路径，App 刷新模型库后可以识别。Leap Xe 不在当前 catalog，使用作者固定版本的权重和配套配置，保存在所选模型目录 `custom/Leap Xe/`，通过 PyMSS 标准用户模型登记接口以 `cw-leap-voc` / `cw-leap-inst` 登记，App 同样可以列出。已有同名自定义模型指向其他位置时拒绝覆盖。

已有完整模型文件保留，不静默恢复或覆盖手工调整过的配置。没有完整旧模型时需要联网下载。下载与登记可取消，下载片段保留用于继续。这里不捆绑或重新发布任何权重。

## 重叠、质量与测量

工作台的 PyMSS 任务提供 **高质量 87.5%**、**平衡 50%**、**模型原配置**三个选项，默认采用 DeUX → Frazer、87.5% 重叠、batch 4、TTA 关闭。在显存较少的设备上可将 batch 降至 1 或 2。Batch 可选 **1 / 2 / 4 / 8 / 16**，TTA 可开启或关闭；点击 **保存这组默认参数** 后，模型、重叠、batch 和 TTA 会在下次打开时恢复。旧 MSST 保持自己的配置，这些控件在旧引擎下禁用。

较高重叠增加相邻块的重复推理，可能改善衔接，不能保证和声分离或音色恢复单调变好。50% 到 87.5% 的分块计算量约为四倍，整任务耗时还包含启动、加载与写盘。Batch 是并行处理块数，不是质量档位；更高值会增加显存需求，也不保证更快。TTA 使用原输入、左右声道互换和极性反转的三次推理，恢复后平均；收益需要试听确认，默认关闭。

每个任务保存实际 batch / TTA 参数及测量记录；重试沿用原任务参数，不随之后保存的默认设置改变。阶段复用同时检查 batch 与 TTA，不复用不同参数的第一阶段结果。显存不足会明确失败并保留日志和测量，不会静默降档，也不会登记不完整输出。模型配置文件和 App 环境保持原样。

任务记录保存 `Metrics.json`：模型加载秒数、推理/写盘秒数、CUDA 分配与保留峰值，以及每 250 ms 采样的设备总显存和 GPU 利用率。CUDA 数值与整机数值的范围不同；设备采样包含其他应用，也可能漏过极短峰值。读数不可用时保留缺失状态，不能当作零显存。

## 模型对比与 SV1

素材分离页的 **模型对比试听** 提供歌曲/声部选择、同一位置 A/B 切换、原曲试听、循环区间和音量。原始分离文件与 RMS 匹配版本独立保存；没有真实干净分轨时不计算 SDR 或自动质量排名。

可复用脚本为开发者或批量评测准备：

```powershell
python tools/RunSeparationBenchmark.py --plan 'D:\Comparison\Plan.json'
python tools/RunSeparationBenchmark.py --plan 'D:\Comparison\Plan.json' --legacy-only
# 使用具备 numpy/soundfile 的 PyMSS 环境运行：
python tools/BuildSeparationAuditions.py --folder 'D:\Workbench\projects\Model Comparison'
```

计划的输出目录必须位于当前工作台 `projects/` 内。计划包含歌曲 `id`、`label`、原媒体 `source`、`bpm`，`folder`、`models`、`ffmpeg` 和 `ffprobe`；所有输入先复制再转为 44.1 kHz 双声道浮点 WAV。正式评测使用完整歌曲、87.5% 重叠，每首/模型独立冷启动一次。Karaoke 统一使用 Big7 完整人声，便于比较模型本身。

输出包括同轴排列三首歌的总 SV1 工程，以及各歌曲单独的 Raw / Matched 工程。原曲轨默认开启，其他轨默认静音，避免多份音频叠加；先将原曲轨静音（M），再取消目标轨的静音，按需 S 独听。匹配版按同首歌、同类声部整体 RMS 匹配，并保留公共 -3 dBFS 样本峰值余量，属于试听辅助，非 EBU 响度标准化。原始模型输出不被改写。已有试听 SVP 时脚本拒绝覆盖。

PyMSS/模型本身的版本和授权以各自仓库为准：

- [PyMSS 推理引擎](https://github.com/pymss-project/pymss)
- [PyMSS Studio](https://github.com/pymss-project/pymss-studio)
- [becruily 模型](https://huggingface.co/becruily)
- [unwa 模型](https://huggingface.co/pcunwa)

## 实验性歌手分离

UNMIXX 等按歌手分离的研究模型不属于以上 PyMSS 两声部分离架构；不能把 Karaoke 的主声/其余声部当作固定歌手身份。本次可选研究工具 `RunSingerBenchmark.py` 使用另行获取的 [UNMIXX 源码与检查点](https://github.com/jihoojung0106/unmixx)，仅加载推理所需的原模型模块和独立依赖，不向 Studio 的 Python 环境安装包，也不把不支持的架构假登记成 App 模型。

适配器对 Big7 人声转换为 24 kHz 单声道，以训练使用的四秒窗、87.5% 重叠和 Hann 拼接做完整歌曲推理，使用相邻重叠波形的相关性尝试保持输出顺序。输出在试听工程中标为歌手 A/B；多人齐唱、顺序切换、单人片段都可能造成混淆，不能视为稳定角色分轨。原输出及换序/低置信接缝记录保存在研究目录；44.1 kHz 双声道试听版本只是重采样与复制单声道，不恢复原始立体声信息。

该研究工具需要自行准备 `runtime/pymss/experiments/unmixx/`、其 `ckpt/best.ckpt` 和独立依赖目录 `runtime/pymss/experiments/deps/`，不属于一键推荐模型下载。没有这些文件时，普通 PyMSS 和旧 MSST 工作流不受影响。
