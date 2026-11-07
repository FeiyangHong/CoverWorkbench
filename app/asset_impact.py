"""Explicit source-version inspection, without replacing creative documents."""
from pathlib import Path
import time
from core import read_json,save_json
import project_assets,workspaces,video_project,video_workflow,video_links

def fingerprint(value):
    if not value:return None
    path=Path(value)
    try:
        # Nanosecond timestamps exceed JavaScript's safe integer range.
        s=path.stat();return {'path':str(path.resolve()),'size':s.st_size,'mtime':str(s.st_mtime_ns)}
    except OSError:return {'path':str(path),'missing':True}

def video_sources(doc):
    values={k:doc.get(k) for k in ['video','audio']}
    values.update({'asset:'+a['id']:a['path'] for a in (doc.get('composition') or {}).get('assets',[])})
    return {k:fingerprint(v) for k,v in values.items() if v}

def scan_video(ident):
    doc=video_project.load(ident);baseline=doc.get('sourceVersions',{});current=video_sources(doc);changes=[]
    for key,value in current.items():
        prior=baseline.get(key);changed=bool(prior and prior!=value)
        if not prior and key in ('audio','video'):
            old=doc.get('timing',{}).get(key+'Key');changed=bool(old and old!=video_workflow.file_key(doc.get(key)))
        if value.get('missing') or changed:changes.append({'role':key,'before':prior,'after':value,'missing':bool(value.get('missing')),
            'effects':['核对音频起点与字幕时间','重做准确预览与成片'] if key=='audio' else ['核对剪切点与源片段时长','重做准确预览与成片']})
    return {'id':ident,'revision':doc['revision'],'changes':changes,'untracked':not bool(baseline),'current':current,'note':'只报告变化；不会自动替换混音、重排字幕或更改偏移。'}

def scan_music(ident,record=False,expected=None):
    p=project_assets.project(ident);file=workspaces.root(p)/'analysis/Asset Baseline.json';assets=project_assets.status(ident)['assets']
    current={k:fingerprint(a['path']) for k,a in assets.items() if a['path']};old=read_json(file) if file.is_file() else None
    if record:
        if expected!=current:raise ValueError('素材在确认期间变化，请重新检查')
        save_json(file,{'at':time.time(),'assets':current});old=read_json(file)
    effects={'source':['需要时重新分离素材'],'vocals':['需要时重新提取主声与和声'],'lead':['核对 SV 参考轨；音符不会自动更新'],'harmony':['核对和声 SV 参考轨'],'svp':['在 Studio One 中重新加载或渲染人声'],'song':['重新导出成品混音'],'mix':['明确带入新版混音','重新核对对齐、预览和导出'],'accompaniment':['在 Studio One 中核对伴奏并重新导出']}
    changes=[{'role':k,'before':(old or {}).get('assets',{}).get(k),'after':v,'missing':bool(v.get('missing')),'effects':effects.get(k,[])} for k,v in current.items() if v.get('missing') or old and v!=old['assets'].get(k)]
    linked=video_links.overview(ident);video_id=linked.get('linkedId') if linked.get('linked') else None
    return {'id':ident,'current':current,'changes':changes,'baselineAt':old['at'] if old else None,'video':scan_video(video_id) if video_id else None,'note':'第一次检查请记录基准；之后可查看素材变化及受影响的步骤。'}
