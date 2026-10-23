"""Real PowerShell 5.1 + venv launcher regression, isolated from user projects."""
from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import tempfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def main():
    if os.name!='nt':raise SystemExit('This test requires Windows')
    paths=subprocess.check_output(['git','ls-files','-co','--exclude-standard','-z'],cwd=ROOT).decode().strip('\0').split('\0')
    (ROOT/'work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'work',prefix='Windows install ') as td:
        dest=Path(td).resolve();assert dest.is_relative_to((ROOT/'work').resolve())
        for name in set(paths):
            source=ROOT/name
            if source.is_file():
                target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env={**os.environ,'COVERWORKBENCH_PORT':str(port)}
        def run(script,*args):
            # A redirected interpreter must not inherit a PIPE that blocks communicate().
            with (dest/'launcher-test.log').open('a',encoding='utf-8') as log:
                result=subprocess.run(['powershell.exe','-NoProfile','-File',str(dest/script),*args],env=env,stdout=log,stderr=log,timeout=120)
            if result.returncode:raise AssertionError((dest/'launcher-test.log').read_text(encoding='utf-8',errors='replace'))
        run('Setup.ps1','-PythonExe',sys.executable)
        try:
            run('Start.ps1','-NoBrowser')
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=5) as response:health=json.load(response)
            assert Path(health['root'])==dest
            assert int((dest/'runtime/server.pid').read_text())==health['pid']
            run('Start.ps1','-NoBrowser')  # Reuses the same owned server.
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=5) as response:assert json.load(response)['pid']==health['pid']
        finally:
            run('Stop.ps1')
        assert not (dest/'runtime/server.pid').exists()
        try:urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=2)
        except OSError:pass
        else:raise AssertionError('Stop left the test server running')
        print('PASS: Windows PowerShell 5.1 setup, venv start, repeated start and stop in a relocated path with spaces')

if __name__=='__main__':main()
