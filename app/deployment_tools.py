"""Bounded, redacted diagnostics and reversible source-only ZIP updates."""
from pathlib import Path,PurePosixPath
import hashlib,importlib.util,json,os,platform,shutil,subprocess,sys,tempfile,time,zipfile,threading
from core import ROOT,save_json,read_json,sha
import settings,lifecycle

SOURCE_DIRS={'app','tools','docs','integrations','assets','.github','.githooks'}
ROOT_FILES={'README.md','README.en.md','LICENSE','NOTICE','AGENTS.md','CONTRIBUTING.md','Setup.ps1','Start.ps1','Start.vbs','Stop.ps1','Desktop.ps1','Desktop.vbs','requirements-lyrics.txt','requirements-video.txt','requirements-desktop.txt','package.json','package-lock.json','.gitignore','.gitattributes'}
PRIVATE={'.svp','.song','.wav','.flac','.mp3','.mp4','.mkv','.webm','.lrc','.srt','.ass','.ckpt','.pt','.pth','.safetensors','.exe','.dll'}
UPDATE_LOCK=threading.RLock()

def no_links(path):
    if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in [path,*path.parents]):raise ValueError('源码或备份路径含目录链接，拒绝更新')

def diagnostic(folder):
    rows=[]
    def add(name,state,message,fix=''):rows.append(dict(name=name,state=state,message=message,fix=fix))
    add('Python','ok',platform.python_version())
    try:
        settings.load();add('个人设置','ok','设置文件可读取')
    except (ValueError,OSError):add('个人设置','error','设置文件无法读取','保留原配置，检查 JSON 格式或恢复备份')
    for name in ['ffmpeg','ffprobe','sv1','sv2','studioOne']:
        try:path=settings.executable(name,False)
        except (ValueError,OSError):path=''
        if not path:add(name,'warning','尚未检测到','在环境设置选择程序；只影响对应功能');continue
        if name in ('ffmpeg','ffprobe'):
            try:
                p=subprocess.run([path,'-version'],capture_output=True,timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));line=p.stdout.decode('utf-8',errors='replace').splitlines()[0];add(name,'ok' if p.returncode==0 else 'error',line[:160])
                if name=='ffmpeg':
                    filters=subprocess.run([path,'-hide_banner','-filters'],capture_output=True,timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));ass=b' ass ' in filters.stdout;add('字幕渲染 libass','ok' if ass else 'error','可用' if ass else '未检测到','配置含 libass 的 FFmpeg')
            except (OSError,subprocess.SubprocessError,IndexError):add(name,'error','程序无法正常启动','重新选择可用程序')
        else:add(name,'ok','已配置可用程序文件')
    for package,label in [('pykakasi','日语读音'),('yt_dlp','视频下载'),('pedalboard','本机插件试听'),('webview','桌面窗口')]:
        available=importlib.util.find_spec(package) is not None;add(label,'ok' if available else 'warning','已安装' if available else '未安装可选组件','查看部署指南中的对应安装步骤')
    try:
        (ROOT/'runtime').mkdir(exist_ok=True)
        with tempfile.TemporaryFile(dir=ROOT/'runtime') as stream:stream.write(b'workspace test')
        add('工作区写入','ok','运行目录可写')
    except OSError:add('工作区写入','error','运行目录不可写','将完整工作台移到有写入权限的目录')
    report={'created':time.time(),'platform':sys.platform,'architecture':platform.machine(),'desktopPackaged':bool(getattr(sys,'frozen',False)),'checks':rows,'privacy':'不包含个人设置、完整路径、歌曲名、歌词、媒体或原始日志。可分享前自行查看。'}
    folder=Path(folder);save_json(folder/'Environment Report.json',report)
    with zipfile.ZipFile(folder/'Diagnostic Report.zip','w',zipfile.ZIP_DEFLATED) as z:z.writestr('Environment Report.json',json.dumps(report,ensure_ascii=False,indent=2))
    return report

def approved(name):
    p=PurePosixPath(name)
    return bool(p.parts and '..' not in p.parts and not p.is_absolute() and '\\' not in name and not any('.local.' in x for x in p.parts) and p.suffix.lower() not in PRIVATE and (p.parts[0] in SOURCE_DIRS or len(p.parts)==1 and name in ROOT_FILES or p.parts[0]=='config' and p.name.endswith('.example.json')))

def idle():
    state=lifecycle.status()
    if any(state.get(k,0) for k in ['videos','separations','auditions','deliveries','maintenance','studioTasks']):raise ValueError('请先等待后台任务结束，再更新程序')

def updates():
    base=ROOT/'work/Source Updates'
    return [dict(read_json(p),name=p.parent.name) for p in sorted(base.glob('Update */Manifest.json'),reverse=True)] if base.exists() else []

def apply(body):
    with UPDATE_LOCK:return _apply(body)

def _apply(body):
    idle()
    if body.get('confirm') is not True:raise ValueError('请先保存编辑并明确确认更新源码')
    if getattr(sys,'frozen',False):raise ValueError('桌面便携版请下载新版到新目录，再用 --workspace 指向现有工作区；不要覆盖运行中的 EXE')
    import video_project
    source=video_project.local(body.get('path'),{'.zip'});base=ROOT/'work/Source Updates';base.mkdir(parents=True,exist_ok=True);number=1
    while (base/f'Update {number:03}').exists():number+=1
    folder=base/f'Update {number:03}';folder.mkdir();incoming=folder/'Incoming';incoming.mkdir();records=[]
    with zipfile.ZipFile(source) as z:
        entries=[e for e in z.infolist() if not e.is_dir()]
        if len(entries)>10000 or sum(e.file_size for e in entries)>100_000_000:raise ValueError('更新包内容过大')
        names=[e.filename for e in entries];prefix='' if 'app/server.py' in names else (names[0].split('/')[0]+'/' if names else '')
        normalized=[n[len(prefix):] if n.startswith(prefix) else '' for n in names]
        if 'app/server.py' not in normalized or 'LICENSE' not in normalized:raise ValueError('请选择 CoverWorkbench 源码 ZIP')
        if len({n.casefold() for n in normalized})!=len(normalized):raise ValueError('更新包存在重复路径')
        for e,name in zip(entries,normalized):
            if not approved(name):continue
            from windows_names import component
            for part in PurePosixPath(name).parts:component(part,'更新包路径')
            if ((e.external_attr>>16)&0o170000)==0o120000:raise ValueError('更新包不允许文件链接')
            target=ROOT/name
            no_links(target)
            if not target.resolve().is_relative_to(ROOT.resolve()):raise ValueError('更新路径指向工作区外部')
            data=z.read(e)
            if name.endswith('.cwmix'):
                from mix_bundle import validate
                validate(data)
            temp=incoming/name;temp.parent.mkdir(parents=True,exist_ok=True);temp.write_bytes(data)
            if target.is_file() and sha(target)==sha(temp):continue
            backup=folder/'Previous'/name
            if target.exists():backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,backup)
            records.append({'name':name,'before':sha(target) if target.is_file() else None,'after':sha(temp)})
    manifest={'created':time.time(),'status':'applying','files':records};save_json(folder/'Manifest.json',manifest)
    try:
        for r in records:
            target=ROOT/r['name'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(incoming/r['name'],target)
        manifest['status']='applied';save_json(folder/'Manifest.json',manifest)
    except Exception:
        for r in records:
            target=ROOT/r['name'];prior=folder/'Previous'/r['name']
            if prior.is_file():shutil.copy2(prior,target)
            elif target.is_file() and sha(target)==r['after']:target.unlink()
        manifest['status']='failed-restored';save_json(folder/'Manifest.json',manifest);raise
    return {'name':folder.name,'changed':len(records),'message':'源码已更新，个人工程与配置保留。请彻底退出后重新启动。'}

def rollback(body):
    with UPDATE_LOCK:return _rollback(body)

def _rollback(body):
    idle();name=body.get('name');entry=next((r for r in updates() if r['name']==name),None)
    if not entry or entry['status']!='applied' or body.get('confirm') is not True:raise ValueError('请选择已应用的更新并确认回退')
    folder=ROOT/'work/Source Updates'/name
    no_links(folder)
    for r in entry['files']:
        target=ROOT/r['name']
        no_links(target)
        if not approved(r['name']) or not target.resolve().is_relative_to(ROOT.resolve()) or not target.is_file() or sha(target)!=r['after']:raise ValueError('更新后源码又被修改，拒绝覆盖；备份保留')
        if r['before'] and (not (folder/'Previous'/r['name']).is_file() or sha(folder/'Previous'/r['name'])!=r['before']):raise ValueError('回退备份缺失或已改变')
    for r in entry['files']:
        target=ROOT/r['name'];prior=folder/'Previous'/r['name']
        if r['before']:shutil.copy2(prior,target)
        else:target.unlink()
    entry['status']='rolled-back';entry.pop('name',None);save_json(folder/'Manifest.json',entry)
    return {'message':'程序源码已回退，个人工程与配置保留；请彻底退出后重新启动。'}
