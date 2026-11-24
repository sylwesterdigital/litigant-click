#!/usr/bin/env python3
"""Build a new checksummed ZIP from trusted source only. Run from the Git root."""
import argparse, hashlib, json, re, zipfile
from pathlib import Path

def build(root,version,output):
    if not re.fullmatch(r'\d+\.\d+\.\d+',version): raise ValueError('Use numeric major.minor.patch')
    app=root/'app'; watcher=root/'watch-litigant-click.sh'; target=output/('LITIGANT_CLICK_RELEASE_v'+version+'.zip')
    if target.exists(): raise FileExistsError('Release already exists; bump version or choose another output folder')
    files={}
    for folder in ('backend','templates','static','deploy','tests'):
        for p in sorted((app/folder).rglob('*')):
            if not p.is_file() or any(x.startswith('.') or x=='__pycache__' for x in p.relative_to(app).parts): continue
            if p.is_symlink() or p.suffix not in ('.py','.html','.css','.js','.json','.md','.txt'): raise ValueError('Unexpected source file: '+str(p))
            files[p.relative_to(root).as_posix()]=p.read_bytes()
    for name in ('README.md','CHANGELOG.md','requirements.txt','version.json'):
        files['app/'+name]=(app/name).read_bytes()
    files['app/version.json']=(json.dumps({'project':'litigant-click','version':version},indent=2)+'\n').encode()
    w=watcher.read_bytes(); m={'project':'litigant-click','version':version,'sha256':{n:hashlib.sha256(b).hexdigest() for n,b in sorted(files.items())},'watcher_sha256':hashlib.sha256(w).hexdigest()}
    output.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in sorted(files.items()): z.writestr(n,b)
        z.writestr('watch-litigant-click.sh',w); z.writestr('manifest.json',json.dumps(m,indent=2,sort_keys=True)+'\n')
    print(target)
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--version',required=True); p.add_argument('--root',type=Path,default=Path.cwd()); p.add_argument('--output',type=Path,default=Path('updates')); a=p.parse_args(); build(a.root.resolve(),a.version,a.output.resolve())
