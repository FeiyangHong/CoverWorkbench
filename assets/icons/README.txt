CoverWorkbench Desktop Icons

01 cw-signature.ico - 音符（已设为默认桌面图标）
02 cw-vocal.ico - 声波
03 cw-studio.ico - 录音室

桌面快捷方式：%USERPROFILE%/Desktop/CoverWorkbench.lnk
图标目录：<checkout>/assets/icons
启动方式：调用现有 Start.vbs；本地服务未启动时先启动，再打开默认浏览器。

网站中更换：打开工作台右上角「桌面图标」，选择预览卡片，再点击「应用到桌面」。

手工更换图标：右键桌面快捷方式 → 属性 → 更改图标 → 浏览对应 ICO 文件。
也可以运行项目 tools/InstallDesktopShortcut.ps1 -Icon cw-vocal（或 cw-studio / cw-signature）。

每个 ICO 内含 16、20、24、32、40、48、64、96、128、256 像素透明图层。
SVG 是可编辑源文件，PNG 为 1024px 预览。不要删除永久图标目录，快捷方式引用它。
