"""Public sample evaluation entry point."""
from pathlib import Path
import subprocess
import sys

if __name__=='__main__':
    subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'main.py'),'--samples',*sys.argv[1:]],check=True)
