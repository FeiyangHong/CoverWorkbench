"""Read and change only CoverWorkbench's desktop shortcut icon; never launch it."""
from pathlib import Path
import json,os,subprocess,threading
from core import ROOT,read_json
LOCK=threading.Lock()
ICONS={
 'cw-signature':{'name':'音符','english':'Signature Note','description':'简洁的双音符，与工作台原标志呼应。'},
 'cw-vocal':{'name':'声波','english':'Vocal Wave','description':'声波与环形轮廓，记录人声的表达。'},
 'cw-studio':{'name':'录音室','english':'Studio Layers','description':'叠放的制作窗口，把灵感留在工作台。'}
}
def native(mode='status',icon='cw-signature'):
    exe=Path('C:/Program Files/PowerShell/7/pwsh.exe')
    if not exe.is_file():exe=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    p=subprocess.run([str(exe),'-NoProfile','-File',str(ROOT/'tools/DesktopIcon.ps1'),'-Mode',mode,'-Icon',icon],capture_output=True,encoding='utf-8-sig',errors='replace',timeout=25,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if p.returncode:raise ValueError('无法更新桌面快捷方式：'+(p.stderr.strip() or p.stdout.strip())[-500:])
    return json.loads(p.stdout.strip())
def status():
    with LOCK:state=native()
    return {**state,'variants':[{'id':key,**v,'preview':'/desktop-icons/'+key+'.png','download':'/desktop-icons/'+key+'.ico'} for key,v in ICONS.items()]}
def apply(body):
    icon=body.get('icon')
    if icon not in ICONS:raise ValueError('请选择提供的三款图标之一')
    with LOCK:return native('apply',icon)
def asset(name):
    p=Path(name)
    if p.stem not in ICONS or p.suffix not in ['.png','.ico'] or p.name!=name:raise ValueError('无效的图标文件')
    return ROOT/'assets/icons'/p.name
