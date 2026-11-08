"""Thin client of the separately installed MSST Python API (no bundled engine/weights)."""
from pathlib import Path
import json
import os
import sys
import threading
import hashlib
import time


def watch_parent(pid):
    # A forced workbench exit must not leave this GPU worker running on Windows.
    if os.name != 'nt':
        return
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        os._exit(2)
    def monitor():
        kernel.WaitForSingleObject(handle, 0xffffffff)
        os._exit(2)
    threading.Thread(target=monitor, daemon=True).start()

def watch_cancel(path):
    if not path:return
    def monitor():
        while True:
            if Path(path).is_file():os._exit(2)
            time.sleep(.15)
    threading.Thread(target=monitor,daemon=True).start()


def run(request, meter=None):
    install = Path(request['installation'])
    sys.path.insert(0, str(install))
    os.chdir(install)
    from inference.msst_infer import MSSeparator
    import yaml
    class ModelConfigLoader(yaml.SafeLoader):
        pass
    # MSST model YAMLs use tuple literals for dimensions; permit only that inert tag.
    ModelConfigLoader.add_constructor('tag:yaml.org,2002:python/tuple',
                                     lambda loader, node: tuple(loader.construct_sequence(node)))
    results = dict(request.get('initialResults',{}))
    for index,step in enumerate(request['steps']):
        if index<request.get('completedSteps',0):continue
        with open(step['config'], encoding='utf-8') as stream:
            config = yaml.load(stream, Loader=ModelConfigLoader)
            instruments = config['training']['instruments']
        if set(instruments) != set(step['stems']):
            raise ValueError('Model stem configuration differs from the selected workflow; no output was registered')
        source = Path(results['vocals']) if step['input'] == '@vocals' else Path(step['input'])
        config_path=step['config']
        if request.get('inferenceOverrides'):
            config['inference'].update(request['inferenceOverrides'])
            config_path=str(Path(request['result']).with_name('Model.yaml'))
            # The old beartype-checked RoFormer requires tuple dimensions. The
            # input was loaded with our inert-tag SafeLoader; preserve tuples
            # when writing this owned config instead of converting them to lists.
            Path(config_path).write_text(yaml.dump(config,sort_keys=False),encoding='utf-8')
        separator = MSSeparator(model_type=step['modelType'], config_path=config_path, model_path=step['model'],
                                device='auto', device_ids=[0], output_format='wav', use_tta=False,
                                store_dirs={stem: step['folders'][role] for stem, role in step['stems'].items()},
                                audio_params={'wav_bit_depth': 'FLOAT', 'flac_bit_depth': 'PCM_24', 'mp3_bit_rate': '320k'})
        try:
            if meter:meter.loaded()
            success = separator.process_folder(str(source.parent))
            if source.name not in success:
                raise RuntimeError('MSST did not successfully process the requested input')
            for stem, role in step['stems'].items():
                output = Path(step['folders'][role]) / (source.stem + '_' + stem + '.wav')
                if not output.is_file():
                    raise RuntimeError('Missing expected stem: ' + role)
                # Only our fresh run directory is touched; never rename the user's input.
                label = {'vocals': 'Vocals', 'accompaniment': 'Instrumental', 'lead': 'Lead', 'harmony': 'Harmony'}[role]
                named = output.with_name(label + '.wav')
                if named != output:
                    if named.exists():
                        raise RuntimeError('Output name already exists: ' + label)
                    output.rename(named)
                results[role] = str(named)
            def digest(path):
                h=hashlib.sha256()
                with Path(path).open('rb') as f:
                    while block:=f.read(1024*1024):h.update(block)
                return h.hexdigest()
            checkpoint={'completedSteps':index+1,'inputSHA256':request.get('inputSHA256'),'models':request.get('modelStamps'),'outputs':{k:{'path':v,'sha256':digest(v)} for k,v in results.items()}}
            target=Path(request['result']).with_name('Checkpoint.json');temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(checkpoint),encoding='utf-8');os.replace(temporary,target)
        finally:
            separator.del_cache()
            del separator
    result = Path(request['result'])
    temp = result.with_suffix('.tmp')
    temp.write_text(json.dumps(results), encoding='utf-8')
    os.replace(temp, result)


if __name__ == '__main__':
    spec = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
    watch_parent(spec['parentPid'])
    watch_cancel(spec.get('cancelFile'))
    if spec.get('measure'):
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'app'))
        from separation_metrics import StageMeter
        import torch
        step=spec['steps'][0]
        with StageMeter(torch,step.get('name','MSST'),step['input'],Path(spec['result']).with_name('Metrics.json')) as meter:
            meter.row.update(engine='msst',torchVersion=torch.__version__,inferenceOverrides=spec.get('inferenceOverrides',{}),tta=False)
            run(spec,meter)
    else:run(spec)
