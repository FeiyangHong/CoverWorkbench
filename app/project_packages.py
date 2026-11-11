"""Portable saved projects with collected dependencies, verified files and fresh identities."""
from pathlib import Path,PurePosixPath
from urllib.parse import urlsplit,unquote
import copy,hashlib,html,io,json,os,re,shutil,tempfile,uuid,zipfile
from core import ROOT,read_json,save_json,sha,parse_svp,audit
from windows_names import component,generated
import project_context as contexts
import project_tasks as tasks
import project_assets,workspaces,video_project,video_edit,daw,asset_storage,relocation,media_names

SCHEMA=1
MEDIA={'.wav','.flac','.mp3','.m4a','.aif','.aiff','.ogg','.mp4','.mkv','.webm','.mov','.avi','.png','.jpg','.jpeg','.webp','.svp','.song','.srt','.ass','.lrc','.txt','.preset','.vstpreset','.envelopex'}
EXCLUDE={'cache','jobs','tasks','trash','recovery','modelhub','models','.git','__pycache__','.venv','node_modules'}
REF_KEYS={'path','filename','filePath','original','preview','svp','managedSVP','working','sv2Working','song','sourceSVP','sourceAudio','audio','video','file','snapshot','sourceFile','recordFile'}


def package_path(value):return video_project.local(value,{'.cwpack','.zip'})


def walk(path,relative=Path()):
    if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('工程包含目录链接，请先归集素材：'+str(path))
    if path.is_file():
        if not path.name.endswith(('.tmp','.partial')) and '.rendering.' not in path.name:yield path,relative
    else:
        for child in sorted(path.iterdir()):
            if child.name.casefold() not in EXCLUDE:yield from walk(child,relative/child.name)


def reference(value,base):
    if not isinstance(value,str) or not value or value.startswith(('http:','https:','media:')):return None
    try:
        clean=value.replace('\\\\','\\')
        if not clean.startswith('file:') and not Path(clean).is_absolute():return None
        path=asset_storage.local_reference(clean,base)
        return path if path.suffix.lower() in MEDIA else None
    except ValueError:return None


def json_refs(doc,base):
    if isinstance(doc,dict):
        for key,value in doc.items():
            if key in REF_KEYS:
                path=reference(value,base)
                if path:yield path
            yield from json_refs(value,base)
    elif isinstance(doc,list):
        for value in doc:yield from json_refs(value,base)


def native_refs(path):
    if path.suffix.lower()=='.svp':yield from asset_storage.sv_references(read_json(path),path.parent)
    elif path.suffix.lower()=='.song':
        with zipfile.ZipFile(path) as z:
            names=set(z.namelist())
            for name in names:
                data=z.read(name)
                if name.endswith('.xml'):
                    for value in re.findall(r'''\burl\s*=\s*["']([^"']*)["']''',data.decode('utf-8-sig')):
                        resolved=song_ref(value,path.parent,names)
                        if resolved and resolved.suffix.lower() in MEDIA:yield resolved
                elif name.endswith('.vstpreset') and data[:4]==b'VST3' and data[8:40] in asset_storage.SV_IDS:
                    for tag,payload in daw.chunks(data):
                        if tag==b'Comp':
                            state,_=json.JSONDecoder().raw_decode(payload.decode());value=state.get('projectPath')
                            if value:yield asset_storage.local_reference(value.replace('\\\\','\\'),path.parent)


def song_ref(value,base,names):
    value=html.unescape(value);parsed=urlsplit(value)
    if parsed.scheme=='media':
        name=unquote(parsed.path).lstrip('/')
        if name in names or 'Media/'+name in names:return None
        options=[base/name,base/'Media'/name]
        return next((p.resolve() for p in options if p.is_file()),options[0].resolve())
    if parsed.scheme not in ('file','') or not value:return None
    return asset_storage.local_reference(value,base)


def pack(job):
    context=contexts.get(job['scope'],job['project']);root=context['root'];folder=Path(job['folder']);stage=folder/'Working Copy';stage.mkdir()
    virtual=Path(root.anchor)/'__COVERWORKBENCH_PROJECT__';mapping={str(root):str(virtual)};sources={};copied={};warnings=[]
    metadata={'scope':context['scope'],'title':context['title'],'videos':[]}
    if context['scope']=='music':
        bundle=read_json(ROOT/'data/projects'/(context['id']+'.json'));metadata['bundle']=bundle;metadata['assets']=project_assets.status(context['id'])['assets']
        metadata['link']=None
        from video_links import STORE
        if STORE.exists():metadata['link']=read_json(STORE).get('links',{}).get(context['id'])
        pilot=Path(context['project']['pilot'])
        # These files are authoritative in older adopted music projects.
        authoritative=[pilot/'analysis'/n for n in ['review.json','lyrics-current.json','comparison.json'] if (pilot/'analysis'/n).is_file()]
    else:authoritative=[]
    queue=[];processed={}
    def copy_file(source,target):
        tasks.check(job);digest=sha(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if sha(source)!=digest or sha(target)!=digest:raise ValueError('文件在打包期间变化：'+str(source))
        sources[source]=digest;copied[source]=target
    for source,rel in walk(root):copy_file(source,stage/rel);queue.append((source,False))
    for source in authoritative:copy_file(source,stage/'analysis'/source.name);queue.append((source,False))
    for v in context['videos']:
        video_root=video_project.folder(v['id']);relative=Path() if context['scope']=='video' else video_root.relative_to(root) if video_root.is_relative_to(root) else Path('video')/v['id']
        if not video_root.is_relative_to(root):
            mapping[str(video_root)]=str(virtual/relative)
            for source,rel in walk(video_root):copy_file(source,stage/relative/rel);queue.append((source,False))
        metadata['videos'].append({'id':v['id'],'directory':relative.as_posix()})
        doc=video_project.load(v['id'])
        for key in ['audio','video']:
            if doc.get(key) and not (key=='audio' and doc.get('audioSource')=='video'):queue.append((Path(doc[key]),True))
        for a in (doc.get('composition') or {}).get('assets',[]):queue.append((Path(a['path']),True))
        for a in video_edit.library(v['id']):queue.append((Path(a['path']),True))
    if context['scope']=='music':
        for item in metadata['assets'].values():
            if item.get('path'):queue.append((Path(item['path']),True))
        queue.extend((p,False) for p in json_refs(metadata,root))
    index=0
    while queue:
        source,required=queue.pop(0);source=source.resolve();tasks.check(job)
        if source in processed and (processed[source] or not required):continue
        processed[source]=required
        if not source.is_file():
            if required:raise ValueError('当前工程缺少输入素材，请重新定位后打包：'+str(source))
            warnings.append('未收纳缺失的历史引用：'+source.name);continue
        if source not in copied:
            if source.is_relative_to(root):target=stage/source.relative_to(root)
            else:
                parent=stage/'Reference Media';name=media_names.filename(source.stem,source.suffix);target=parent/name;number=2
                while target.exists():target=parent/media_names.filename(source.stem,source.suffix,number);number+=1
            copy_file(source,target)
        mapping[str(source)]=str(virtual/copied[source].relative_to(stage))
        suffix=source.suffix.lower()
        if suffix in ('.svp','.song'):
            try:queue.extend((p,required) for p in native_refs(source))
            except (ValueError,zipfile.BadZipFile) as error:
                if required:raise ValueError('原生工程依赖无法读取：'+str(source)) from error
                warnings.append('历史原生工程未解析：'+source.name)
        elif suffix=='.json':
            try:queue.extend((p,False) for p in json_refs(read_json(source),source.parent))
            except ValueError:pass
        index+=1;tasks.update(job,stage=f'收纳依赖 · {index} 个文件',progress=min(55,10+index//5))
    text,document=relocation.replacements(mapping)
    for target in stage.rglob('*'):
        tasks.check(job)
        if target.is_file():relocation.patch(target,text,document)
    # Canonicalize relative native references using the original source base.
    def virtual_file(actual):
        return Path(mapping[str(actual.resolve())]) if str(actual.resolve()) in mapping else virtual/actual.resolve().relative_to(root) if actual.resolve().is_relative_to(root) else None
    def host_transform(state,base):
        result=copy.deepcopy(state);value=result.get('projectPath')
        if value:
            target=virtual_file(asset_storage.local_reference(value.replace('\\\\','\\'),base))
            if target:result['projectPath']=str(target).replace('\\','\\\\') if '\\\\' in value else str(target)
        return result
    for source,target in copied.items():
        tasks.check(job)
        if source.suffix.lower()=='.svp':
            doc=read_json(source)
            def sv_walk(value):
                if isinstance(value,dict):
                    for key,item in value.items():
                        if key in ('filename','filePath','path') and isinstance(item,str) and Path(item).suffix.lower() in asset_storage.AUDIO:
                            dest=virtual_file(asset_storage.local_reference(item,source.parent))
                            if dest:value[key]=str(dest)
                        else:sv_walk(item)
                elif isinstance(value,list):
                    for item in value:sv_walk(item)
            sv_walk(doc);doc=document(doc)
            destination=doc.setdefault('renderConfig',{}).get('destination','')
            if not destination.startswith(str(virtual)):doc['renderConfig']['destination']=str(virtual/'exports/audio')
            save_json(target,doc)
        elif source.suffix.lower()=='.song':
            with zipfile.ZipFile(source) as original:
                buffer=io.BytesIO();names=set(original.namelist())
                with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as output:
                    for entry in original.infolist():
                        data=original.read(entry)
                        if entry.filename.endswith('.xml'):
                            def url(match):
                                actual=song_ref(match[2],source.parent,names)
                                if actual is None:return match[0]
                                dest=virtual_file(actual)
                                if dest is None and (actual.is_dir() or actual.name.lower() in ('mixdown','exports')):dest=virtual/'exports/audio'
                                directory=actual.is_dir() or actual.name.lower() in ('mixdown','exports') or match[2].endswith('/')
                                return match[1]+html.escape(dest.as_uri()+('/' if directory else ''),quote=True)+match[3] if dest else match[0]
                            data=text(re.sub(r'''(\burl\s*=\s*["'])([^"']*)(["'])''',url,data.decode('utf-8-sig'))).encode()
                        elif entry.filename.endswith('.vstpreset'):data=relocation.preset(data,lambda state:host_transform(state,source.parent))
                        output.writestr(entry,data)
                target.write_bytes(buffer.getvalue())
    metadata=document(metadata)
    if metadata['scope']=='music':metadata['bundle']['project']['pilot']=str(virtual)
    files={p.relative_to(stage).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in stage.rglob('*') if p.is_file()}
    fonts=set()
    for v in context['videos']:
        doc=video_project.load(v['id']);fonts.update(style.get('font','') for style in doc.get('styles',{}).values())
        for cue in doc.get('cues',[]):fonts.update((cue.get(key) or {}).get('font','') for key in ['originalStyle','translationStyle'])
    manifest={'schema':SCHEMA,'virtualRoot':str(virtual),'metadata':metadata,'files':files,'warnings':sorted(set(warnings)),'requirements':{'software':['Synthesizer V (for SVP)','Studio One and the original plugins (for Song)','FFmpeg/FFprobe (for video rendering)'],'fonts':sorted(fonts-{''}),'note':'新设备需安装原有声库、插件与字体；模型和程序本体未打包。插件内部无法解析的外部素材需在原生软件中归集。'}}
    if job.get('snapshotOnly'):
        if any(sha(p)!=digest for p,digest in sources.items()):raise ValueError('源工程在备份期间改变，请保存后重试')
        return {'stage':str(stage),'manifest':manifest}
    output=folder/generated(media_names.filename(context['title'],''),' - Project.cwpack');partial=output.with_suffix('.partial')
    with zipfile.ZipFile(partial,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        z.writestr('Manifest.json',json.dumps(manifest,ensure_ascii=False))
        for i,name in enumerate(files):tasks.check(job);z.write(stage/name,'Project/'+name);tasks.update(job,stage=f'打包 · {i+1}/{len(files)}',progress=55+int((i+1)/len(files)*40))
    if any(sha(p)!=digest for p,digest in sources.items()):raise ValueError('源工程在打包期间改变，请保存后重试')
    partial.rename(output)
    # Generated staging copies only. All user inputs remain read-only.
    if stage.resolve().parent==folder.resolve():shutil.rmtree(stage)
    return {'path':str(output),'fileCount':len(files),'bytes':output.stat().st_size,'warnings':manifest['warnings'],'requirements':manifest['requirements'],'url':'/project-package/'+job['id']}


def import_package(job,body):
    source=package_path(body.get('path'));folder=Path(job['folder']);stage=folder/'Import Copy';stage.mkdir();before=sha(source)
    with zipfile.ZipFile(source) as z:
        if len(z.infolist())>100000:raise ValueError('工程包文件过多')
        if 'Manifest.json' not in z.namelist():raise ValueError('不是 CoverWorkbench 工程包：缺少清单')
        entry=z.getinfo('Manifest.json')
        if entry.file_size>20_000_000:raise ValueError('工程包清单过大')
        manifest=json.loads(z.read(entry))
        if manifest.get('schema')!=SCHEMA or not isinstance(manifest.get('files'),dict):raise ValueError('不支持的工程包格式')
        names=z.namelist();expected={'Manifest.json',*['Project/'+n for n in manifest['files']]}
        if len(names)!=len({n.casefold() for n in names}) or set(names)!=expected:raise ValueError('工程包存在重复或未登记的文件')
        total=sum(z.getinfo('Project/'+n).file_size for n in manifest['files'])
        if total*2.2>shutil.disk_usage(folder).free:raise ValueError('导入校验需要约两份工程体积的临时空间，请先释放磁盘空间')
        for i,(name,description) in enumerate(manifest['files'].items()):
            tasks.check(job);parts=PurePosixPath(name).parts
            if not parts or PurePosixPath(name).is_absolute() or '\\' in name:raise ValueError('工程包文件路径无效')
            for part in parts:component(part,'工程包文件名')
            item=z.getinfo('Project/'+name)
            if ((item.external_attr>>16)&0o170000)==0o120000 or item.file_size!=description['bytes']:raise ValueError('工程包含链接或文件大小不符')
            target=stage.joinpath(*parts)
            if not target.resolve().is_relative_to(stage.resolve()):raise ValueError('工程包路径越界')
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(item) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            if sha(target)!=description['sha256']:raise ValueError('工程包校验失败：'+name)
            tasks.update(job,stage=f'校验导入 · {i+1}/{len(manifest["files"])}',progress=int((i+1)/len(manifest['files'])*60))
    metadata=manifest['metadata'];scope=metadata['scope'];label=component(body.get('name') or metadata['title'],'导入项目名')
    if scope not in ('music','video'):raise ValueError('工程包类型无效')
    if not isinstance(manifest.get('virtualRoot'),str) or not Path(manifest['virtualRoot']).is_absolute():raise ValueError('工程包根目录无效')
    parent=ROOT/'projects';parent.mkdir(exist_ok=True);destination=parent/label;version=2
    while destination.exists():destination=parent/generated(label,f'_v{version}');version+=1
    ident='song-'+uuid.uuid4().hex[:12] if scope=='music' else None
    videos=[];mapping={manifest['virtualRoot']:str(destination)};known={v['id'] for v in video_project.listing()}
    for video in metadata['videos']:
        old=component(video['id'],'视频工程名');new=old;n=2
        while new in known:new=generated(old,f'_v{n}');n+=1
        known.add(new);oldrel=Path(video['directory'])
        if oldrel.is_absolute() or '..' in oldrel.parts:raise ValueError('视频目录无效')
        newrel=Path('video')/new if scope=='video' else oldrel.parent/new
        mapping[str(Path(manifest['virtualRoot'])/oldrel)]=str(destination/newrel)
        videos.append((old,new,oldrel,newrel))
    text,document=relocation.replacements(mapping)
    # Rebuild in an unregistered folder before publishing any index entries.
    staging=folder/'Ready Project';staging.mkdir()
    for source_file in stage.rglob('*'):
        if not source_file.is_file():continue
        relative=source_file.relative_to(stage)
        relative_new=relative
        for old,new,oldrel,newrel in videos:
            if relative==oldrel or relative.is_relative_to(oldrel):relative_new=newrel/relative.relative_to(oldrel);break
        target=staging/relative_new;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_file,target)
        relocation.patch(target,text,document)
    for old,new,oldrel,newrel in videos:
        path=staging/newrel/'project.json';doc=read_json(path);doc['id']=new;doc['name']=new;save_json(path,doc)
        for record in (staging/newrel/'Exports').glob('*/job.json'):
            data=read_json(record);data['project']=new;save_json(record,data)
    tasks.check(job)
    if sha(source)!=before:raise ValueError('工程包在导入期间改变')
    stores=[ROOT/'config/projects.json',ROOT/'config/workspaces.local.json',project_assets.STORE,video_project.mapping_file(),ROOT/'config/video-links.local.json',daw.BUILD_INDEX]
    saved={};new_bundle=None
    try:
        import projects
        with projects.LOCK,daw.BUILD_LOCK,project_assets.LOCK,video_project.LOCK,workspaces.LOCK:
            saved={p:p.read_bytes() if p.exists() else None for p in stores}
            if destination.exists():raise ValueError('导入位置刚被其他窗口使用，请重试')
            staging.rename(destination)
            registry=video_project.mappings()
            for old,new,oldrel,newrel in videos:registry[new]=str(destination/newrel)
            save_json(video_project.mapping_file(),registry)
            if scope=='music':
                bundle=document(metadata['bundle']);p=bundle['project'];p.update(id=ident,pilot=str(destination),source=str(destination/'source'))
                assets={key:document(value['path']) for key,value in metadata['assets'].items() if value.get('path')}
                for value in assets.values():
                    if not Path(value).resolve().is_relative_to(destination.resolve()) or not Path(value).is_file():raise ValueError('工程包包含未收纳的输入引用')
                collector=asset_storage.Import(destination)
                native_queue=[Path(assets[r]) for r in ['svp','song'] if assets.get(r)];native_seen=set()
                while native_queue:
                    native=native_queue.pop().resolve()
                    if native in native_seen:continue
                    native_seen.add(native)
                    if native.suffix.lower()=='.svp':
                        doc_native=read_json(native);output=doc_native.get('renderConfig',{}).get('destination')
                        if output and not asset_storage.local_reference(output,native.parent).is_relative_to(destination.resolve()):raise ValueError('SV 渲染目录仍指向外部位置')
                    native_queue.extend(p for p in native_refs(native) if p.suffix.lower() in ('.svp','.song') and p.is_file() and p.is_relative_to(destination.resolve()))
                for role in ['svp','song']:
                    if assets.get(role) and not collector.self_contained(Path(assets[role]),role):raise ValueError('原生工程仍有外部引用，无法完成导入')
                if assets.get('svp'):
                    p['managedSVP']=assets['svp'];p['working']=assets['svp'];bundle['parsed']=parse_svp(assets['svp']);bundle['flags']=audit(bundle['parsed'])
                new_bundle=ROOT/'data/projects'/(ident+'.json');save_json(new_bundle,bundle)
                rows=read_json(ROOT/'config/projects.json');rows.append({key:p[key] for key in ['id','title','artist','language','duration','pilot','selectedVersion']});save_json(ROOT/'config/projects.json',rows)
                workspaces_doc=workspaces.registry();workspaces_doc[ident]=str(destination);save_json(ROOT/'config/workspaces.local.json',workspaces_doc)
                asset_doc=project_assets.document();asset_doc['projects'][ident]=assets;asset_doc['revision']+=1;save_json(project_assets.STORE,asset_doc)
                save_json(destination/'workspace.json',{'version':1,'musicId':ident,'title':p['title'],'directories':workspaces.DIRECTORIES,'importedPackageSHA256':before})
                if metadata.get('link'):
                    from video_links import STORE
                    links=read_json(STORE) if STORE.exists() else {'version':1,'links':{}};link=document(metadata['link']);link['videoId']=next((new for old,new,a,b in videos if old==link['videoId']),link['videoId']);links['links'][ident]=link;save_json(STORE,links)
                builds=read_json(daw.BUILD_INDEX) if daw.BUILD_INDEX.exists() else []
                save_json(daw.BUILD_INDEX,list(dict.fromkeys([*builds,*[str(p) for p in destination.rglob('build.json') if p.parent.parent.name=='studio-one']])))
            # Imported references have new fingerprints. Require a fresh alignment/preview review,
            # while preserving the already-materialized subtitle timestamps and offsets.
            for old,new,oldrel,newrel in videos:
                path=destination/newrel/'project.json';doc=read_json(path);doc['workflow']={};timing=doc.get('timing',{})
                for key in ['video','audio']:
                    value=doc.get(key)
                    if value and (key=='audio' and doc.get('audioSource')=='video' or key=='video' and doc.get('composition')) and (not Path(value).resolve().is_relative_to(destination.resolve()) or not Path(value).is_file()):doc[key]=''
                library=destination/newrel/'media-library.json';library_refs=[a['path'] for a in read_json(library)] if library.exists() else []
                refs=[doc.get('video'),doc.get('audio')]+[a['path'] for a in (doc.get('composition') or {}).get('assets',[])]+library_refs
                for value in refs:
                    if value and (not Path(value).resolve().is_relative_to(destination.resolve()) or not Path(value).is_file()):raise ValueError('视频工程包包含未收纳的输入引用')
                from video_workflow import file_key
                timing.update(videoKey=file_key(doc.get('video')),audioKey=file_key(doc.get('audio')));doc['timing']=timing;save_json(path,doc)
            for record in destination.rglob('Versions.json'):
                if record.parent.name not in ('Workbench','ProjectData'):continue
                data=read_json(record)
                for entry in data.get('entries',[]):
                    target=Path(entry['path'])
                    if not target.resolve().is_relative_to(destination.resolve()) or not target.is_file() or sha(target)!=entry['sha256']:raise ValueError('成品版本未收纳或校验失败')
                    stat=target.stat();entry.update(size=stat.st_size,mtime=stat.st_mtime_ns)
                save_json(record,data)
        if stage.resolve().parent==folder.resolve() and stage.name=='Import Copy':shutil.rmtree(stage)
        return {'scope':scope,'id':ident if scope=='music' else videos[0][1],'root':str(destination),'title':metadata['title'],'requirements':manifest.get('requirements'),'warnings':manifest.get('warnings',[])}
    except Exception:
        for path,data in saved.items():
            if data is None:path.unlink(missing_ok=True)
            else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        if new_bundle:new_bundle.unlink(missing_ok=True)
        if destination.exists() and destination.resolve().parent==parent.resolve():destination.rename(folder/'Unregistered Project')
        raise
