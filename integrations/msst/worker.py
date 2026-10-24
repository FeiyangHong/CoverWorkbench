"""Thin client of the separately installed MSST Python API (no bundled engine/weights)."""
from pathlib import Path
import json
import os
import sys
import threading


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


def run(request):
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
    results = {}
    for step in request['steps']:
        with open(step['config'], encoding='utf-8') as stream:
            instruments = yaml.load(stream, Loader=ModelConfigLoader)['training']['instruments']
        if set(instruments) != set(step['stems']):
            raise ValueError('Model stem configuration differs from the selected workflow; no output was registered')
        source = Path(results['vocals']) if step['input'] == '@vocals' else Path(step['input'])
        separator = MSSeparator(model_type=step['modelType'], config_path=step['config'], model_path=step['model'],
                                device='auto', device_ids=[0], output_format='wav', use_tta=False,
                                store_dirs={stem: step['folders'][role] for stem, role in step['stems'].items()},
                                audio_params={'wav_bit_depth': 'FLOAT', 'flac_bit_depth': 'PCM_24', 'mp3_bit_rate': '320k'})
        try:
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
    run(spec)
