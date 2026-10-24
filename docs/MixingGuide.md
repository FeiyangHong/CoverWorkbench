# 混音指南 / Mixing guide

在工作台顶部选择 **混音指南**。新安装即能使用，无需先导入歌曲。也可以打开独立页面：<http://127.0.0.1:8765/mix-guide/index.html>，放在 Studio One 旁边对照。

## 如何使用

1. 在左侧搜索或选择声音问题，例如“混响拖尾太长”“回声重复太久”“人声闷”。支持空间、延迟、音色和动态四类目标。
2. 阅读对应的 Studio One 操作路径、建议动作、试调起点，以及调整后应该听什么变化。
3. 默认对照清晰的 SVG 控件教学图。点击编号或参数卡查看说明；切换“实拍局部对照”可核对实际界面，局部截图按原始像素限制尺寸。
4. 用“完整界面”按需打开原始截图；100% 对应原始像素，继续放大不增加截图细节。支持滚动和 Esc 关闭。手动浏览其他插件后，可以回到目标图示。
5. 在“先听一听”中播放演示，同一时间线切换 A/B，试听旋钮变化。再在 Studio One 中完成实际调整。指南不会读取或写入 Song、SVP 或插件参数。

当前包含 18 个问题入口、5 个插件的本机截图，以及一张单独标明的 Studio One 插入／发送／返回路由示意图。数值是练习起点，不代表对某首歌曲试听后的结论。

## 前后试听

- 提供干声／混响、长尾／短尾、干声／回声、长反馈／短反馈，以及 EQ 对比。
- A/B 共用播放位置，切换时使用短交叉淡化。支持暂停、回到开头、拖动进度、循环和独立音量。
- 调节尾音时间、预延迟、效果量、延迟间隔、反馈、EQ 频率／增益／Q。EQ 提供 Bell 与 High Shelf；空气感与低中频问题会载入相应的起始频段。
- 默认使用代码生成的原创合成哼唱或拨弦，无歌曲、歌词、录音或声库。可选择本地短音频，仅在浏览器内解码，不上传、不保存；限制 50 MB，使用开头最多 10 秒，并留出最多 4 秒效果尾音。
- 示例采用通用 Web Audio 卷积混响、延迟和 Biquad EQ，**不是 FabFilter 插件渲染，也不模拟具体预设**。参数用于理解变化方向，不表示在原插件中会得到相同音色。当前试听覆盖混响、回声和 EQ；动态与齿音仍提供图文指南。
- 音量匹配使用近似 RMS，而非 LUFS；两路共享峰值留量，播放音量默认为 35%。切换工作台页签、隐藏网页或离开页面会暂停教学试听。

## 图示与内容来源

参数含义核对于厂商说明；操作步骤、问题分类、中文解释、交互标注与路由示意由 CoverWorkbench 整理。

| Plugin | Reference |
| --- | --- |
| Pro-R 2 | [Main controls](https://www.fabfilter.com/help/pro-r/using/maincontrols) |
| Timeless 3 | [Delay controls](https://www.fabfilter.com/help/timeless/using/delaycontrols) |
| Pro-Q 3 | [Version 3 manual](https://www.fabfilter.com/help/ffproq3-manual.pdf) |
| Pro-C 2 | [Version 2 manual](https://www.fabfilter.com/downloads/pdf/help/ffproc2-manual.pdf) |
| Pro-DS | [Basic controls](https://www.fabfilter.com/help/pro-ds/using/basiccontrols) |

截图只保留插件本体，已裁去宿主标题、歌曲名称、音轨名称、文件路径与桌面区域。图中的参数、频谱和电平仅用于展示界面，不是推荐预设或音频质量证明。不同版本、界面缩放或频点选择会改变控件位置，应同时对照英文名称。

FabFilter 的界面、标识和产品名称归各自权利人所有，不属于本项目原创素材的 MIT 授权范围。仓库不包含插件程序或授权信息。详见 [第三方声明](../THIRD_PARTY_NOTICES.md)。

## 维护与验证

页面、浏览器音频处理和图示位于 `app/static/mix-guide/`；应用内和独立页面共用同一份内容。新增或更换截图时必须重新核对裁剪范围和百分比标记坐标。原创矢量控件图可通过 `python tools/render_mix_controls.py` 生成；对应坐标保存在 `diagrams/positions.json`，修改布局时需同时更新 `guide.js` 的 `clearPositions`。

浏览器验证包含空工作区入口、所有图示加载、参数联动、搜索／分类、放大／Esc 与焦点恢复、移动端溢出，大屏实拍图不拉伸、本地音频不上传、A/B 保持时间线、效果差异／尾音能量／音量匹配／峰值留量，以及教学操作不发送工程修改请求：

```powershell
npm ci
$env:CW_BROWSER_CHANNEL='msedge'
python tests/portable-smoke.py --browser
```

CI 使用 Playwright Chromium；Edge 选项只用于本机已有浏览器。指南的说明与插图可离线加载，打开“官方参数说明”链接时才访问外部网站。
