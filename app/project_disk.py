"""Measured cache cleanup with a local recovery archive and explicit permanent purge."""
from pathlib import Path
import hashlib,json,shutil,threading,time,uuid,zipfile
from core import ROOT,read_json,save_json
import project_context as contexts
import video_project,video_jobs,video_edit

LOCK=threading.RLock();PLANS={}
ARCHIVE=ROOT/'work/Recoverable Cleanup'


def safe_tree(path):
    if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('目录包含链接，无法按缓存处理：'+str(path))
    if path.is_file():return [path]
    files=[]
    for child in path.iterdir():
        files.extend(safe_tree(child))
    return files


def describe(path):
    for parent in [path,*path.parents]:
        if parent.is_symlink() or getattr(parent,'is_junction',lambda:False)():raise ValueError('缓存路径包含目录链接，拒绝处理')
    files=safe_tree(path);rows=[(str(p.relative_to(path)) if path.is_dir() else p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in files]
    return {'bytes':sum(r[1] for r in rows),'files':len(rows),'fingerprint':hashlib.sha256(json.dumps(sorted(rows)).encode()).hexdigest()}


def busy():
    import lifecycle
    state=lifecycle.status()
    if any(state[k] for k in ['videos','separations','auditions','deliveries']) or state.get('maintenance',0) or state.get('studioTasks',0) or state.get('supportTasks',0):raise ValueError('请先等待后台任务完成，再进行磁盘操作')


def allowed(context):
    return [ROOT/'runtime/video-preview',ROOT/'runtime/video-captions',*[video_project.folder(v['id'])/'Cache' for v in context['videos']],*[video_project.output_folder(v['id'])/'Jobs' for v in context['videos']]]


def protected(context):
    paths=[]
    import project_assets,project_packages
    index=ROOT/'config/projects.json'
    for p in read_json(index) if index.exists() else []:
        items=project_assets.status(p['id'])['assets']
        paths += [Path(a['path']).resolve() for a in items.values() if a.get('path')]
        for key in ['svp','song']:
            if items[key].get('exists'):
                try:
                    queue=[Path(items[key]['path'])];seen=set()
                    while queue:
                        native=queue.pop().resolve()
                        if native in seen or not native.is_file():continue
                        seen.add(native);refs=list(project_packages.native_refs(native));paths.extend(refs)
                        queue.extend(p for p in refs if p.suffix.lower() in ('.svp','.song'))
                except (ValueError,OSError,zipfile.BadZipFile):pass
    # Shared caches must not remove inputs registered by another song or video.
    for v in video_project.listing():
        doc=video_project.load(v['id']);paths += [Path(doc[k]).resolve() for k in ['video','audio'] if doc.get(k)]
        paths += [Path(a['path']).resolve() for a in (doc.get('composition') or {}).get('assets',[])]
        paths += [Path(a['path']).resolve() for a in video_edit.library(v['id'])]
    return paths


def scan(scope,ident):
    context=contexts.get(scope,ident);root=context['root'];entries=[];protected_paths=protected(context)
    def add(path,label):
        if not path.exists() or any(p==path.resolve() or p.is_relative_to(path.resolve()) for p in protected_paths):return
        details=describe(path)
        if any(p.suffix.lower() in ('.svp','.song','.s5p') for p in safe_tree(path)):return
        entries.append({'id':str(len(entries)+1),'label':label,'path':str(path.resolve()),**details})
    for directory,label in [(ROOT/'runtime/video-preview','共享音视频试听缓存'),(ROOT/'runtime/video-captions','共享字幕排版缓存')]:
        if directory.exists():
            for i,p in enumerate(sorted(directory.iterdir())):
                if p.is_dir():add(p,f'{label} {i+1:03}')
    for video in context['videos']:
        folder=video_project.folder(video['id'])
        for name in ['Filmstrips','Proxies','Thumbnails']:
            add(folder/'Cache'/name,video['name']+' · '+{'Filmstrips':'连续缩略图','Proxies':'网页代理','Thumbnails':'封面缩略图'}[name])
        for job in video_jobs.history(video['id']):
            if job['kind']=='preview' and job['status'] not in ('queued','running'):
                add(Path(job['folder']),video['name']+f" · 区间预览 {job.get('version') or ''}")
    # Count once, without traversing reparse points or including unrelated songs.
    totals={'source':0,'cache':0,'outputs':0,'history':0,'other':0}
    for file in safe_tree(root):
        parts={p.lower() for p in file.relative_to(root).parts};category='cache' if 'cache' in parts or 'jobs' in parts else 'outputs' if 'exports' in parts or 'mixdown' in parts else 'history' if 'history' in parts or 'snapshots' in parts or 'recovery' in parts else 'source' if file.suffix.lower() in {'.wav','.flac','.mp3','.mp4','.mkv','.mov','.webm','.png','.jpg','.svp','.song'} else 'other'
        totals[category]+=file.stat().st_size
    token=uuid.uuid4().hex
    with LOCK:
        while len(PLANS)>=10:PLANS.pop(next(iter(PLANS)))
        PLANS[token]={'scope':scope,'ident':ident,'entries':entries,'created':time.time()}
    archives=[]
    if ARCHIVE.exists():
        for file in ARCHIVE.glob('Batch */Manifest.json'):
            doc=read_json(file)
            if doc['scope']==scope and doc['ident']==ident:archives.append({'name':file.parent.name,'status':doc['status'],'bytes':sum(e['bytes'] for e in doc['entries']),'created':doc['created']})
    backups=[]
    for folder in (ROOT/'work').glob('Project Organization Backup *'):
        backups.append({'name':folder.name,'path':str(folder),'bytes':describe(folder)['bytes']})
    return {'token':token,'root':str(root),'totals':totals,'candidates':entries,'archives':archives,'backups':backups}


def archive(scope,ident,body):
    busy();context=contexts.get(scope,ident)
    with LOCK:
        plan=PLANS.get(body.get('token'));ids=body.get('entries',[])
        if not plan or plan['scope']!=scope or plan['ident']!=ident or time.time()-plan['created']>1800:raise ValueError('清理预览已过期，请重新扫描')
        if not isinstance(ids,list) or not ids or len(set(ids))!=len(ids):raise ValueError('请勾选要隔离的缓存')
        selected=[copy for copy in plan['entries'] if copy['id'] in ids]
        if len(selected)!=len(ids):raise ValueError('缓存选择无效')
        protected_paths=protected(context)
        for item in selected:
            path=Path(item['path']);resolved=path.resolve()
            if not any(resolved!=base.resolve() and resolved.is_relative_to(base.resolve()) for base in allowed(context)) and not any(resolved==video_project.folder(v['id'])/'Cache'/name for v in context['videos'] for name in ['Filmstrips','Proxies','Thumbnails']):raise ValueError('路径不是允许清理的缓存')
            if any(p==resolved or p.is_relative_to(resolved) for p in protected_paths):raise ValueError('缓存已被登记为输入素材，拒绝清理')
            if describe(path)['fingerprint']!=item['fingerprint']:raise ValueError('缓存内容已经变化，请重新扫描')
        ARCHIVE.mkdir(parents=True,exist_ok=True);number=1
        while (ARCHIVE/f'Batch {number:03}').exists():number+=1
        folder=ARCHIVE/f'Batch {number:03}';folder.mkdir()
        entries=[dict(item,target=str(folder/f'Item {i+1:03}'/Path(item['path']).name)) for i,item in enumerate(selected)]
        doc={'scope':scope,'ident':ident,'created':time.time(),'status':'moving','entries':entries};save_json(folder/'Manifest.json',doc)
        moved=[]
        try:
            for item in entries:
                target=Path(item['target']);target.parent.mkdir();Path(item['path']).rename(target);moved.append(item)
            doc['status']='archived';save_json(folder/'Manifest.json',doc)
        except Exception:
            for item in reversed(moved):Path(item['target']).rename(item['path'])
            doc['status']='failed';save_json(folder/'Manifest.json',doc);raise
        PLANS.pop(body['token'],None)
    return {'name':folder.name,'bytes':sum(e['bytes'] for e in entries),'message':'已隔离，可恢复；永久删除后才释放磁盘空间'}


def manage(scope,ident,body):
    busy();context=contexts.get(scope,ident);name=body.get('name','')
    from windows_names import component
    component(name,'清理批次');folder=(ARCHIVE/name).resolve()
    if folder.parent!=ARCHIVE.resolve() or not (folder/'Manifest.json').is_file():raise ValueError('清理批次不存在')
    with LOCK:
        doc=read_json(folder/'Manifest.json')
        for parent in [folder,*folder.parents]:
            if parent.is_symlink() or getattr(parent,'is_junction',lambda:False)():raise ValueError('归档路径包含链接')
        if doc['scope']!=scope or doc['ident']!=ident or doc['created']!=body.get('created') or doc['status'] not in ('archived','moving'):raise ValueError('批次已处理或不属于此工程')
        if any(p==Path(item['target']).resolve() or p.is_relative_to(Path(item['target']).resolve()) for p in protected(context) for item in doc['entries']):raise ValueError('隔离副本已登记为输入素材，不能移动或删除')
        if body.get('action')=='restore':
            for item in doc['entries']:
                if Path(item['target']).exists() and Path(item['path']).exists():raise ValueError('原位置已有重新生成的缓存，不能覆盖；隔离批次保留')
            for item in doc['entries']:
                source=Path(item['target']).resolve();target=Path(item['path']);
                for parent in target.parents:
                    if parent.is_symlink() or getattr(parent,'is_junction',lambda:False)():raise ValueError('原缓存目录包含链接')
                if not source.is_relative_to(folder):raise ValueError('恢复路径无效')
                if not any(target.resolve().is_relative_to(base.resolve()) for base in allowed(context)):raise ValueError('原缓存位置已变化，不能恢复')
                if source.exists():safe_tree(source);target.parent.mkdir(parents=True,exist_ok=True);source.rename(target)
            doc['status']='restored'
        elif body.get('action')=='purge' and body.get('confirm') is True:
            safe_tree(folder)
            # Only validated archive payloads are deleted, never original paths.
            for child in folder.iterdir():
                if child.name=='Manifest.json':continue
                if not child.resolve().is_relative_to(ARCHIVE.resolve()):raise ValueError('清理归档路径无效')
                shutil.rmtree(child) if child.is_dir() else child.unlink()
            doc['status']='purged'
        else:raise ValueError('请明确选择恢复，或确认永久删除')
        save_json(folder/'Manifest.json',doc)
    return {'status':doc['status']}
