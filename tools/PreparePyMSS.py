"""Install curated weights into the selected Studio/source model cache, not another runtime."""
from pathlib import Path
import argparse,json,os,shutil,sys,time,urllib.request
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from core import sha,save_json,read_json
import pymss_backend,separation_jobs

def fetch(url,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_file():return
    part=target.with_suffix(target.suffix+'.part')
    for attempt in range(5):
        try:
            while True:
                offset=part.stat().st_size if part.exists() else 0
                req=urllib.request.Request(url,headers={'Range':f'bytes={offset}-{offset+8*1024*1024-1}','Accept-Encoding':'identity'})
                with urllib.request.urlopen(req,timeout=30) as response:
                    content_range=response.headers.get('Content-Range','')
                    if response.status==206:
                        start_end,total=content_range.split(' ')[1].split('/');start,end=map(int,start_end.split('-'));total=int(total)
                        if start!=offset:raise ValueError('Download server returned the wrong byte range')
                    else:
                        if offset:raise ValueError('Download server did not support resume')
                        total=int(response.headers['Content-Length']);end=total-1
                    data=response.read(end-offset+1)
                    if len(data)!=end-offset+1:raise OSError('Incomplete model download range')
                    with part.open('ab') as stream:stream.write(data)
                print(target.name,round(part.stat().st_size/1048576),'/',round(total/1048576),'MiB',flush=True)
                if part.stat().st_size==total:part.replace(target);return
        except OSError:
            if attempt==4:raise
            time.sleep(1+attempt)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--models',nargs='+',default=list(pymss_backend.PRESETS));parser.add_argument('--source',choices=['modelscope','huggingface','hf-mirror'],default='modelscope');parser.add_argument('--cancel-file');parser.add_argument('--parent-pid',type=int);args=parser.parse_args()
    sys.path.insert(0,str(ROOT/'integrations/msst'));from worker import watch_parent,watch_cancel
    if args.parent_pid:watch_parent(args.parent_pid)
    watch_cancel(args.cancel_file)
    env=pymss_backend.environment()
    if env.get('overlay'):sys.path.insert(0,env['overlay'])
    if env.get('directory') and (env['directory']/'pymss/__init__.py').is_file():sys.path.insert(0,str(env['directory']))
    from pymss import download_model,resolve_model,register_model,list_user_models
    import yaml
    class Loader(yaml.SafeLoader):pass
    Loader.add_constructor('tag:yaml.org,2002:python/tuple',lambda loader,node:tuple(loader.construct_sequence(node)))
    folder=env['models'];folder.mkdir(parents=True,exist_ok=True)
    registry_file=ROOT/'runtime/pymss/Model Registry.json';registry=read_json(registry_file) if registry_file.is_file() else {}
    try:legacy=separation_jobs.installation()[2]
    except (OSError,ValueError):legacy={}
    for ident in args.models:
        spec=pymss_backend.PRESETS[ident];print('Preparing',spec['name'],'in',folder,flush=True)
        if spec.get('catalog'):
            resolved=resolve_model(spec['catalog'],model_dir=str(folder),require_exists=False)
            model=Path(resolved['model_path']);config=Path(resolved['config_path']);typ=resolved['model_type']
            old=legacy.get(spec['catalog'])
            if model.is_file() and config.is_file():pass
            elif old and not model.exists():
                model.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old['model'],model);shutil.copy2(old['config'],config)
            else:
                last=[0]
                def progress(done,total,message=None):
                    if done-last[0]>32*1024*1024 or done==total:
                        print(spec['name'],round(done/1048576),'/',round(total/1048576),'MiB',flush=True);last[0]=done
                download_model(spec['catalog'],model_dir=str(folder),source=args.source,progress_callback=progress,timeout=45)
        else:
            revision='4e47d6662ae82eaa8b4ac4329fe66099a843b48e';base='https://huggingface.co/pcunwa/BS-Roformer-Leap/resolve/'+revision+'/'
            model=folder/'custom/Leap Xe'/Path(spec['hfFile']).name;config=model.with_name(Path(spec['hfConfig']).name);typ='bs_roformer'
            fetch(base+spec['hfConfig'],config);fetch(base+spec['hfFile'],model)
            name='cw-'+ident
            existing=next((x for x in list_user_models() if x.name==name),None)
            if existing and Path(existing.model_path).resolve()!=model.resolve():raise ValueError('Existing custom model name belongs to another path: '+name)
            if not existing:register_model(name,typ,str(model),str(config))
        conf=yaml.load(config.read_text(encoding='utf8'),Loader=Loader)
        registry[ident]={'model':str(model),'config':str(config),'modelType':typ,'stems':list(conf['training']['instruments']),'sha256':sha(model),'configSHA256':sha(config),'source':spec.get('catalog') or base}
        save_json(registry_file,registry)
        print('Ready',ident,registry[ident]['stems'],flush=True)

if __name__=='__main__':main()
