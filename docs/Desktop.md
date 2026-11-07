# Windows 桌面版

桌面版提供独立的 Windows 窗口，使用与网页相同的工程、设置和后台接口。它不复制另一套歌曲库，也不代替 SV 或 Studio One。窗口宿主采用 [pywebview](https://pywebview.flowrl.com/guide/usage.html) 与 Windows [WebView2](https://developer.microsoft.com/microsoft-edge/webview2/)。

## 便携 EXE

将完整 `CoverWorkbench-Windows-x64.zip` 解压到可写目录，运行其中的 `CoverWorkbench.exe`。保留 `_internal`、`app`、`assets` 等随附目录；不要只取出 EXE。便携包包含核心 Python 运行环境，无需另外安装 Python；WebView2 Runtime、FFmpeg、SV、Studio One、声库与商业插件由本机提供。

默认把工作区放在 EXE 所在目录。要继续使用已有源码工作区，创建快捷方式或运行：

```powershell
.\CoverWorkbench.exe --workspace 'D:\Music\CoverWorkbench'
```

同一工作区的网页后台已启动时，桌面版会复用它；发现端口属于其他工作区会拒绝连接。旧版后台需先保存编辑、彻底退出，再启动新版。已有工作区含 `.venv/Scripts/python.exe` 时，桌面版优先用该环境运行后台，保留你已安装的可选歌词、插件试听等组件。

便携包核心运行时不打包 pykakasi、Pedalboard 或商业插件。需要这些可选引擎时，可在对应源码工作区运行 `Setup.ps1 -WithLyrics` 或 `tools/InstallNativeAudio.ps1`，再重启桌面版；也可继续使用已经配置好的本机工作区。程序自身源码仍按 MIT 提供，随包第三方运行库声明见 `Third Party Notices/`。

## 从源码打开桌面窗口

```powershell
.\Setup.ps1 -WithDesktop
.\Desktop.ps1
```

也可双击 `Desktop.vbs` 静默打开。网页入口 `Start.vbs` 保持可用。原有浏览器桌面快捷方式保留；桌面应用可建立独立快捷方式：

```powershell
.\tools\InstallDesktopAppShortcut.ps1 -Executable 'D:\Apps\CoverWorkbench\CoverWorkbench.exe' -Workspace 'D:\Music\CoverWorkbench'
```

## 窗口与后台的关闭

点击窗口右上角关闭按钮时，有三个选择：

- **继续编辑**：留在当前窗口。
- **仅关闭窗口 · 保留后台**：先保存当前视频编辑，关闭窗口；下载、分离与渲染继续运行，浏览器仍可连接。
- **保存并彻底退出**：先保存视频，再进入统一的后台退出确认。后台有任务时需要等待或到制作助手取消，绝不强制结束创作软件。

保存失败时窗口保留。SV、Studio One 内尚未保存的编辑需要在各自软件中保存。网页端彻底退出同一个后台后，桌面窗口也会结束。桌面和普通浏览器各有自己的界面偏好与浏览器本地存储；已同步的服务器草稿、工程和成品共用，跨窗口保存有修订冲突检查。

## 自行构建与升级

构建需要 Windows、Python 3.11+ 和 Git 源码检出：

```powershell
.\tools\BuildDesktop.ps1
```

构建使用独立的 `work/Desktop Build Env/`，输出到 `dist/desktop/`，提供 ZIP 与 `SHA256SUMS.txt`。构建只收集公开源码、产品资源和所需运行库，排除歌曲、工程、个人配置、模型和私有预设。输出目录已有个人工作区时会拒绝覆盖；可使用 `-Output` 选择新目录。源码仓库也提供手动运行的 **Windows desktop portable build** GitHub Actions 工作流。

便携版升级请解压到新目录，再继续指定原工作区；不要覆盖正在运行的 EXE。源码工作区可用制作助手的源码 ZIP 更新功能，先备份、再更新，有修改冲突时拒绝回退覆盖；更新后应彻底退出并重新启动。桌面外壳升级与工作区源码更新是两个明确步骤，不会静默替换正在运行的应用。
