"""Persistent shelf preferences; timestamps describe saved local project work."""
from pathlib import Path
from datetime import datetime
import threading
from core import ROOT, read_json, save_json

STORE=ROOT/'config/project-library.local.json'
LOCK=threading.RLock()
MODES={'updated-desc','updated-asc','created-desc','created-asc','name','manual'}


def timestamp(value):
    try:return float(value) if isinstance(value,(float,int)) else datetime.fromisoformat(value).timestamp()
    except (ValueError,TypeError):return 0


def listing(kind):
    if kind=='music':
        rows=[]
        import project_assets
        assets=project_assets.document().get('projects',{})
        for entry in read_json(ROOT/'config/projects.json'):
            path=ROOT/'data/projects'/(entry['id']+'.json')
            doc=read_json(path).get('project',{}) if path.exists() else {}
            created=timestamp(doc.get('builtAt')) or (path.stat().st_ctime if path.exists() else 0)
            files=[path,Path(entry['pilot'])/'analysis/review.json',Path(entry['pilot'])/'analysis/lyrics-current.json']
            files += [Path(p) for p in [doc.get('managedSVP'),doc.get('working'),assets.get(entry['id'],{}).get('song'),assets.get(entry['id'],{}).get('svp')] if p]
            rows.append(dict(entry,created=created,updated=max([created]+[p.stat().st_mtime for p in files if p.exists()])))
        return rows
    if kind=='video':
        import video_project
        return [dict(p,title=p['name'],created=timestamp(p.get('created',p['updated'])),updated=timestamp(p['updated'])) for p in video_project.listing()]
    raise ValueError('未知工程列表')


def state(kind):
    rows=listing(kind)
    with LOCK:preferences=read_json(STORE).get(kind,{}) if STORE.exists() else {}
    return {'rows':rows,'mode':preferences.get('mode','updated-desc'),'order':preferences.get('order',[])}


def save(kind,body):
    rows=listing(kind);known={p['id'] for p in rows};mode=body.get('mode')
    order=body.get('order',[])
    if mode not in MODES or not isinstance(order,list) or any(not isinstance(x,str) for x in order) or len(set(order))!=len(order) or not set(order)<=known:raise ValueError('工程排序参数无效，请刷新列表')
    with LOCK:
        doc=read_json(STORE) if STORE.exists() else {}
        doc[kind]={'mode':mode,'order':order};save_json(STORE,doc)
    return state(kind)
