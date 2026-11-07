"""Immutable, named mix/video snapshots and auditable release stages."""
from pathlib import Path
import copy,threading,time,shutil
from core import ROOT,read_json,save_json,sha
from windows_names import generated
import project_context as contexts
import video_project
import media_names

LOCK=threading.RLock()
STAGES={'trial':'试用','final':'定稿','published':'已发布'}
EXTENSIONS={'mix':{'.wav','.flac','.mp3','.m4a','.aif','.aiff'},'video':{'.mp4','.mkv','.webm','.mov'}}


def path(context):return contexts.metadata(context)/'Versions.json'


def document(context):
    file=path(context)
    return read_json(file) if file.exists() else {'revision':0,'entries':[]}


def listing(scope,ident):
    context=contexts.get(scope,ident);doc=document(context)
    return {**doc,'entries':[dict(e,available=Path(e['path']).is_file(),changed=not same(e)) for e in doc['entries']],'stages':STAGES}


def same(entry):
    try:
        stat=Path(entry['path']).stat()
        return stat.st_size==entry['size'] and stat.st_mtime_ns==entry['mtime']
    except OSError:return False


def register(scope,ident,body):
    context=contexts.get(scope,ident);kind=body.get('kind');stage=body.get('stage','trial');label=body.get('label','')
    if kind not in EXTENSIONS or stage not in STAGES or not isinstance(label,str) or len(label)>150:raise ValueError('版本类型、阶段或名称无效')
    label=label.strip();source=video_project.local(body.get('path'),EXTENSIONS[kind]);digest=sha(source)
    with LOCK:
        doc=document(context)
        if body.get('revision')!=doc['revision']:raise ValueError('版本列表已更新，请刷新')
        prefix='Mix' if kind=='mix' else 'Video';number=1
        parent=context['root']/'exports/releases';parent.mkdir(parents=True,exist_ok=True)
        while True:
            folder=parent/f'{prefix} {number:03}'
            try:folder.mkdir();break
            except FileExistsError:number+=1
        target=folder/generated(media_names.filename(context['title'],''),f' - {prefix} {number:03}'+source.suffix.lower())
        try:
            shutil.copy2(source,target)
            if sha(source)!=digest or sha(target)!=digest:raise ValueError('源文件在版本保存期间变化，请完成原生导出后重试')
            stat=target.stat();provenance=None
            report=source.parent/'report.json'
            if kind=='video' and report.exists():
                data=read_json(report)
                if data.get('sha256')==digest:provenance=data.get('provenance') or {'subtitleRevision':data.get('revision'),'audioSource':data.get('audioSource','mix')}
            entry={'id':folder.name,'kind':kind,'name':label or folder.name,'stage':stage,'path':str(target),'source':str(source),'sha256':digest,'size':stat.st_size,'mtime':stat.st_mtime_ns,'created':time.time(),'provenance':provenance,'history':[{'stage':stage,'at':time.time()}]}
            doc['entries'].append(entry);doc['revision']+=1;save_json(path(context),doc)
        except Exception:
            # Incomplete copies remain diagnosable; never remove the user's input.
            save_json(folder/'Incomplete.json',{'source':str(source),'message':'版本保存未完成；原文件保留'})
            raise
    return listing(scope,ident)


def stage(scope,ident,body):
    context=contexts.get(scope,ident)
    with LOCK:
        doc=document(context)
        if body.get('revision')!=doc['revision'] or body.get('stage') not in STAGES:raise ValueError('阶段无效或列表已更新')
        entry=next((e for e in doc['entries'] if e['id']==body.get('entry')),None)
        if not entry or not same(entry):raise ValueError('版本文件缺失或已变化，请重新保存版本')
        if body['stage'] in ('final','published') and sha(entry['path'])!=entry['sha256']:raise ValueError('文件校验与保存版本不符')
        entry['stage']=body['stage'];entry['history'].append({'stage':body['stage'],'at':time.time()});doc['revision']+=1;save_json(path(context),doc)
    return listing(scope,ident)


def video_context(ident):
    from video_links import STORE
    links=read_json(STORE).get('links',{}) if STORE.exists() else {}
    owner=next((key for key,value in links.items() if value.get('videoId')==ident),None)
    try:return contexts.get('music',owner) if owner else contexts.get('video',ident)
    except ValueError:return contexts.get('video',ident)


def provenance(doc,hashes=None):
    context=video_context(doc['id']);entries=list(document(context)['entries']);audio=doc.get('audio','');original=doc.get('audioSource')=='video'
    if context['scope']=='music':entries += document(contexts.get('video',doc['id']))['entries']
    entries.sort(key=lambda e:e['created'])
    digest=(hashes or {}).get(audio)
    def match_audio(entry):
        if digest:return entry['sha256']==digest
        if entry['path']==audio:return True
        if entry['source']==audio:
            try:s=Path(audio).stat();return s.st_size==entry['size'] and s.st_mtime_ns==entry['mtime']
            except OSError:return False
        return False
    match=next((e for e in reversed(entries) if e['kind']=='mix' and same(e) and match_audio(e)),None) if not original else None
    import hashlib,json
    signature=hashlib.sha256(json.dumps({'cues':doc.get('cues',[]),'styles':doc.get('styles',{}),'shift':doc.get('subtitleShift',0)},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return {'audioSource':doc.get('audioSource','mix'),'mixVersion':match['id'] if match else None,'mixName':match['name'] if match else None,'mixStage':match['stage'] if match else None,'audioFile':Path(audio).name if audio and not original else None,'subtitleRevision':doc['revision'],'captionsSignature':signature,'unmarked':not original and not match}
