"""Owned PyMSS/MSST jobs: explicit input and stems, register after success."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
import shutil
import subprocess
import threading
import time
import uuid

from core import ROOT, read_json, save_json, sha
import daw
import lifecycle
import project_assets
import settings
import workspaces
import pymss_backend
import separation_options

LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='msst')
JOBS = {}
_SHORTCUTS = {}
PROFILES = {
    'song': ('big_beta7.ckpt', {'vocals': 'vocals', 'other': 'accompaniment'}),
    'harmony': ('mel_band_roformer_karaoke_becruily.ckpt', {'Vocals': 'lead', 'Instrumental': 'harmony'}),
}

def model_stamp(step):
    return {key:[str(Path(step[key]).resolve()),Path(step[key]).stat().st_size,Path(step[key]).stat().st_mtime_ns] for key in ['model','config']}


def installation():
    values = settings.load()
    directory = values.get('msstDirectory', '')
    launcher = values.get('msstLauncher', '')
    if not directory and launcher:
        target = Path(launcher)
        if target.suffix.lower() == '.lnk' and os.name == 'nt' and target.is_file():
            key = (str(target), target.stat().st_mtime_ns)
            if key not in _SHORTCUTS:
                script = '(New-Object -ComObject WScript.Shell).CreateShortcut($env:CW_MSST_LINK).TargetPath'
                result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                        env={**os.environ, 'CW_MSST_LINK': str(target)}, capture_output=True,
                                        encoding='utf-8', errors='replace', timeout=8,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                _SHORTCUTS[key] = result.stdout.strip() if result.returncode == 0 else ''
            target = Path(_SHORTCUTS[key])
        if target.is_file():
            directory = str(target.parent)
    if not directory:
        raise ValueError('请在 MSST 服务设置中选择安装目录，或设置其启动程序 / 快捷方式')
    install = Path(daw.clean_path(directory))
    if not install.is_absolute() or str(install).startswith(('\\\\', '//')) or not install.is_dir():
        raise ValueError('请选择存在的本机 MSST 安装目录')
    install = install.resolve()
    runtime = values.get('msstPython') or next((str(install / p) for p in
              ['workenv/python.exe', '.venv/Scripts/python.exe', 'venv/Scripts/python.exe', '.venv/bin/python']
              if (install / p).is_file()), '')
    if not runtime or not Path(runtime).is_file() or not (install / 'inference/msst_infer.py').is_file():
        raise ValueError('未找到 MSST Python 运行环境或 inference/msst_infer.py；请检查安装目录 / Python 路径')
    models = {}
    for index in ['data_backup/msst_model_map.json', 'config_unofficial/unofficial_msst_model.json']:
        if not (install / index).is_file():
            continue
        for category, entries in read_json(install / index).items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict) or entry.get('name') not in {v[0] for v in PROFILES.values()}:
                    continue
                weight = install / 'pretrain' / category / entry['name']
                config = (install / entry.get('config_path', '').replace('\\', '/')).resolve()
                if (weight.is_file() and config.is_file() and config.is_relative_to(install)
                        and entry.get('model_type') in ['mel_band_roformer', 'bs_roformer']):
                    models[entry['name']] = {'model': str(weight), 'config': str(config), 'modelType': entry['model_type']}
    return install, Path(runtime).resolve(), models


def legacy_capabilities():
    try:
        install, runtime, models = installation()
        return {'available': True, 'installation': str(install), 'python': str(runtime),
                'models': {k: {'name': value[0], 'available': value[0] in models} for k, value in PROFILES.items()}}
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        return {'available': False, 'message': str(exc), 'models': {}}


def capabilities():
    engines={'msst':legacy_capabilities(),'pymss':pymss_backend.capabilities()}
    selected=settings.load().get('separationEngine','pymss')
    if not engines[selected]['available'] and engines['msst']['available']:selected='msst'
    current=engines[selected]
    defaults=separation_options.defaults(settings.load())
    models=current['models'] if selected=='msst' else {stage:{'name':pymss_backend.PRESETS[key]['name'],'available':current['models'][key]['available']} for stage,key in [('song',defaults['songModel']),('harmony',defaults['harmonyModel'])]}
    return {**current,'engine':selected,'engines':engines,'models':models,'defaults':defaults}


def public(job):
    return copy.deepcopy({k: v for k, v in job.items() if k not in ['cancel', 'process']})


def update(job, **fields):
    with LOCK:
        job.update(fields)
        save_json(Path(job['folder']) / 'job.json', public(job))


def history(ident):
    p = project_assets.project(ident)
    rows = {}
    for file in (workspaces.root(p) / 'separation').glob('Run */job.json'):
        try:
            job = read_json(file)
            if job.get('musicId') != ident:
                continue
            if job.get('status') in ['queued', 'running']:
                job.update(status='interrupted', message='上次服务中断；未登记未完成结果。请检查日志后重新提交。')
            rows[job['id']] = job
        except (ValueError, OSError, KeyError):
            continue
    with LOCK:
        rows.update({k: public(j) for k, j in JOBS.items() if j['musicId'] == ident})
    return sorted(rows.values(), key=lambda j: j['created'], reverse=True)[:30]


def submit(ident, body):
    with lifecycle.operation('提交素材分离'), LOCK:
        p = project_assets.project(ident)
        if any(j['status'] in ['queued', 'running'] for j in JOBS.values()):
            raise ValueError('已有工作台分离任务，请完成或取消后再开始，避免同时占用显存')
        mode = body.get('mode', 'song')
        if mode not in ['song', 'pipeline', 'harmony']:
            raise ValueError('请选择完整人声 + 伴奏、两步分离，或主声 + 和声')
        current = project_assets.status(ident)['assets']
        harmony_input = body.get('harmonyInput', 'vocals')
        if harmony_input not in ['vocals', 'source']:
            raise ValueError('请选择 karaoke 使用完整人声或原歌曲')
        role = harmony_input if mode == 'harmony' else 'source'
        source = daw.local(body.get('input') or current[role]['path'], {'.wav', '.flac'})
        info = daw.media_info(source)
        engine=body.get('engine') or capabilities()['engine']
        if engine not in ('msst','pymss'):raise ValueError('请选择 PyMSS 或旧 MSST 引擎')
        install, runtime, models = pymss_backend.installation() if engine=='pymss' else installation()
        stages = ['song', 'harmony'] if mode == 'pipeline' else [mode]
        defaults=separation_options.defaults(settings.load())
        song_model=body.get('songModel',defaults['songModel']);harmony_model=body.get('harmonyModel',defaults['harmonyModel'])
        quality=body.get('quality',defaults['quality'])
        batch_size=separation_options.batch_size(body.get('batchSize',defaults['batchSize'])) if engine=='pymss' else None
        tta=separation_options.tta(body.get('tta',defaults['tta'])) if engine=='pymss' else None
        if quality not in ('high','balanced','model'):raise ValueError('请选择高质量、平衡或模型默认参数')
        if engine=='msst' and any(PROFILES[s][0] not in models for s in stages):
            raise ValueError('缺少此流程需要的模型 / 配置，请在自己的 MSST 中安装后再试')
        # Validate model choices before creating a run directory.
        if engine=='pymss':
            for stage in stages:pymss_backend.step(song_model if stage=='song' else harmony_model,stage,models)
        root = workspaces.outputs(p)
        number = 1
        while True:
            folder = root / 'separation' / f'Run {number:02}'
            try:
                folder.mkdir()
                break
            except FileExistsError:
                number += 1
        request = {'installation': str(install), 'parentPid': os.getpid(),'cancelFile':str(folder/'Cancel.requested'), 'result': str(folder / 'result.json'), 'steps': []}
        # The worker consumes a single immutable input, never a shared global input folder.
        owned = folder / 'input' / ('Input' + source.suffix.lower())
        owned.parent.mkdir()
        job = {'id': uuid.uuid4().hex, 'musicId': ident, 'mode': mode, 'harmonyInput': harmony_input, 'inputRole': role, 'status': 'queued', 'folder': str(folder),
               'created': time.time(), 'engine':engine,'quality':quality,'batchSize':batch_size,'tta':tta,'songModel':song_model,'harmonyModel':harmony_model,'input': str(source), 'inputInfo': info, 'ownedInput': str(owned),
               'baseline': {k: v['path'] for k, v in current.items()}, 'message': '正在准备输入副本', 'outputs': {},
               'cancel': threading.Event()}
        for index, stage in enumerate(stages):
            if engine=='pymss':
                selected,stems=pymss_backend.step(song_model if stage=='song' else harmony_model,stage,models)
            else:
                model, stems = PROFILES[stage];selected=models[model]
            folders = {r: str(folder / r) for r in stems.values()}
            request['steps'].append({**selected, 'input': '@vocals' if index > 0 and harmony_input == 'vocals' else str(owned),
                                     'stems': stems, 'folders': folders})
        request['engine']=engine
        if engine=='pymss':
            request.update(inferenceParams={'batch_size':batch_size},tta=tta)
            env=pymss_backend.environment();request['sourceRoot']=str(env['directory'] or '')
            request['overlay']=env.get('overlay')
            if quality!='model':request['overlapFraction']=.875 if quality=='high' else .5
        save_json(folder / 'request.json', request)
        if body.get('resumeFrom') and mode=='pipeline':
            old=next((j for j in history(ident) if j['id']==body['resumeFrom'] and j['status'] in ('failed','cancelled','interrupted')),None)
            checkpoint=Path(old['folder'])/'Checkpoint.json' if old else None
            if checkpoint and checkpoint.is_file():
                data=read_json(checkpoint);outputs=data.get('outputs',{})
                if data.get('completedSteps',0)>=1 and data.get('engine','msst')==engine and data.get('overlapFraction')==request.get('overlapFraction') and (engine!='pymss' or (data.get('batchSize',1)==batch_size and data.get('tta',False)==tta)) and data.get('inputSHA256')==sha(source) and data.get('models',[None])[0]==model_stamp(request['steps'][0]) and set(outputs)>={'vocals','accompaniment'}:
                    for role in ['vocals','accompaniment']:
                        f=Path(outputs[role]['path'])
                        if not f.is_file() or not f.resolve().is_relative_to(Path(old['folder']).resolve()) or sha(f)!=outputs[role]['sha256']:raise ValueError('已完成分离步骤的输出已改变，无法复用；请重新分离')
                    job['resumeOutputs']={r:outputs[r]['path'] for r in ['vocals','accompaniment']};job['resumeHashes']={r:outputs[r]['sha256'] for r in ['vocals','accompaniment']};job['resumedFrom']=old['id']
        JOBS[job['id']] = job
        update(job)
        try:
            POOL.submit(run, job, runtime, install)
        except Exception:
            update(job, status='failed', message='无法启动任务线程')
            raise
        return public(job)


def run(job, runtime, install):
    import task_resources
    def check():
        if job['cancel'].is_set():raise InterruptedError('已取消，已有分离结果保留')
    try:
        with task_resources.claim(check,lambda:update(job,message='等待计算资源')):
            return _run(job,runtime,install)
    except InterruptedError as error:update(job,status='cancelled',message=str(error))

def _run(job, runtime, install):
    process = None
    engine_name='PyMSS' if job.get('engine')=='pymss' else 'MSST'
    try:
        update(job, status='running', message=f'准备输入副本；随后由本机 {engine_name} 模型分离')
        source, owned = Path(job['input']), Path(job['ownedInput'])
        before = sha(source)
        shutil.copy2(source, owned)
        if sha(owned) != before or sha(source) != before:
            raise ValueError('输入音频在复制时发生改变，请完成保存后重试')
        update(job, inputSHA256=before, message=f'{engine_name} 正在分离；模型首次加载可能需要一些时间')
        if job['cancel'].is_set():
            update(job, status='cancelled', message='已取消；已有素材保持不变')
            return
        folder = Path(job['folder'])
        request=read_json(folder/'request.json');request['inputSHA256']=before;request['modelStamps']=[model_stamp(s) for s in request['steps']]
        if job.get('resumeOutputs'):
            initial={}
            for role,value in job['resumeOutputs'].items():
                target=folder/role/({'vocals':'Vocals','accompaniment':'Instrumental'}[role]+'.wav');target.parent.mkdir(exist_ok=True);shutil.copy2(value,target)
                if sha(target)!=job['resumeHashes'][role] or sha(value)!=job['resumeHashes'][role]:raise ValueError('复用的分离结果在排队期间改变，请重新分离')
                initial[role]=str(target)
            request.update(initialResults=initial,completedSteps=1)
        save_json(folder/'request.json',request)
        with (folder / 'msst.log').open('wb') as log:
            process = subprocess.Popen([str(runtime), str(ROOT / ('integrations/pymss/worker.py' if job.get('engine')=='pymss' else 'integrations/msst/worker.py')), str(folder / 'request.json')],
                                       cwd=install, stdout=log, stderr=subprocess.STDOUT,
                                       env={**os.environ, 'PYTHONUTF8': '1', 'PATH': str(Path(settings.executable('ffmpeg',False)).parent) + os.pathsep + str(install / 'ffmpeg/bin') + os.pathsep + str(install / 'ffmpeg') + os.pathsep + os.environ.get('PATH', '')},
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            while process.poll() is None:
                if job['cancel'].wait(.25):
                    (folder/'Cancel.requested').write_text('cancel',encoding='ascii')
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    break
        if job['cancel'].is_set():
            update(job, status='cancelled', message='已取消；未登记本次结果，已有素材保持不变')
            return
        if process.returncode != 0:
            raise ValueError(engine_name+' 运行失败，请打开本次结果文件夹查看 msst.log')
        result = read_json(folder / 'result.json')
        expected = {'vocals', 'accompaniment'} if job['mode'] == 'song' else {'lead', 'harmony'} if job['mode'] == 'harmony' else {'vocals', 'accompaniment', 'lead', 'harmony'}
        if not isinstance(result, dict) or set(result) != expected:
            raise ValueError(engine_name+' 结果种类不完整，未自动登记')
        for role, value in result.items():
            file = daw.local(value, {'.wav'})
            if file.resolve().parent != (folder / role).resolve():
                raise ValueError('分离结果不在对应的项目目录中')
            info = daw.media_info(file)
            if abs(info['duration'] - job['inputInfo']['duration']) > .2 or info['duration'] <= 0:
                raise ValueError('分离音频时长与输入不符，未自动登记')
        values = dict(result)
        input_role = job['inputRole']
        if job['baseline'].get(input_role) != job['input']:
            values[input_role] = str(owned)
        with LOCK:
            if job['cancel'].is_set():
                update(job, status='cancelled', message='已取消；本次结果保留在文件夹，未登记')
                return
            skipped = project_assets.register_generated(job['musicId'], values, job['baseline'])
            metrics=read_json(folder/'Metrics.json') if (folder/'Metrics.json').is_file() else []
            update(job, status='completed', outputs=result, skipped=skipped,metrics=metrics,
                   message='分离完成，已自动登记素材' if not skipped else '分离完成；运行中手动改过的素材路径已保留，请在结果中查看')
    except Exception as exc:
        folder=Path(job['folder'])
        try:metrics=read_json(folder/'Metrics.json') if (folder/'Metrics.json').is_file() else []
        except (OSError,ValueError):metrics=[]
        try:log=(folder/'msst.log').read_text(encoding='utf8',errors='replace')[-1000000:]
        except OSError:log=''
        capacity='out of memory' in log.lower() or 'cuda_error_out_of_memory' in log.lower()
        message='显存不足；本次结果未登记。请降低 batch size 后重试，已有素材保留。' if capacity else str(exc)
        update(job, status='failed', message=message,metrics=metrics,failureCategory='capacity' if capacity else 'runtime')


def cancel(ident, body):
    with LOCK:
        job = JOBS.get(body.get('id'))
        if not job or job['musicId'] != ident:
            raise ValueError('本次服务中未找到这首歌的任务')
        if job['status'] in ['queued', 'running']:
            job['cancel'].set()
        return public(job)
