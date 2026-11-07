"""Shared workspace selection for source and frozen desktop entry points."""
from pathlib import Path
import os,sys

ROOT=Path(os.environ.get('COVERWORKBENCH_ROOT') or (Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1])).resolve()

def worker(script,*args):
    if getattr(sys,'frozen',False):return [sys.executable,'--worker',script,*map(str,args)]
    return [sys.executable,str(ROOT/'app'/script),*map(str,args)]

def module(name,*args):
    return [sys.executable,'--module' if getattr(sys,'frozen',False) else '-m',name,*map(str,args)]
