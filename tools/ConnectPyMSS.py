"""Configure an existing App/source runtime without pip-installing into it."""
from pathlib import Path
import argparse,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import settings,pymss_backend

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory');p.add_argument('--python');p.add_argument('--models');p.add_argument('--data-root');p.add_argument('--download',action='store_true');args=p.parse_args()
    values={key:value for key,value in [('pymssDirectory',args.directory),('pymssPython',args.python),('pymssModels',args.models),('pymssDataRoot',args.data_root)] if value is not None}
    if values:settings.save(values)
    env=pymss_backend.environment();python=env['python']
    if not python.is_file():raise ValueError('未找到活动 Python。请先在 PyMSS App 中准备环境，或明确指定源码环境 Python')
    code='import importlib.metadata,json,sys;print(json.dumps({"python":sys.version.split()[0],"pymss":importlib.metadata.version("pymss"),"core":importlib.metadata.version("pymss-core")}))'
    extra=[env['overlay']] if env.get('overlay') else []
    if env.get('directory') and (env['directory']/'pymss/__init__.py').is_file():extra.append(str(env['directory']))
    child_env={**os.environ,'PYTHONUTF8':'1'}
    if extra:child_env['PYTHONPATH']=os.pathsep.join(extra+[os.environ.get('PYTHONPATH','')])
    subprocess.run([str(python),'-c',code],check=True,env=child_env)
    print('Shared models:',env['models'],flush=True)
    if args.download:subprocess.run([str(python),str(ROOT/'tools/PreparePyMSS.py')],check=True,env=child_env)

if __name__=='__main__':main()
