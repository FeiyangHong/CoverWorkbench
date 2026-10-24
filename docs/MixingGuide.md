# 混音指南 / Mixing guide

在工作台顶部选择 **混音指南**。新安装即能使用，无需先导入歌曲。也可以打开独立页面：<http://127.0.0.1:8765/mix-guide/index.html>，放在 Studio One 旁边对照。

## 如何使用

1. 在左侧搜索或选择声音问题，例如“混响拖尾太长”“回声重复太久”“人声闷”。支持空间、延迟、音色和动态四类目标。
2. 阅读对应的 Studio One 操作路径、建议动作、试调起点，以及调整后应该听什么变化。
3. 对照右侧插件实拍图。点击图上的编号或下方参数按钮，查看英文旋钮名与中文说明。
4. 用“放大图示”查看细节；支持 100–250% 放大和滚动，按 Esc 关闭。手动浏览其他插件后，可以回到当前目标的图示。
5. 在 Studio One 中完成调整。指南中的按钮只切换教学内容，不会读取或写入 Song、SVP 或插件参数。

当前包含 18 个问题入口、5 个插件的本机截图，以及一张单独标明的 Studio One 插入／发送／返回路由示意图。数值是练习起点，不代表对某首歌曲试听后的结论。

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

页面和图示位于 `app/static/mix-guide/`；应用内和独立页面共用同一份内容。新增或更换截图时必须重新核对裁剪范围和百分比标记坐标。

浏览器验证包含空工作区入口、所有图示加载、参数联动、搜索／分类、放大／Esc 与焦点恢复、移动端溢出，以及教学操作不发送工程修改请求：

```powershell
npm ci
$env:CW_BROWSER_CHANNEL='msedge'
python tests/portable-smoke.py --browser
```

CI 使用 Playwright Chromium；Edge 选项只用于本机已有浏览器。指南的说明与插图可离线加载，打开“官方参数说明”链接时才访问外部网站。
