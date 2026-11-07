"""Durable, per-session drafts. Saving a draft never saves a creative document."""
import copy,json,re,threading,time
from core import read_json,save_json
import video_project as project

LOCK=threading.RLock()
FIELDS={'video','audio','audioSource','audioOffset','subtitleShift','gainDb','targetLufs','audioMode','resolution','fps','format','crf','burn','styles','cues','composition'}


def payload(doc):return {k:copy.deepcopy(doc[k]) for k in FIELDS if k in doc}


def records(ident):
    folder=project.folder(ident)/'Recovery'
    rows=[]
    for p in folder.glob('Draft *.json'):
        try:
            d=read_json(p)
            if all(k in d for k in ['session','sequence','baseRevision','updated','payload']):rows.append((p,d))
        except (ValueError,OSError):pass
    return rows


def listing(ident):
    current=project.load(ident)
    with LOCK:
        items=[dict(d,name=p.stem,conflict=d['baseRevision']!=current['revision']) for p,d in records(ident) if not d.get('dismissed') and d.get('payload')!=payload(current)]
    return {'revision':current['revision'],'drafts':sorted(items,key=lambda d:d['updated'],reverse=True)[:20]}


def update(ident,body):
    session=body.get('session','');sequence=body.get('sequence');base=body.get('baseRevision')
    if not isinstance(session,str) or not re.fullmatch(r'[0-9a-f-]{32,40}',session) or type(sequence) is not int or sequence<1 or type(base) is not int or base<1:raise ValueError('草稿会话无效')
    content=body.get('payload',{})
    if not isinstance(body.get('baseTiming',{}),dict):raise ValueError('草稿时间基准无效')
    if not isinstance(content,dict) or set(content)-FIELDS or len(json.dumps(content,ensure_ascii=False,allow_nan=False).encode())>1_800_000:raise ValueError('草稿内容过大或包含未知字段')
    with LOCK:
        current=project.load(ident);existing=next(((p,d) for p,d in records(ident) if d['session']==session),None)
        if existing:
            path,old=existing
            if sequence<=old['sequence']:return {'saved':False,'sequence':old['sequence']}
        else:
            folder=project.folder(ident)/'Recovery';folder.mkdir(exist_ok=True);number=1
            while (folder/f'Draft {number:03}.json').exists():number+=1
            path=folder/f'Draft {number:03}.json'
        dismissed=body.get('action')=='dismiss'
        if dismissed and not body.get('dismissSession') and base!=current['revision']:raise ValueError('工程修订已变化，请刷新后处理草稿')
        save_json(path,{'session':session,'sequence':sequence,'baseRevision':base,'baseTiming':copy.deepcopy(body.get('baseTiming',existing[1].get('baseTiming',{}) if existing else {})),'updated':time.time(),'payload':existing[1]['payload'] if dismissed and existing else payload(content),'dismissed':dismissed})
        return {'saved':True,'name':path.stem,'updated':time.time(),'conflict':base!=current['revision']}


def recover_copy(ident,body):
    with LOCK:
        found=next((d for p,d in records(ident) if p.stem==body.get('name') and not d.get('dismissed')),None)
        if not found:raise ValueError('草稿不存在或已处理')
        current=project.load(ident)
        if body.get('updated')!=found['updated']:raise ValueError('草稿已更新，请刷新后再恢复')
        # Validation runs before creating the copy; invalid draft paths remain recoverable.
        merged=project.validate({**current,**copy.deepcopy(found['payload']),'timing':copy.deepcopy(found.get('baseTiming',current.get('timing',{})))})
        from video_workflow import reconcile
        # A recovered copy is already a saved document: materialize the draft's
        # pending offset delta now, so playback and the next save use one clock.
        merged=project.validate(reconcile(merged,merged));merged['workflow']={}
        for key in ['id','revision','updated','created']:merged.pop(key,None)
        merged['name']=current['name']+' - Recovered'
        return project.create({'name':merged['name']},internal=merged,directory=project.folder(ident).parent)
