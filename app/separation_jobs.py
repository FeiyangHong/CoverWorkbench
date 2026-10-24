"""Owned, finite MSST jobs: explicit input, explicit stem roles, register after success."""
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

LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='msst')
JOBS = {}
_SHORTCUTS = {}
PROFILES = {
    'song': ('big_beta7.ckpt', {'vocals': 'vocals', 'other': 'accompaniment'}),
    'harmony': ('mel_band_roformer_karaoke_becruily.ckpt', {'Vocals': 'lead', 'Instrumental': 'harmony'}),
}


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


def capabilities():
    try:
        install, runtime, models = installation()
        return {'available': True, 'installation': str(install), 'python': str(runtime),
                'models': {k: {'name': value[0], 'available': value[0] in models} for k, value in PROFILES.items()}}
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        return {'available': False, 'message': str(exc), 'models': {}}


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
    with lifecycle.operation('提交 MSST 分离'), LOCK:
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
        install, runtime, models = installation()
        stages = ['song', 'harmony'] if mode == 'pipeline' else [mode]
        if any(PROFILES[s][0] not in models for s in stages):
            raise ValueError('缺少此流程需要的模型 / 配置，请在自己的 MSST 中安装后再试')
        root = workspaces.outputs(p)
        number = 1
        while True:
            folder = root / 'separation' / f'Run {number:02}'
            try:
                folder.mkdir()
                break
            except FileExistsError:
                number += 1
        request = {'installation': str(install), 'parentPid': os.getpid(), 'result': str(folder / 'result.json'), 'steps': []}
        # The worker consumes a single immutable input, never a shared global input folder.
        owned = folder / 'input' / ('Input' + source.suffix.lower())
        owned.parent.mkdir()
        job = {'id': uuid.uuid4().hex, 'musicId': ident, 'mode': mode, 'harmonyInput': harmony_input, 'inputRole': role, 'status': 'queued', 'folder': str(folder),
               'created': time.time(), 'input': str(source), 'inputInfo': info, 'ownedInput': str(owned),
               'baseline': {k: v['path'] for k, v in current.items()}, 'message': '正在准备输入副本', 'outputs': {},
               'cancel': threading.Event()}
        for index, stage in enumerate(stages):
            model, stems = PROFILES[stage]
            folders = {r: str(folder / r) for r in stems.values()}
            request['steps'].append({**models[model], 'input': '@vocals' if index > 0 and harmony_input == 'vocals' else str(owned),
                                     'stems': stems, 'folders': folders})
        save_json(folder / 'request.json', request)
        JOBS[job['id']] = job
        update(job)
        try:
            POOL.submit(run, job, runtime, install)
        except Exception:
            update(job, status='failed', message='无法启动任务线程')
            raise
        return public(job)


def run(job, runtime, install):
    process = None
    try:
        update(job, status='running', message='准备输入副本；随后由本机 MSST 模型分离')
        source, owned = Path(job['input']), Path(job['ownedInput'])
        before = sha(source)
        shutil.copy2(source, owned)
        if sha(owned) != before or sha(source) != before:
            raise ValueError('输入音频在复制时发生改变，请完成保存后重试')
        update(job, inputSHA256=before, message='MSST 正在分离；模型首次加载可能需要一些时间')
        if job['cancel'].is_set():
            update(job, status='cancelled', message='已取消；已有素材保持不变')
            return
        folder = Path(job['folder'])
        with (folder / 'msst.log').open('wb') as log:
            process = subprocess.Popen([str(runtime), str(ROOT / 'integrations/msst/worker.py'), str(folder / 'request.json')],
                                       cwd=install, stdout=log, stderr=subprocess.STDOUT,
                                       env={**os.environ, 'PYTHONUTF8': '1', 'PATH': str(install / 'ffmpeg/bin') + os.pathsep + str(install / 'ffmpeg') + os.pathsep + os.environ.get('PATH', '')},
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            while process.poll() is None:
                if job['cancel'].wait(.25):
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
            raise ValueError('MSST 运行失败，请打开本次结果文件夹查看 msst.log')
        result = read_json(folder / 'result.json')
        expected = {'vocals', 'accompaniment'} if job['mode'] == 'song' else {'lead', 'harmony'} if job['mode'] == 'harmony' else {'vocals', 'accompaniment', 'lead', 'harmony'}
        if not isinstance(result, dict) or set(result) != expected:
            raise ValueError('MSST 结果种类不完整，未自动登记')
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
            update(job, status='completed', outputs=result, skipped=skipped,
                   message='分离完成，已自动登记素材' if not skipped else '分离完成；运行中手动改过的素材路径已保留，请在结果中查看')
    except Exception as exc:
        update(job, status='failed', message=str(exc))


def cancel(ident, body):
    with LOCK:
        job = JOBS.get(body.get('id'))
        if not job or job['musicId'] != ident:
            raise ValueError('本次服务中未找到这首歌的任务')
        if job['status'] in ['queued', 'running']:
            job['cancel'].set()
        return public(job)
