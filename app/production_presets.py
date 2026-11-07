"""Caption and delivery settings only: no paths, clips, cues, or time offsets."""
import copy,threading
from core import ROOT,read_json,save_json
import video_project as project
from windows_names import component

STORE=ROOT/'config/production-presets.local.json'
LOCK=threading.RLock()
KEYS={'styles','resolution','fps','format','crf','burn'}


def builtins():
    styles={'original':{**project.STYLE,'size':38,'y':958},'translation':{**project.STYLE,'size':44,'y':1026}}
    base=dict(styles=styles,resolution='1080',fps='source',format='mp4',crf=18,burn=True)
    english=copy.deepcopy(base);english['styles']['original']['font']='Arial'
    return [{'name':'中日双语 · 清晰字幕','settings':base,'builtin':True},{'name':'中英双语 · 西文字幕','settings':english,'builtin':True}]


def listing():
    custom=read_json(STORE) if STORE.exists() else []
    return builtins()+[dict(p,builtin=False) for p in custom]


def validated(value):
    if not isinstance(value,dict) or set(value)-KEYS:raise ValueError('预设只允许字幕样式和导出规格')
    seed=dict(video='',audio='',audioMode='gain',resolution='source',fps='source',format='mp4',crf=18,burn=True,styles={'original':project.STYLE,'translation':project.STYLE},cues=[])
    result=project.validate({**seed,**copy.deepcopy(value)})
    return {k:result[k] for k in KEYS}


def save(body):
    name=component(body.get('name'),'预设名称')
    if any(p['name']==name for p in builtins()):raise ValueError('内置预设请使用新名称另存')
    settings=validated(body.get('settings'))
    with LOCK:
        items=read_json(STORE) if STORE.exists() else []
        previous=next((p for p in items if p['name']==name),None)
        if previous and not body.get('replace'):raise ValueError('同名预设已存在，请另存名称或明确选择覆盖')
        items=[p for p in items if p['name']!=name]+[{'name':name,'settings':settings}];save_json(STORE,items)
    return listing()
