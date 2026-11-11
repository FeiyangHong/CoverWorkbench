"""Metadata-only discovery; stable-file proposals never modify creative documents."""
from pathlib import Path
import threading,time
from core import ROOT,read_json,save_json
import project_assets,workspaces,mix_sources,video_links,video_project
LOCK=threading.RLock()

def stamp(path):
    try:s=Path(path).stat();return {'size':s.st_size,'mtime':str(s.st_mtime_ns)}
    except OSError:return None

def scan(ident):
    with LOCK:
        p=project_assets.project(ident);root=workspaces.root(p);file=root/'analysis/Workbench/Handoff Watch.json'
        state=read_json(file) if file.exists() else {'observed':{},'accepted':{},'pending':{}}
        chosen=project_assets.overrides(ident);audio=p.get('audio',{});native={'svp':chosen.get('svp') or p.get('managedSVP') or p.get('working'),'song':chosen.get('song') or p.get('dawCopy',{}).get('song')}
        mix=chosen.get('mix') or audio.get('mix',{}).get('original');found={}
        for role,path in {**native,'mix':mix}.items():
            if path and Path(path).is_file():found[str(Path(path).resolve())]=role
        folders={root/'exports/audio'}
        if native['song']:folders.add(Path(native['song']).parent/'Mixdown')
        for folder in folders:
            if not folder.is_dir():continue
            for index,path in enumerate(folder.iterdir()):
                if index>=500:break
                if path.is_file() and path.suffix.lower() in project_assets.AUDIO and not mix_sources.STEMS.search(path.stem) and not any(x in path.name.lower() for x in ['.partial','.tmp','.rendering']):found[str(path.resolve())]='mix'
        now=time.time();pending=state['pending']
        for path,role in found.items():
            current=stamp(path);previous=state['observed'].get(path)
            if not current:continue
            if not previous or previous['stamp']!=current:
                state['observed'][path]={'stamp':current,'since':now,'role':role}
                if not previous and role!='mix':state['accepted'][path]=current
                pending.pop(path,None);continue
            if now-previous['since']<3:continue
            if state['accepted'].get(path)==current:continue
            if role=='mix' and mix and Path(path).resolve()==Path(mix).resolve() and not previous.get('announced') and path not in state['accepted']:
                state['accepted'][path]=current;continue
            pending[path]={'path':path,'role':role,'name':Path(path).name,'stamp':current,'detectedAt':previous['since'],'previous':state['accepted'].get(path)}
        for path in list(pending):
            if path not in found or stamp(path)!=pending[path]['stamp']:pending.pop(path,None)
        save_json(file,state)
        return {'project':ident,'changes':list(pending.values()),'checkedAt':now,'watchFolders':[str(p) for p in folders],'note':'连续检查确认写入稳定后才提示；不会自动替换工程或移动字幕。'}

def accept(ident,body):
    path=str(Path(body.get('path','')).resolve());current=scan(ident);item=next((x for x in current['changes'] if x['path']==path),None)
    if not item or item['stamp']!=body.get('stamp') or stamp(path)!=item['stamp']:raise ValueError('文件版本已变化或仍在写入，请重新检查')
    if item['role']=='mix':
        assets=project_assets.status(ident)
        if body.get('assetRevision')!=assets['revision']:raise ValueError('素材登记已变化，请刷新后确认')
        project_assets.save(ident,{'revision':assets['revision'],'assets':{'mix':path},'storageMode':'copy'})
    p=project_assets.project(ident);file=workspaces.root(p)/'analysis/Workbench/Handoff Watch.json'
    with LOCK:
        state=read_json(file);state['accepted'][path]=item['stamp'];state['pending'].pop(path,None);save_json(file,state)
    return {'accepted':True,'role':item['role']}

def video_update(ident,body):
    if body.get('draftsSaved') is not True:raise ValueError('请先保存视频编辑草稿，再确认带入混音')
    path=project_assets.status(ident)['assets']['mix']['path'];overview=video_links.overview(ident,path)
    if not overview['linked']:raise ValueError('请先关联已有视频工程')
    if overview['linked']['revision']!=body.get('videoRevision'):raise ValueError('视频版本已变化，请重新检查')
    # The existing audio-only transfer preserves edited cues, styles and offsets.
    return video_links.perform(ident,{'action':'update','videoId':overview['linkedId'],'revision':body['videoRevision'],'sourceSignature':overview['signature'],'audioPath':path,'audio':True,'captions':False})
