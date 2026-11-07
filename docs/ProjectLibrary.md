# 工程排序、歌词文件与旧目录整理

音乐与视频工程列表均提供最近修改、创建时间（升序 / 降序）、名称和自定义排序。拖动工程可保存手动顺序，也可聚焦工程后按 Alt + ↑ / ↓。排序保存在本机 `config/project-library.local.json`，刷新或重启后保留。最近修改读取已保存的工作台记录和已登记的原生工作文件；不扫描整棵媒体目录。旧工程没有精确创建字段时使用文件记录回退。

## 歌词下载与文件名

「歌词素材」下载并整理后，「歌词文件 · 下载与保存位置」显示可下载文件、完整项目保存目录和「打开歌词文件夹」。带时间的歌词提供原文 LRC、已有译文 LRC、罗马音 LRC、双语 LRC，以及原文＋罗马音 TXT；未提供译文时不会编造，无时间歌词导出 TXT。译文无时间且不能对应各行时仅提供原始译文 TXT，不编造双语时间。

浏览器下载副本的目录由浏览器设置决定；工作台保存的版本始终留在本曲 `exports/lyrics`。

内部记录为 `working/lyrics/Lyrics 001/Source.json` 与 `Lines.json`，读音修订为 `Reading 001.json`；对外文件例如 `Artist - Song - Lyrics 001 - Original.lrc`、`Artist - Song - Lyrics 001 - Bilingual.lrc`。每次整理或修订递增版本，保留之前文件。来源原文独立保存，罗马音、译文修订会生成新的下载文件，不写回 SV。

## 历史目录迁移

先保存草稿并彻底退出工作台。预览计划：

```powershell
python tools/organize_projects.py
```

核对归属后明确执行：

```powershell
python tools/organize_projects.py --apply
```

脚本把旧公共 `projects/studio-one`、`projects/video` 的实际工程归入歌曲目录；宿主验证工程收纳到 `work/Legacy Studio One Checks`。它结构化更新 Song 的 XML / SV 插件链接与 SVP、视频、任务和素材索引，其他插件状态不重建。已保存的字幕、样式和对齐值保留。

原目录与配置归档在 `work/Project Organization Backup 001` 等可读目录，附计划和哈希清单。失败会尝试恢复登记与歌词原件，并保留备份及失败记录，不能不核对就重复执行。目标已存在或源目录包含链接时停止，避免覆盖。未登记的外部歌曲原工程不会移动。后台 8765 服务仍在运行时拒绝迁移。

新建项目默认目录：

```text
projects/Artist - Song/
  working/lyrics/Lyrics 001/
  exports/lyrics/
  studio-one/Song/
  video/Song Video/
```

独立视频使用 `projects/<视频工程>/video/<视频工程>/`；其索引位于忽略的 `data/video-folders.local.json`。旧 `.folders.json` 可兼容读取，但新工程不会再创建公共 `projects/video`。Studio One 的工作台预选位置也归入具名歌曲目录，仍可明确选择原生 Songs 或自定义输出父目录。
