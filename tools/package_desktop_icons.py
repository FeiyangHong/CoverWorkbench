from pathlib import Path
from PIL import Image
import ctypes,json,shutil,zipfile
root=Path(__file__).resolve().parents[1];assets=root/'assets/icons';delivery=root/'outputs/DesktopIconPack';delivery.mkdir(parents=True,exist_ok=True)
checks=[]
extract=ctypes.windll.user32.PrivateExtractIconsW
extract.argtypes=[ctypes.c_wchar_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(ctypes.c_uint),ctypes.c_uint,ctypes.c_uint]
extract.restype=ctypes.c_uint
ctypes.windll.user32.DestroyIcon.argtypes=[ctypes.c_void_p]
for name in ['cw-signature','cw-vocal','cw-studio']:
 p=assets/(name+'.ico');im=Image.open(p)
 assert im.ico.sizes()=={(n,n) for n in [16,20,24,32,40,48,64,96,128,256]}
 for size in [16,32,256]:
  frame=im.ico.getimage((size,size)).convert('RGBA');assert frame.getpixel((0,0))[3]<=1
  icon=ctypes.c_void_p();iconid=ctypes.c_uint();count=extract(str(p),0,size,size,ctypes.byref(icon),ctypes.byref(iconid),1,0)
  assert count==1 and icon.value, f'Windows icon extraction failed: {name} {size}'
  ctypes.windll.user32.DestroyIcon(icon)
 for ext in ['.svg','.png','.ico']:shutil.copy2(assets/(name+ext),delivery/(name+ext))
 checks.append({'icon':name,'sizes':10,'transparentCorners':True,'nativeWindowsExtract16_32_256':True})
shutil.copy2(assets/'IconCollection.png',delivery/'IconCollection.png')
readme='''CoverWorkbench Desktop Icons

01 cw-signature.ico - 音符（已设为默认桌面图标）
02 cw-vocal.ico - 声波
03 cw-studio.ico - 录音室

桌面快捷方式：%USERPROFILE%/Desktop/CoverWorkbench.lnk
图标目录：<checkout>/assets/icons
启动方式：调用现有 Start.vbs；本地服务未启动时先启动，再打开默认浏览器。

更换图标：右键桌面快捷方式 → 属性 → 更改图标 → 浏览对应 ICO 文件。
也可以运行项目 tools/InstallDesktopShortcut.ps1 -Icon cw-vocal（或 cw-studio / cw-signature）。

每个 ICO 内含 16、20、24、32、40、48、64、96、128、256 像素透明图层。
SVG 是可编辑源文件，PNG 为 1024px 预览。不要删除永久图标目录，快捷方式引用它。
'''
(delivery/'README.txt').write_text(readme,encoding='utf-8-sig');(assets/'README.txt').write_text(readme,encoding='utf-8-sig')
with zipfile.ZipFile(delivery.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED) as z:
 for p in delivery.iterdir():z.write(p,'DesktopIconPack/'+p.name)
(root/'reports/desktop-icons.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
print(json.dumps(checks))
