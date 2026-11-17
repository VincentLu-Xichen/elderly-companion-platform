"""Standard-library bootstrap; selects Python3.11—3.13 before installing pinned deps."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent


def compatible(candidate):
    try:
        p=subprocess.run([str(candidate),'-c','import sys;print(sys.version_info.major,sys.version_info.minor)'],
            capture_output=True,text=True,timeout=10)
        return p.returncode==0 and tuple(map(int,p.stdout.strip().split())) in {(3,11),(3,12),(3,13)}
    except (OSError,ValueError,subprocess.TimeoutExpired):return False


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--python',dest='interpreter');args=parser.parse_args()
    target=ROOT/'.venv';python=target/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if target.exists():
        if not python.is_file() or not compatible(python):parser.error('现有.venv不兼容，请使用空目录解压后重试。')
    else:
        candidates=[args.interpreter] if args.interpreter else [shutil.which(n) for n in ('python3.13','python3.12','python3.11')]+[sys.executable]
        if not args.interpreter:
            # Reuse an already-installed Codex Python when PATH points to Python3.14.
            runtimes=Path.home()/'Documents/Codex/runtimes/python'
            candidates+=sorted(runtimes.glob('cpython-3.13*/bin/python3.13'),reverse=True)
        chosen=next((p for p in candidates if p and compatible(p)),None)
        if not chosen:parser.error('需要Python3.11—3.13。安装后重试，或使用--python /路径/python3.13。')
        subprocess.check_call([str(chosen),'-m','venv',str(target)])
    subprocess.check_call([str(python),'-m','pip','install','-r',str(ROOT/'requirements.txt')])
    print('环境已准备。填写本目录.env后启动：.venv/bin/python run.py')


if __name__=='__main__':main()
