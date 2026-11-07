"""Explicit, backed-up migration of legacy shared folders into named projects.

Preview: python tools/organize_projects.py
Apply while the workbench is stopped: python tools/organize_projects.py --apply
Original folders are archived under work/, never deleted. Native DAW state is
retargeted structurally; commercial plugin chunks stay byte-for-byte unchanged.
"""
from pathlib import Path
import argparse,copy,json,os,re,shutil,struct,sys,time,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from core import ROOT,read_json,save_json,sha
import workspaces,video_project,daw,asset_storage,lyric_files,media_names


def plan():
    music=read_json(ROOT/'config/projects.json');assets=read_json(ROOT/'config/project-assets.local.json').get('projects',{}) if (ROOT/'config/project-assets.local.json').exists() else {}
    links=read_json(ROOT/'config/video-links.local.json').get('links',{}) if (ROOT/'config/video-links.local.json').exists() else {}
    roots={p['id']:workspaces.proposed(p) for p in music};moves=[]
    for path in (ROOT/'projects/studio-one').glob('*/build.json'):
        build=read_json(path);owner=next((p for p in music if assets.get(p['id'],{}).get('song')==build.get('song')),None)
        if not owner:
            for p in music:
                source=read_json(ROOT/'data/projects'/(p['id']+'.json'))['project']
                if build.get('sourceSVP') in [source.get('working'),source.get('managedSVP'),*[f.get('original') for f in source.get('files',[])]]:owner=p;break
        label=media_names.filename(build.get('name') or path.parent.name,'')
        if 'setup_check' in build.get('name',''):
            target=ROOT/'work/Legacy Studio One Checks'/label.replace('_',' ')
        elif owner:target=roots[owner['id']]/'studio-one'/workspaces.name(owner['title'])
        else:target=ROOT/'projects'/label/'studio-one'/label
        moves.append({'source':str(path.parent),'target':str(target),'kind':'song','owner':owner['id'] if owner else None})
    for path in (ROOT/'projects/video').glob('*/project.json'):
        doc=read_json(path);owner=next((p for p in music if links.get(p['id'],{}).get('videoId')==doc['id']),None)
        target=(roots[owner['id']] if owner else ROOT/'projects'/workspaces.name(doc['name']))/'video'/doc['id']
        moves.append({'source':str(path.parent),'target':str(target),'kind':'video','owner':owner['id'] if owner else None})
    for move in moves:
        source,target=Path(move['source']).resolve(),Path(move['target']).resolve()
        if not source.is_relative_to((ROOT/'projects').resolve()) or source==target or target.is_relative_to(source):raise ValueError('迁移路径不安全')
        if target.exists():raise ValueError('目标已经存在，停止以避免覆盖：'+str(target))
        if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in [source,*source.rglob('*')]):raise ValueError('源目录包含链接，请先人工确认')
    return {'roots':{k:str(v) for k,v in roots.items()},'moves':moves}


def replacements(mapping):
    pairs=[]
    for old,new in mapping.items():
        if old.startswith('/download/'):
            pairs.append((old,new));continue
        for a,b in [(old,new),(old.replace('\\','\\\\'),new.replace('\\','\\\\')),(Path(old).as_posix(),Path(new).as_posix()),(Path(old).as_uri(),Path(new).as_uri())]:
            if a!=b:pairs.append((a,b))
    pairs=sorted(set(pairs),key=lambda row:-len(row[0]))
    def text(value):
        for a,b in pairs:value=value.replace(a,b)
        return value
    def document(value):
        if isinstance(value,str):return text(value)
        if isinstance(value,list):return [document(x) for x in value]
        if isinstance(value,dict):return {text(k):document(v) for k,v in value.items()}
        return value
    return text,document


def preset(blob,transform):
    if blob[:4]!=b'VST3' or blob[8:40] not in asset_storage.SV_IDS:return blob
    chunks=[]
    for tag,data in daw.chunks(blob):
        if tag==b'Comp':
            raw=data.decode('utf-8');state,end=json.JSONDecoder().raw_decode(raw);changed=transform(state)
            if state!=changed:data=(json.dumps(changed,ensure_ascii=True)+raw[end:]).encode()
        chunks.append((tag,data))
    payload=b'';records=[]
    for tag,data in chunks:records.append((tag,48+len(payload),len(data)));payload+=data
    return blob[:40]+struct.pack('<Q',48+len(payload))+payload+b'List'+struct.pack('<I',len(records))+b''.join(struct.pack('<4sQQ',*r) for r in records)


def patch(path,text,document):
    suffix=path.suffix.lower();before=path.read_bytes();after=before
    if not before:return False  # Some model caches intentionally use empty .json marker files.
    if suffix in ('.json','.svp'):
        raw=before.decode('utf-8-sig');padding=len(raw)-len(raw.rstrip('\x00'))
        obj=json.loads(raw.rstrip('\x00'));updated=document(obj)
        if obj!=updated:after=(json.dumps(updated,ensure_ascii=False,indent=2)+'\n'+'\x00'*padding).encode()
    elif suffix=='.vstpreset':after=preset(before,document)
    elif suffix in ('.song','.songtemplate'):
        import io
        buffer=io.BytesIO();changed=False
        with zipfile.ZipFile(io.BytesIO(before)) as source,zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as dest:
            for entry in source.infolist():
                data=source.read(entry);new=text(data.decode('utf-8-sig')).encode() if entry.filename.endswith('.xml') else preset(data,document) if entry.filename.endswith('.vstpreset') else data
                changed|=new!=data;dest.writestr(entry,new)
        if changed:after=buffer.getvalue()
    elif suffix in ('.toml','.xml','.txt','.md','.log','.py','.ps1','.vbs','.bat','.ffconcat'):
        try:after=text(before.decode('utf-8')).encode()
        except UnicodeDecodeError:pass
    if before!=after:
        stat=path.stat();path.write_bytes(after);os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        return True
    return False


def readable_lyrics(p,backup,mapping,source_root=None):
    root=Path(source_root) if source_root else workspaces.root(p);parent=root/'working/lyrics'
    if not parent.exists():return 0
    old=list(parent.glob('*.json'));count=0;consumed=set()
    for file in sorted(old):
        result=read_json(file)
        if not result.get('rows') or 'metadata' not in result:continue
        folder=lyric_files.allocate(p);source=Path(result.get('sourceFile',''));raw=read_json(source) if source.is_file() else None
        if raw:
            save_json(folder/'Source.json',raw);mapping[str(source)]=str(folder/'Source.json');consumed.add(source)
            result['sourceFile']=str(folder/'Source.json')
        old_exports=copy.deepcopy(result.get('exports',[]));lyric_files.export(p,result,folder,raw=raw)
        for item in old_exports:
            previous=Path(item['file'])
            match=next((e for e in result['exports'] if e['role']==('reading' if 'romaji' in previous.stem or 'reading' in previous.stem else 'original')),None)
            if match:
                mapping[str(previous)]=match['file'];mapping[item['url']]=match['url'];consumed.add(previous)
        current=Path(p['pilot'])/'analysis/lyrics-current.json'
        if current.exists() and old_exports and read_json(current).get('exports',[{}])[0].get('file')==old_exports[0]['file']:
            save_json(current,result)
        mapping[str(file)]=result['recordFile'];consumed.add(file);count+=1
    # Preserve non-package leftovers with readable names rather than dropping them.
    for file in parent.iterdir():
        if file.is_file() and file not in consumed:
            target=lyric_files.allocate(p)/('Imported Reading'+file.suffix);shutil.copy2(file,target);mapping[str(file)]=str(target);consumed.add(file)
    for file in sorted(consumed):
        if not file.is_file() or not file.resolve().is_relative_to(root.resolve()):continue
        target=backup/'lyrics'/workspaces.suggested(p)/root.name/file.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(file,target);assert sha(file)==sha(target)
        index=backup/'lyric-archive.json';records=read_json(index) if index.exists() else []
        records.append({'original':str(file),'archive':str(target),'sha256':sha(file)});save_json(index,records)
        file.unlink()
    return count


def apply(proposal):
    # The operator must close the service; never migrate an active editing session.
    import urllib.request
    try:
        urllib.request.urlopen('http://127.0.0.1:8765/api/health',timeout=2)
    except OSError:pass
    else:raise ValueError('请先保存网页草稿并彻底退出工作台，再执行迁移')
    number=1
    while (ROOT/f'work/Project Organization Backup {number:03}').exists():number+=1
    backup=ROOT/f'work/Project Organization Backup {number:03}';backup.mkdir(parents=True)
    save_json(backup/'plan.json',proposal)
    old_files={p:sha(p) for m in proposal['moves'] for p in Path(m['source']).rglob('*') if p.is_file()}
    metadata=list((ROOT/'config').glob('*.json'))+list((ROOT/'data').rglob('*.json'))
    for p in metadata:
        target=backup/'metadata'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    mapping={m['source']:m['target'] for m in proposal['moves']};created=[]
    try:
        rows=read_json(ROOT/'config/projects.json')
        # Reserve the planned song roots before copying nested folders into them.
        # Calling the allocator after copy would mistake its own parent for a conflict.
        registry=workspaces.registry()
        for row in rows:
            if row['id'] not in registry:
                dest=Path(proposal['roots'][row['id']]);dest.mkdir(parents=True,exist_ok=True)
                for directory in workspaces.DIRECTORIES:(dest/directory).mkdir(parents=True,exist_ok=True)
                save_json(dest/'workspace.json',{'version':1,'musicId':row['id'],'title':row['title'],'legacyPilot':row['pilot'],'directories':workspaces.DIRECTORIES})
                registry[row['id']]=str(dest)
        save_json(ROOT/'config/workspaces.local.json',registry)
        for move in proposal['moves']:
            target=Path(move['target']);target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(move['source'],target,copy_function=shutil.copy2);created.append(target)
        assert all(sha(p)==h for p,h in old_files.items()),'源文件在复制期间发生变化'
        # Capture current pointers before conversion, including legacy private pilots.
        pointers=[]
        for row in rows:
            path=Path(row['pilot'])/'analysis/lyrics-current.json'
            if path.exists():
                target=backup/'lyric-pointers'/(row['id']+'.json');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target);pointers.append((path,target))
        # Capture lyric originals too; package conversion is explicit and versioned.
        lyric_count=0
        for row in rows:
            p=read_json(ROOT/'data/projects'/(row['id']+'.json'))['project']
            for source_root in dict.fromkeys([workspaces.root(p),Path(p['pilot'])]):
                lyric_count+=readable_lyrics(p,backup,mapping,source_root)
        text,document=replacements(mapping)
        candidates=set(metadata)|{p for root in created for p in root.rglob('*') if p.is_file()}|{p for p in (ROOT/'projects').rglob('*.json') if not any(p.is_relative_to(Path(m['source'])) for m in proposal['moves'])}
        # Include lyric-current pointers in legacy private pilots, without moving source work.
        candidates.update(path for path,_ in pointers)
        modified=[]
        for p in sorted(candidates):
            if p.is_file() and patch(p,text,document):modified.append(str(p))
        index=video_project.mappings()
        for move in proposal['moves']:
            if move['kind']=='video':index[Path(move['source']).name]=move['target']
        save_json(video_project.mapping_file(),document(index))
        builds=read_json(daw.BUILD_INDEX) if daw.BUILD_INDEX.exists() else []
        builds=list(dict.fromkeys([*builds,*[str(Path(m['target'])/'build.json') for m in proposal['moves'] if m['kind']=='song']]))
        save_json(daw.BUILD_INDEX,document(builds))
        # Verify saved video content except paths, and every copied source file.
        for move in proposal['moves']:
            source,target=Path(move['source']),Path(move['target'])
            for old in source.rglob('*'):
                if old.is_file():
                    new=target/old.relative_to(source)
                    assert new.is_file(),str(new)
                    if old.suffix.lower() in ('.wav','.flac','.mp3','.mp4','.mkv','.webm','.png','.jpg'):assert sha(old)==sha(new)
            if move['kind']=='video':assert read_json(target/'project.json')==document(read_json(source/'project.json'))
        assert all(sha(p)==h for p,h in old_files.items()),'源文件在提交前发生变化'
        for legacy in [ROOT/'projects/studio-one',ROOT/'projects/video']:
            if legacy.exists():
                # Verify the final absolute move stays inside this workspace's private backup.
                target=(backup/'originals'/legacy.name).resolve()
                assert target.is_relative_to(backup.resolve()) and legacy.resolve().parent==(ROOT/'projects').resolve()
                legacy.rename(target) if target.parent.exists() else (target.parent.mkdir(parents=True),legacy.rename(target))
        save_json(backup/'manifest.json',{'status':'complete','moves':proposal['moves'],'modified':modified,'lyricPackages':lyric_count,'originalHashes':{str(p):h for p,h in old_files.items()}})
        return {'backup':str(backup),'moves':len(proposal['moves']),'lyricPackages':lyric_count,'modified':len(modified)}
    except Exception:
        # Restore active registries and consumed lyric originals before surfacing failure.
        for saved in (backup/'metadata').rglob('*.json'):
            target=ROOT/saved.relative_to(backup/'metadata');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(saved,target)
        for path,saved in locals().get('pointers',[]):shutil.copy2(saved,path)
        if (backup/'lyric-archive.json').exists():
            for entry in read_json(backup/'lyric-archive.json'):
                target=Path(entry['original']);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(entry['archive'],target)
        for name in ['studio-one','video']:
            original=ROOT/'projects'/name;saved=backup/'originals'/name
            if saved.exists() and not original.exists():saved.rename(original)
        save_json(backup/'failure.json',{'status':'incomplete','copied':list(map(str,created)),'message':'Original backup and metadata retained. Stop and inspect before retrying.'})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    proposal=plan();print(json.dumps(apply(proposal) if args.apply else proposal,ensure_ascii=False,indent=2))
