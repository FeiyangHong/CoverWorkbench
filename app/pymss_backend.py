"""Optional isolated PyMSS runtime and explicitly installed separation recipes."""
from pathlib import Path
import json,os,subprocess,time
from core import ROOT,read_json
import settings

PRESETS={
 'big7':{'name':'Big Beta 7','kind':'song','catalog':'big_beta7.ckpt'},
 'deux':{'name':'DeUX · becruily','kind':'song','catalog':'becruily_deux.ckpt'},
 'hyperace-voc':{'name':'HyperACE v2 · Vocals','kind':'song','catalog':'bs_roformer_voc_hyperacev2.ckpt'},
 'hyperace-inst':{'name':'HyperACE v2 · Instrumental','kind':'song','catalog':'bs_roformer_inst_hyperacev2.ckpt'},
 'leap-voc':{'name':'Leap Xe · Vocals','kind':'song','hfFile':'Xe/bs_leap_xe_voc.ckpt','hfConfig':'Xe/leap_xe_config_voc.yaml'},
 'leap-inst':{'name':'Leap Xe · Instrumental','kind':'song','hfFile':'Xe/bs_leap_xe_inst.ckpt','hfConfig':'Xe/leap_xe_config_inst.yaml'},
 'mel-karaoke':{'name':'Mel Karaoke · becruily (legacy)','kind':'harmony','catalog':'mel_band_roformer_karaoke_becruily.ckpt'},
 'bs-frazer':{'name':'BS Karaoke · frazer & becruily','kind':'harmony','catalog':'bs_roformer_karaoke_frazer_becruily.ckpt'},
 'bs-anvuew':{'name':'BS Karaoke · anvuew','kind':'harmony','catalog':'bs_roformer_karaoke_anvuew.ckpt'},
}

_discovered=None
def discover():
    global _discovered
    if _discovered and time.monotonic()-_discovered[0]<30:return _discovered[1]
    directory=None
    if os.name=='nt':
        roots=[Path.home()/'Desktop',Path(os.environ.get('PUBLIC','C:/Users/Public'))/'Desktop',Path(os.environ.get('PROGRAMDATA','C:/ProgramData'))/'Microsoft/Windows/Start Menu/Programs']
        link=next((p for root in roots if root.is_dir() for p in root.glob('*[Pp]ymss*.lnk')),None)
        if link:
            command='(New-Object -ComObject WScript.Shell).CreateShortcut($env:CW_PYMSS_LINK).TargetPath'
            try:
                result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],env={**os.environ,'CW_PYMSS_LINK':str(link)},capture_output=True,text=True,timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode==0 and Path(result.stdout.strip()).is_file():directory=Path(result.stdout.strip()).parent
            except (OSError,subprocess.SubprocessError):pass
    _discovered=(time.monotonic(),directory);return directory

def environment():
    values=settings.load()
    directory=Path(values['pymssDirectory']) if values.get('pymssDirectory') else discover()
    data=Path(values.get('pymssDataRoot') or os.environ.get('PYMSS_STUDIO_DATA_ROOT') or (directory/'data' if directory and ((directory/'pymss-studio.portable').is_file() or (directory/'src-tauri').is_dir()) else Path.home()/'.pymss-studio'))
    state={}
    if directory:
        for base in [directory/'python-runtime/runtime-envs',data/'runtime-envs']:
            f=base/'active-runtime.json'
            if f.is_file():
                state=read_json(f)
                for key in ('pythonPath','overlayPath'):
                    if state.get(key) and not Path(state[key]).is_absolute():state[key]=str(base/state[key])
                break
    app_settings=read_json(data/'settings/app.json') if (data/'settings/app.json').is_file() else {}
    python=Path(values['pymssPython']) if values.get('pymssPython') else Path(state['pythonPath']) if state.get('pythonPath') else next((directory/p for p in ['.venv/Scripts/python.exe','venv/Scripts/python.exe','python-runtime/python.exe','.venv/bin/python'] if directory and (directory/p).is_file()),ROOT/'runtime/pymss/env/Scripts/python.exe') if directory else ROOT/'runtime/pymss/env/Scripts/python.exe'
    models=Path(values.get('pymssModels') or app_settings.get('modelDir') or data/'models' if directory else values.get('pymssModels') or ROOT/'runtime/pymss/models')
    return {'python':python,'models':models,'directory':directory,'data':data,'overlay':state.get('overlayPath'),'runtime':state}

def paths():
    env=environment();return env['python'],env['models']

def installation():
    python,folder=paths()
    if not python.is_file():raise ValueError('尚未找到 PyMSS；请选择 App 安装目录或源码 Python，详见 docs/PyMSS.md')
    env=environment()
    module_candidates=[python.parent.parent/'Lib/site-packages/pymss/__init__.py',python.parent/'Lib/site-packages/pymss/__init__.py']
    module_candidates.extend(python.parent.parent.glob('lib/python*/site-packages/pymss/__init__.py'))
    if env.get('directory'):module_candidates.append(env['directory']/'pymss/__init__.py')
    if env.get('overlay'):module_candidates.append(Path(env['overlay'])/'pymss/__init__.py')
    if not any(p.is_file() for p in module_candidates):raise ValueError('所选 Python 未找到 pymss；请在 App 中准备活动环境，或选择已安装 pymss 的源码环境')
    registry_file=ROOT/'runtime/pymss/Model Registry.json'
    registry=read_json(registry_file) if registry_file.is_file() else {}
    if not isinstance(registry,dict):raise ValueError('PyMSS 模型登记文件格式无效')
    models={}
    # Read package catalog metadata without importing Torch into the web server.
    catalog_candidates=[python.parent.parent/'Lib/site-packages/pymss/resources/model_catalog.json',python.parent/'Lib/site-packages/pymss/resources/model_catalog.json']
    if env.get('directory'):catalog_candidates.insert(0,env['directory']/'pymss/resources/model_catalog.json')
    if env.get('overlay'):catalog_candidates.insert(0,Path(env['overlay'])/'pymss/resources/model_catalog.json')
    catalog=next((p for p in catalog_candidates if p.is_file()),catalog_candidates[0])
    if catalog.is_file():
        entries={m['name']:m for m in read_json(catalog)['models']}
        for key,preset in PRESETS.items():
            entry=entries.get(preset.get('catalog'))
            if entry and (folder/entry['relpath']).is_file() and (folder/entry['config_relpath']).is_file():
                stems=['vocals','other'] if key=='big7' else ['vocals','instrument'] if key.startswith('hyperace') else ['Vocals','Instrumental']
                registry[key]={'model':str(folder/entry['relpath']),'config':str(folder/entry['config_relpath']),'modelType':entry['model_type'],'stems':stems}
    for key,row in registry.items():
        if key not in PRESETS or not isinstance(row,dict):continue
        if row.get('modelType') not in ('bs_roformer','mel_band_roformer','auto'):continue
        if all(isinstance(row.get(k),str) and Path(row[k]).is_absolute() and Path(row[k]).is_file() and Path(row[k]).resolve().is_relative_to(folder.resolve()) for k in ('model','config')):
            models[key]=row
    return folder,python,models

def capabilities():
    try:
        folder,python,models=installation()
        env=environment()
        return {'available':True,'python':str(python),'installation':str(folder),'appDirectory':str(env['directory'] or ''),'models':{k:{**v,'available':k in models} for k,v in PRESETS.items()},'message':'复用 PyMSS App / 源码环境与模型目录；不在分离任务中隐式下载'}
    except (OSError,ValueError,json.JSONDecodeError) as error:
        return {'available':False,'message':str(error),'models':{k:{**v,'available':False} for k,v in PRESETS.items()}}

def step(model,kind,models):
    if model not in PRESETS or PRESETS[model]['kind']!=kind or model not in models:raise ValueError('请选择已安装的对应 PyMSS 模型')
    row=models[model]
    stems={}
    for stem in row.get('stems',[]):
        normalized=stem.casefold()
        if normalized in ('vocals','vocal'):stems[stem]='vocals' if kind=='song' else 'lead'
        elif normalized in ('other','instrument','instrumental'):stems[stem]='accompaniment' if kind=='song' else 'harmony'
        else:raise ValueError('模型声部不适用于所选两声部流程')
    if set(stems.values())!=({'vocals','accompaniment'} if kind=='song' else {'lead','harmony'}):raise ValueError('模型缺少完整的两声部输出定义')
    return {**row,'modelId':model,'name':PRESETS[model]['name']},stems
