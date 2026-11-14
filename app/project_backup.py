"""Readable incremental snapshots, collected native dependencies and verified restore."""
from pathlib import Path,PurePosixPath
import json,os,re,shutil,threading,time,zipfile
from core import ROOT,read_json,save_json,sha
import project_packages,project_context,project_tasks
from windows_names import component
LOCK=threading.RLock()

def cross_disk(source,destination):return os.name!='nt' or source.drive.casefold()!=destination.drive.casefold()

def target(value):
    path=Path(str(value).strip().strip('"“”'))
    if not path.is_absolute() or str(path).startswith(('\\\\','//')):raise ValueError('请选择本机备份磁盘的绝对路径')
    path=path.resolve()
    for p in [path,*path.parents]:
        if p.is_symlink() or getattr(p,'is_junction',lambda:False)():raise ValueError('备份路径不允许目录链接')
    if path==ROOT or path.is_relative_to(ROOT) or ROOT.is_relative_to(path):raise ValueError('备份目录必须位于工作区之外的独立目录')
    if not cross_disk(ROOT,path):raise ValueError('跨盘备份请选择与工作区不同的盘符')
    if path==Path(path.anchor):raise ValueError('请选择磁盘中的专用备份文件夹')
    return path

def project_folder(directory,ident):
    context=project_context.get('music',ident);base=target(directory)
    title=component(context['root'].name,'备份工程目录');folder=base/title
    if folder.exists():
        owner=folder/'Owner.json'
        if not owner.is_file() or read_json(owner).get('project')!=ident:raise ValueError('同名备份目录属于其他工程，请选择独立备份目录')
    return folder,context

def listing(directory,ident):
    if not directory:return []
    folder,_=project_folder(directory,ident);rows=[]
    paths=[p for p in folder.glob('Backup */Manifest.json') if re.fullmatch(r'Backup [0-9]{3,}',p.parent.name)]
    for path in sorted(paths,key=lambda p:int(p.parent.name.split()[-1]),reverse=True):
        try:
            d=read_json(path);verification=path.parent/'Verification.json';rows.append({'name':path.parent.name,'created':d['created'],'files':len(d['files']),'changedFiles':d['changedFiles'],'newBytes':d['newBytes'],'totalBytes':d['totalBytes'],'requirements':d['packageManifest']['requirements'],'verification':read_json(verification) if verification.exists() else {}})
        except (OSError,ValueError,KeyError):continue
    return rows

def snapshot(folder,name):
    if not isinstance(name,str) or not re.fullmatch(r'Backup [0-9]{3,}',name):raise ValueError('无效备份版本')
    path=(folder/name).resolve()
    if path.parent!=folder.resolve() or path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('备份版本路径无效')
    doc=read_json(path/'Manifest.json')
    if doc.get('schema')!=1:raise ValueError('不支持的备份格式')
    return path,doc

def stored(folder,record):
    name=record['snapshot'];relative=record['file'];parts=PurePosixPath(relative).parts
    if not re.fullmatch(r'Backup [0-9]{3,}',name) or not parts or PurePosixPath(relative).is_absolute() or '\\' in relative:raise ValueError('备份文件引用无效')
    for p in parts:component(p,'备份文件名')
    path=folder/name/'Files'/Path(*parts)
    if not path.resolve().is_relative_to(folder.resolve()):raise ValueError('备份引用越界')
    for p in [path,*path.parents]:
        if p.is_symlink() or getattr(p,'is_junction',lambda:False)():raise ValueError('备份引用含链接')
    return path

def create(job,directory):
    with LOCK:
        folder,context=project_folder(directory,job['project']);folder.mkdir(parents=True,exist_ok=True)
        save_json(folder/'Owner.json',{'project':job['project'],'title':context['title'],'schema':1})
        prior=listing(directory,job['project']);old=snapshot(folder,prior[0]['name'])[1] if prior else {'files':{}}
        stage=None;working=None
        try:
            staged=project_packages.pack({**job,'scope':'music','snapshotOnly':True});stage=Path(staged['stage']);manifest=staged['manifest']
            total=sum(d['bytes'] for d in manifest['files'].values())
            needed=sum(d['bytes'] for name,d in manifest['files'].items() if old['files'].get(name,{}).get('sha256')!=d['sha256'])
            if shutil.disk_usage(folder).free<needed+64*1024*1024:raise ValueError('备份盘可用空间不足')
            number=1
            while (folder/f'Backup {number:03}').exists() or (folder/f'Preparing Backup {number:03}').exists():number+=1
            name=f'Backup {number:03}';working=folder/f'Preparing {name}';working.mkdir();files={};changed=0
            for i,(relative,info) in enumerate(manifest['files'].items()):
                project_tasks.check(job);previous=old['files'].get(relative)
                if previous and previous['sha256']==info['sha256'] and stored(folder,previous).is_file() and sha(stored(folder,previous))==info['sha256']:files[relative]=previous
                else:
                    dest=working/'Files'/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(stage/relative,dest)
                    if sha(dest)!=info['sha256']:raise ValueError('备份复制校验失败：'+relative)
                    files[relative]={**info,'snapshot':name,'file':relative};changed+=1
                project_tasks.update(job,stage=f'增量备份 · {i+1}/{len(manifest["files"])}',progress=55+int(40*(i+1)/max(1,len(manifest['files']))))
            doc={'schema':1,'project':job['project'],'created':time.time(),'files':files,'packageManifest':manifest,'changedFiles':changed,'newBytes':sum(r['bytes'] for r in files.values() if r['snapshot']==name),'totalBytes':total}
            save_json(working/'Manifest.json',doc);working.rename(folder/name)
            return {'name':name,'folder':str(folder/name),'files':len(files),'changedFiles':changed,'newBytes':doc['newBytes'],'totalBytes':total,'requirements':manifest['requirements'],'warnings':manifest['warnings']}
        finally:
            if stage is not None:project_packages.remove_stage(stage,Path(job['folder']))
            # A failed, unpublished snapshot is scratch data, not a recovery version.
            if working is not None and working.exists():
                if working.parent.resolve()!=folder.resolve() or not re.fullmatch(r'Preparing Backup [0-9]{3,}',working.name) or working.is_symlink() or getattr(working,'is_junction',lambda:False)():
                    raise ValueError('临时备份目录无效，拒绝清理')
                shutil.rmtree(working)


def verify(job,directory,name):
    folder,_=project_folder(directory,job['project']);path,doc=snapshot(folder,name)
    for i,(relative,record) in enumerate(doc['files'].items()):
        project_tasks.check(job);file=stored(folder,record)
        if not file.is_file() or file.stat().st_size!=record['bytes'] or sha(file)!=record['sha256']:raise ValueError('备份校验失败：'+relative)
        if doc['packageManifest']['files'].get(relative)!={k:record[k] for k in ('bytes','sha256')}:raise ValueError('备份清单不一致')
        project_tasks.update(job,stage=f'验证备份 · {i+1}/{len(doc["files"])}',progress=int((i+1)/max(1,len(doc['files']))*80))
    if set(doc['files'])!=set(doc['packageManifest']['files']):raise ValueError('备份文件清单缺失')
    return {'name':name,'files':len(doc['files']),'verified':True,'requirements':doc['packageManifest']['requirements']}

def restore(job,directory,name,new_name):
    verify(job,directory,name);folder,_=project_folder(directory,job['project']);_,doc=snapshot(folder,name)
    output=Path(job['folder'])/'Restore.cwpack'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_STORED) as z:
        z.writestr('Manifest.json',json.dumps(doc['packageManifest'],ensure_ascii=False))
        for relative,record in doc['files'].items():project_tasks.check(job);z.write(stored(folder,record),'Project/'+relative)
    # Existing importer allocates a fresh identity/directory and relocates native references.
    try:
        result=project_packages.import_package(job,{'path':str(output),'name':component(new_name,'恢复工程名称')})
        save_json(folder/name/'Verification.json',{'restoreCheckedAt':time.time(),'restoreVerified':True,'restoredRoot':result['root']})
        return result
    except Exception as error:
        save_json(folder/name/'Verification.json',{'restoreCheckedAt':time.time(),'restoreVerified':False,'error':str(error)})
        raise
