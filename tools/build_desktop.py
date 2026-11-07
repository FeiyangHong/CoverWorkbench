"""Build a source-only Windows portable app; never copy local projects/configuration."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess,sys,zipfile,importlib.metadata

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from deployment_tools import approved

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(ROOT/'dist/desktop'));args=parser.parse_args()
    out=Path(args.output).resolve();target=out/'CoverWorkbench'
    if target.exists() and any((target/p).exists() for p in ['projects','data','config/settings.local.json','config/projects.json']):raise ValueError('输出目录已有个人工作区；请指定新的构建目录，不覆盖它')
    names=subprocess.check_output(['git','ls-files','-co','--exclude-standard','-z'],cwd=ROOT).decode().strip('\0').split('\0');names=sorted(set(n for n in names if approved(n) and (ROOT/n).is_file()))
    for name in names:
        raw=(ROOT/name).read_bytes()
        if re.search(rb'(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}|sk-proj-[A-Za-z0-9_-]{30,}',raw):raise ValueError('检测到疑似凭据，停止构建：'+name)
        try:text=raw.decode('utf-8-sig')
        except UnicodeError:continue
        if re.search(r'[A-Za-z]:[/\\]Users[/\\](?!Public|Your|<|%)[0-9]{3,}[/\\]',text):raise ValueError('检测到个人主目录，停止构建：'+name)
    work=ROOT/'work/Desktop Build';work.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name','CoverWorkbench','--icon',str(ROOT/'assets/icons/cw-signature.ico'),'--paths',str(ROOT/'app'),'--additional-hooks-dir',str(ROOT/'tools/pyinstaller-hooks'),'--distpath',str(out),'--workpath',str(work/'Build'),'--specpath',str(work)]
    for module in ['webview.platforms.edgechromium','webview.platforms.winforms','yt_dlp']+[p.stem for p in (ROOT/'app').glob('*.py')]:command+=['--hidden-import',module]
    # Optional GPL lyric/plugin engines remain in separately installed source
    # environments, instead of being redistributed inside the desktop runtime.
    for module in ['PyQt5','PyQt6','PySide2','PySide6','tkinter','pykakasi','pedalboard','soundfile','jaconv','deprecated','wrapt']:command+=['--exclude-module',module]
    command.append(str(ROOT/'app/desktop_main.py'));subprocess.run(command,cwd=ROOT,check=True)
    for name in names:
        dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
    notices=target/'Third Party Notices';notices.mkdir(exist_ok=True);packages=[]
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if not python_license.is_file():raise ValueError('CPython runtime license is missing; portable distribution was not created')
    shutil.copy2(python_license,notices/'Python-LICENSE.txt')
    excluded={'pykakasi','pedalboard','soundfile','jaconv','deprecated','wrapt'}
    for distribution in importlib.metadata.distributions():
        name=distribution.metadata.get('Name','unknown')
        if name.casefold().replace('_','-') in excluded:continue
        packages.append({'name':name,'version':distribution.version})
        for file in distribution.files or []:
            if not any(k in str(file).lower() for k in ['license','copying','notice']):continue
            source=Path(distribution.locate_file(file))
            if source.is_file() and source.stat().st_size<2_000_000:
                dest=notices/name/str(file).replace('../','').replace('..\\','');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    (notices/'Packages.json').write_text(json.dumps(packages,indent=2),encoding='utf-8')
    version=subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=ROOT).decode().strip();(target/'Build Info.json').write_text(json.dumps({'revision':version,'python':sys.version.split()[0],'platform':'windows-x64','content':'Public source and runtime only; no media, user config, model weights or native commercial plugins.'},indent=2),encoding='utf-8')
    archive=out/'CoverWorkbench-Windows-x64.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in target.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(out))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest();(out/'SHA256SUMS.txt').write_text(digest+'  '+archive.name+'\n',encoding='ascii');print(json.dumps({'folder':str(target),'zip':str(archive),'sha256':digest}))

if __name__=='__main__':main()
