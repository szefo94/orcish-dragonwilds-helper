"""Build a source-only update archive; run from any working directory."""
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1]
FILES=('README.md','Setup.cmd','Run.cmd','Update.cmd','.gitignore','.gitattributes','.editorconfig','AGENTS.md','CONTRIBUTING.md','SECURITY.md','RIGHTS.md')
DIRS=('src','tests','docs','.github','scripts')

def build():
    out=ROOT/'dist'/'OrcPresser_2.3.zip';out.parent.mkdir(exist_ok=True)
    paths=[ROOT/n for n in FILES]
    paths += [p for d in DIRS for p in (ROOT/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.log','.onnx','.npz')]
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(paths):z.write(p,Path('orcish-dragonwilds-helper')/p.relative_to(ROOT))
    print(out)
    return out
if __name__=='__main__':build()
