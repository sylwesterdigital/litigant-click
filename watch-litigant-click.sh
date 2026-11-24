#!/usr/bin/env bash
# Litigant Click release watcher — macOS Zsh/Bash -> optional GitHub -> optional Ubuntu.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 - "$ROOT" "$@" <<'LITIGANT_WATCH_PY'
import argparse, datetime, signal, threading, fcntl, hashlib, ipaddress, json, os, plistlib, re, secrets, shlex, shutil, socket, sqlite3, stat, subprocess, sys, tempfile, time, urllib.request, zipfile
from pathlib import Path, PurePosixPath
ROOT=Path(sys.argv[1]).resolve(); sys.argv=[sys.argv[0]]+sys.argv[2:]
STATE=ROOT/'.litigant'; UPDATES=ROOT/'updates'; UPLOADS=ROOT/'uploads'; RELEASES=ROOT/'releases'; PROCESSED=UPDATES/'processed'; REJECTED=UPDATES/'rejected'
VERSION='0.1.1'; PROJECT='litigant-click'; REPO='git@github.com:sylwesterdigital/litigant-click.git'; DOMAIN='litigant.click'; ZIP_RE=re.compile(r'LITIGANT_CLICK_RELEASE_v(\d+\.\d+\.\d+)\.zip'); HOST=os.getenv('LITIGANT_SSH_HOST','root@46.62.232.64'); PORT=os.getenv('LITIGANT_SSH_PORT','333'); EXPECTED=os.getenv('LITIGANT_EXPECTED_IP','46.62.232.64')
LOCAL_PORT=8767; LABEL='com.litigant-click.local'; DATA=Path.home()/'.local/share/litigant-click'; PLIST=Path.home()/'Library/LaunchAgents'/ (LABEL+'.plist'); CURRENT=STATE/'current'; LOCAL=STATE/'local-releases'; URL=f'http://127.0.0.1:{LOCAL_PORT}'; PUBLIC='https://'+DOMAIN
class Failure(Exception): pass
class BadArchive(Failure): pass

def say(msg):
    line=datetime.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')+'  '+str(msg); print(line,flush=True)
    if STATE.is_dir():
        with (STATE/'watch.log').open('a',encoding='utf-8') as f: f.write(line+'\n')
def cmd(args, cwd=None, timeout=180, check=True, stdin=None, live=False):
    try: p=subprocess.run([str(a) for a in args],cwd=cwd,timeout=timeout,check=False,input=stdin,text=True,capture_output=not live,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'})
    except subprocess.TimeoutExpired: raise Failure(str(args[0])+' timed out')
    if check and p.returncode: raise Failure(str(args[0])+' failed (exit '+str(p.returncode)+'). '+(p.stderr or p.stdout or "See terminal output above")[-1500:])
    return p

def ver(v): return tuple(int(x) for x in v.split('.'))
def sha(data): return hashlib.sha256(data).hexdigest()
def load(name,default=None):
    try: return json.loads((STATE/name).read_text())
    except (OSError,ValueError): return default

def save(name,value):
    p=STATE/(name+'.new'); p.write_text(json.dumps(value,indent=2)+'\n'); p.chmod(0o600); os.replace(p,STATE/name)
def local_version():
    try: return json.loads((CURRENT/'version.json').read_text())['version']
    except (OSError,ValueError,KeyError): return '0.0.0'
def remote_version(): return (load('production.json',{}) or {}).get('version','0.0.0')
def validate(path,stage):
    match=ZIP_RE.fullmatch(path.name)
    if not match or path.is_symlink() or path.stat().st_size>32*1024*1024: raise BadArchive('Invalid archive name, symlink or excessive archive size')
    try:
        with zipfile.ZipFile(path) as z:
            entries=z.infolist(); names=[e.filename for e in entries if not e.is_dir()]
            if len(entries)>512 or len(names)!=len(set(names)) or sum(e.file_size for e in entries)>100*1024*1024: raise BadArchive('Archive file count, duplicate or size limit exceeded')
            for e in entries:
                parts=PurePosixPath(e.filename).parts
                if not parts or e.filename.startswith('/') or '\\' in e.filename or '..' in parts or stat.S_IFMT(e.external_attr>>16)==stat.S_IFLNK or e.flag_bits&1 or e.file_size>25*1024*1024 or (e.file_size>1024*1024 and e.file_size/max(1,e.compress_size)>250): raise BadArchive('Unsafe ZIP entry')
            m=json.loads(z.read('manifest.json')); version=match.group(1); files=m['sha256']
            required={'app/backend/app.py','app/backend/evidence.py','app/requirements.txt','app/version.json','app/deploy/install.py','app/tests/test_core.py','app/templates/base.html','app/README.md'}
            if m['project']!=PROJECT or m['version']!=version or not required.issubset(files) or set(names)!=set(files)|{'manifest.json','watch-litigant-click.sh'}: raise BadArchive('Manifest project/version/file-set mismatch')
            watcher=z.read('watch-litigant-click.sh');
            if sha(watcher)!=m['watcher_sha256']: raise BadArchive('Watcher checksum mismatch')
            for name,digest in files.items():
                if not re.fullmatch(r'app/[A-Za-z0-9_.\-/]+',name) or any(p.startswith('.') or p=='__pycache__' for p in PurePosixPath(name).parts) or not re.fullmatch(r'[a-f0-9]{64}',digest): raise BadArchive('Disallowed source path')
                payload=z.read(name)
                if sha(payload)!=digest: raise BadArchive('Checksum mismatch: '+name)
                dest=stage/name; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(payload)
            (stage/'manifest.json').write_bytes(z.read('manifest.json')); (stage/'watch-litigant-click.sh').write_bytes(watcher)
            if json.loads((stage/'app/version.json').read_text())!={'project':PROJECT,'version':version}: raise BadArchive('Application version marker mismatch')
            for py in (stage/'app').rglob('*.py'): compile(py.read_bytes(),str(py),'exec')
            cmd(['bash','-n',stage/'watch-litigant-click.sh'],timeout=10)
            program=re.search(rb"<<'LITIGANT_WATCH_PY'\n(.*?)\nLITIGANT_WATCH_PY\s*$",watcher,re.S)
            if not program: raise BadArchive('Embedded watcher missing')
            compile(program.group(1),'watcher','exec')
            if shutil.which('node'): cmd(['node','--check',stage/'app/static/app.js'],timeout=20)
            return version,m
    except (zipfile.BadZipFile,KeyError,ValueError,SyntaxError,TypeError) as e: raise BadArchive('Invalid release: '+str(e)) from e

def health(url,version=None):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url+'/api/health',timeout=4) as r: h=json.load(r)
        with opener.open(url+'/version.json',timeout=4) as r: marker=json.load(r)
        if h.get('project')==PROJECT and h.get('ok') and h.get('storage')=='sqlite' and marker.get('version')==h.get('version') and (version is None or h['version']==version): return h
    except Exception: pass
    return None

def wait_health(url,v):
    for _ in range(25):
        if health(url,v): return
        time.sleep(1)
    raise Failure('Health/version check failed: '+url)

def switch(target):
    tmp=STATE/'current.new'; tmp.unlink(missing_ok=True)
    if target is None: CURRENT.unlink(missing_ok=True)
    else: tmp.symlink_to(target); os.replace(tmp,CURRENT)

# The watcher owns the local server. The child is isolated from the terminal's
# SIGINT so the parent can stop it cleanly, including subprocesses such as OCR.
CHILD=None; READER=None
LOCAL_RUNNER="""
import logging, time
from flask import request, g
from waitress import serve
from backend.app import app
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log=logging.getLogger('litigant.http')
def route():
    return request.url_rule.rule if request.url_rule else '<unmatched>'
@app.before_request
def request_start():
    g.litigant_started=time.monotonic()
    log.info('START %s %s', request.method, route())
@app.after_request
def request_end(response):
    elapsed=(time.monotonic()-getattr(g,'litigant_started',time.monotonic()))*1000
    log.info('HTTP %s %s -> %s (%.1f ms)', request.method, route(), response.status_code, elapsed)
    return response
logging.getLogger('litigant').info('Flask application ready; listening on http://127.0.0.1:8767')
serve(app, listen='127.0.0.1:8767', threads=4, max_request_body_size=110100480)
"""
def stream_output(child):
    try:
        with (STATE/'local-service.log').open('a',encoding='utf-8') as out:
            for line in child.stdout:
                print(line,end='',flush=True); out.write(line); out.flush()
    finally:
        child.stdout.close()

def stop_child():
    global CHILD, READER
    child=CHILD; reader=READER
    if child is not None:
        try: os.killpg(child.pid,signal.SIGTERM)
        except ProcessLookupError: pass
        try: child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try: os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            child.wait(timeout=5)
        if reader: reader.join(timeout=3)
        CHILD=None; READER=None
        say('Foreground Flask application stopped')

def retire_agent():
    domain='gui/'+str(os.getuid()); service=domain+'/'+LABEL
    if cmd(['launchctl','print',service],check=False,timeout=15).returncode==0:
        say('Stopping legacy Litigant LaunchAgent')
        cmd(['launchctl','bootout',service],timeout=20)
    PLIST.unlink(missing_ok=True)

def launch(release,ai=False,model='qwen2.5:7b'):
    global CHILD, READER
    if sys.platform!='darwin': raise Failure('Local launch requires macOS')
    DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
    stop_child(); retire_agent()
    for _ in range(15):
        with socket.socket() as sock:
            sock.settimeout(.2)
            if sock.connect_ex(('127.0.0.1',LOCAL_PORT))!=0: break
        time.sleep(.2)
    else: raise Failure('Local port 8767 still occupied; refusing to kill an unrelated process')
    env={**os.environ,'LITIGANT_DATA_DIR':str(DATA),'LITIGANT_PRODUCTION':'0','LITIGANT_OLLAMA':'1' if ai else '0','LITIGANT_OLLAMA_MODEL':model,'PYTHONUNBUFFERED':'1'}
    say('START FLASK '+release.name+' | '+URL+' | live terminal output')
    CHILD=subprocess.Popen([str(release/'.venv/bin/python'),'-u','-c',LOCAL_RUNNER],cwd=release,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace',bufsize=1,start_new_session=True)
    READER=threading.Thread(target=stream_output,args=(CHILD,),daemon=True); READER.start()

def foreground_wait():
    say('Flask is running in this terminal. Ctrl+C stops the application and watcher.')
    while CHILD is not None and CHILD.poll() is None: time.sleep(1)
    raise Failure('Foreground Flask process exited; see application logs above')

def backup_local():
    src=DATA/'evidence.sqlite3'
    if src.is_file():
        dest=DATA/'deploy-backups'; dest.mkdir(mode=0o700,exist_ok=True); file=dest/('db-'+str(time.time_ns())+'.sqlite3')
        with sqlite3.connect(src) as a, sqlite3.connect(file) as b: a.backup(b)
        file.chmod(0o600)

def local_install(stage,v,args):
    if sys.platform!='darwin': raise Failure('Local installation requires macOS; use --dry-run here')
    previous=CURRENT.resolve() if CURRENT.is_symlink() else None; release=LOCAL/('v'+v)
    if previous==release and CHILD is not None and CHILD.poll() is None and health(URL,v): return
    with socket.socket() as s:
        s.settimeout(1)
        if s.connect_ex(('127.0.0.1',LOCAL_PORT))==0 and not (previous and health(URL)): raise Failure('Local port 8767 is occupied by another application')
    if previous==release: # restart rather than delete the currently installed code
        launch(release,args.ai,args.model); wait_health(URL,v); return
    if release.exists(): shutil.rmtree(release)
    shutil.copytree(stage/'app',release)
    (release/'.manifest.sha256').write_text(sha((stage/'manifest.json').read_bytes())+'\n')
    say('Building isolated Python environment and running mandatory tests')
    cmd([sys.executable,'-m','venv',release/'.venv'],timeout=180)
    py=release/'.venv/bin/python'; cmd([py,'-m','pip','install','--disable-pip-version-check','--no-input','-r',release/'requirements.txt'],timeout=900,live=True)
    cmd([py,'-m','unittest','discover','-s','tests','-v'],cwd=release,timeout=240,live=True)
    backup_local(); old=load('local.json',{}) or {}
    try:
        switch(release); launch(release,args.ai,args.model); wait_health(URL,v)
    except Exception:
        switch(previous)
        if previous:
            launch(previous,old.get('ai',False),old.get('model','qwen2.5:7b')); wait_health(URL,previous.name[1:])
        else:
            stop_child(); retire_agent()
        raise
    save('local.json',{'version':v,'previous':str(previous) if previous else None,'ai':args.ai,'model':args.model}); say('LOCAL VERIFIED '+v+' '+URL)

def ssh(script,timeout=60):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+',HOST) or not PORT.isdigit() or not 1<=int(PORT)<=65535: raise Failure('Invalid SSH configuration')
    return cmd(['ssh','-p',PORT,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',HOST,'bash','-se'],stdin='set -euo pipefail\n'+script+'\n',timeout=timeout).stdout

def deploy(stage,v,args):
    ipaddress.ip_address(EXPECTED)
    if 'SSH_READY' not in ssh('test "$(id -u)" -eq 0; command -v python3 >/dev/null; command -v systemctl >/dev/null; echo SSH_READY'): raise Failure('SSH preflight failed')
    remote='/var/www/.litigant-stage-'+v+'-'+secrets.token_hex(6); q=shlex.quote(remote)
    ssh('mkdir -p /var/www; mkdir -m 700 -- '+q)
    try:
        cmd(['scp','-r','-P',PORT,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',stage/'app',stage/'manifest.json',HOST+':'+remote+'/'],timeout=180)
        env=''
        for name in ('LITIGANT_CERTBOT_EMAIL','LITIGANT_CERTBOT_ACCOUNT','LITIGANT_INSTALL_LIBREOFFICE'):
            value=os.getenv(name)
            if value:
                if not re.fullmatch(r'[A-Za-z0-9@._+\-]+',value): raise Failure('Invalid deployment setting '+name)
                env+='export '+name+'='+shlex.quote(value)+'\n'
        # Installer verifies remote hashes, gates DNS, checks collisions and handles rollback.
        output=ssh(env+'python3 '+q+'/app/deploy/install.py --stage '+q+' --version '+shlex.quote(v)+' --expected-ip '+shlex.quote(EXPECTED),timeout=1800)
        if 'DEPLOYED '+v not in output: raise Failure('Remote installer did not confirm release')
        wait_health(PUBLIC,v); save('production.json',{'version':v,'url':PUBLIC}); say('PRODUCTION VERIFIED '+v+' '+PUBLIC)
    finally:
        try: ssh('rm -rf -- '+q,timeout=30)
        except Exception: say('WARNING: remote stage cleanup requires review')

def git_preflight(approved_watcher=None):
    if not (ROOT/'.git').is_dir(): raise Failure('Watcher must be in the cloned repository')
    if cmd(['git','branch','--show-current'],cwd=ROOT).stdout.strip()!='main': raise Failure('Only main may publish or pull')
    if cmd(['git','remote','get-url','origin'],cwd=ROOT).stdout.strip() not in (REPO,'ssh://git@github.com/sylwesterdigital/litigant-click.git'): raise Failure('Unexpected Git origin')
    changes=cmd(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT).stdout.splitlines()
    for change in changes:
        if approved_watcher and change==' M watch-litigant-click.sh' and (ROOT/'watch-litigant-click.sh').read_bytes()==approved_watcher.read_bytes(): continue
        raise Failure('Tracked or staged edits exist; refusing to overwrite or publish')

def pull():
    git_preflight(); cmd(['git','fetch','--no-tags','origin','main'],cwd=ROOT,timeout=65); cmd(['git','merge','--ff-only','FETCH_HEAD'],cwd=ROOT,timeout=65)

def publish(stage,v,m,archive):
    git_preflight(stage/'watch-litigant-click.sh'); cmd(['git','fetch','--no-tags','origin','main'],cwd=ROOT,timeout=65)
    if cmd(['git','merge-base','--is-ancestor','FETCH_HEAD','HEAD'],cwd=ROOT,check=False).returncode: raise Failure('GitHub main ahead/diverged; reconcile first')
    names=sorted(m['sha256'])+['watch-litigant-click.sh','releases/'+archive.name]
    for name in names:
        target=ROOT/name; source=archive if name.startswith('releases/') else stage/name
        if target.is_symlink() or any(p.is_symlink() for p in target.parents if p!=ROOT and ROOT in p.parents): raise Failure('Unsafe repository path')
        if target.exists() and cmd(['git','ls-files','--error-unmatch','--',name],cwd=ROOT,check=False).returncode and target.read_bytes()!=source.read_bytes(): raise Failure('Untracked source collision: '+name)
    # Only manifest-listed source and the release archive are staged; never runtime state or evidence.
    for name in names:
        target=ROOT/name; source=archive if name.startswith('releases/') else stage/name; target.parent.mkdir(parents=True,exist_ok=True)
        if source.resolve()!=target.resolve(): shutil.copy2(source,target)
    (ROOT/'watch-litigant-click.sh').chmod(0o755)
    cmd(['git','add','--',*names],cwd=ROOT)
    if cmd(['git','diff','--cached','--quiet'],cwd=ROOT,check=False).returncode==1: cmd(['git','commit','-m','Release Litigant Click v'+v],cwd=ROOT)
    cmd(['git','push','origin','main'],cwd=ROOT,timeout=160); head=cmd(['git','rev-parse','HEAD'],cwd=ROOT).stdout.strip(); remote=cmd(['git','ls-remote','origin','refs/heads/main'],cwd=ROOT,timeout=65).stdout
    if not remote.startswith(head+'\t'): raise Failure('GitHub push could not be verified')
    save('published.json',{'version':v,'commit':head}); say('GITHUB VERIFIED '+head[:12])

def setup():
    os.umask(0o077)
    for p in (STATE,LOCAL,UPDATES,UPLOADS,PROCESSED,REJECTED,RELEASES): p.mkdir(parents=True,exist_ok=True)
    STATE.chmod(0o700)
    exclude=ROOT/'.git/info/exclude'
    if exclude.exists():
        rules='\n# Litigant private runtime and inbox\n/.litigant/\n/updates/\n/uploads/\n/LITIGANT_CLICK_RELEASE_v*.zip\n/.DS_Store\n'
        if '# Litigant private runtime and inbox' not in exclude.read_text():
            with exclude.open('a') as f: f.write(rules)

def candidates(args):
    current=ver(local_version()); published=ver((load('published.json',{}) or {}).get('version','0.0.0')); prod=ver(remote_version()); files=[*UPDATES.glob('*.zip'),*UPLOADS.glob('*.zip'),*ROOT.glob('*.zip'),*RELEASES.glob('*.zip')]
    if args.deploy or args.publish: files+=list(PROCESSED.glob('*.zip'))
    out=[]
    for p in files:
        m=ZIP_RE.fullmatch(p.name)
        if not m or not p.is_file() or p.is_symlink(): continue
        v=ver(m.group(1))
        if v>current or v==current and ((args.deploy and (v>prod or v>published)) or (args.publish and v>published)) or args.dry_run: out.append((v,p))
    return sorted(out,key=lambda x:x[0],reverse=True)

def process(archive,args):
    with tempfile.TemporaryDirectory(prefix='release-',dir=STATE) as t:
        stage=Path(t); v,m=validate(archive,stage); say('VALIDATED '+archive.name+' (checksums and syntax)')
        if args.dry_run: return
        if ver(v)<ver(local_version()): raise Failure('Older release refused')
        if v==local_version() and (not (CURRENT/'.manifest.sha256').is_file() or (CURRENT/'.manifest.sha256').read_text().strip()!=sha((stage/'manifest.json').read_bytes())): raise Failure('Same-version release fingerprint mismatch; bump version')
        if ver(v)>ver(local_version()) or CHILD is None or CHILD.poll() is not None or not health(URL,v): local_install(stage,v,args)
        if args.deploy and ver(v)>ver(remote_version()):
            git_preflight(stage/'watch-litigant-click.sh'); cmd(['git','fetch','--no-tags','origin','main'],cwd=ROOT,timeout=65)
            if cmd(['git','merge-base','--is-ancestor','FETCH_HEAD','HEAD'],cwd=ROOT,check=False).returncode: raise Failure('GitHub main ahead/diverged; reconcile before Ubuntu deployment')
            deploy(stage,v,args)
        if args.publish or args.deploy:
            if ver(v)>ver((load('published.json',{}) or {}).get('version','0.0.0')): publish(stage,v,m,archive)
        if archive.parent in (UPDATES,UPLOADS,ROOT):
            dest=PROCESSED/archive.name
            if dest.exists() and sha(dest.read_bytes())!=sha(archive.read_bytes()): raise Failure('Processed archive version collision')
            os.replace(archive,dest)
        say('RELEASE COMPLETE '+v)

def main():
    ap=argparse.ArgumentParser(description='Litigant Click local-first release watcher'); actions=ap.add_mutually_exclusive_group()
    for flag in ('once','dry-run','status','tail','diagnose','rollback','server-rollback','restart-local','stop-local'): actions.add_argument('--'+flag,action='store_true')
    ap.add_argument('--deploy',action='store_true',help='Explicitly deploy to Ubuntu then publish verified source to GitHub'); ap.add_argument('--publish',action='store_true',help='Publish verified local source to GitHub without SSH'); ap.add_argument('--pull',action='store_true',help='Poll GitHub main for new committed release archives'); ap.add_argument('--interval',type=int,default=3); ap.add_argument('--ai',action='store_true',default=None); ap.add_argument('--model',default=None); args=ap.parse_args()
    if args.interval<1: ap.error('interval must be positive')
    if sys.version_info<(3,10): raise Failure('Python 3.10+ required; install Homebrew Python')
    setup()
    if args.status:
        say('Local version '+local_version()+' | '+('healthy' if health(URL) else 'not reachable')+' | '+URL); say('Last verified production '+remote_version()+' | '+PUBLIC); return 0
    if args.tail:
        for p in (STATE/'watch.log',STATE/'local-service.log'):
            if p.exists(): print('\n=== '+p.name+' ===\n'+'\n'.join(p.read_text(errors='replace').splitlines()[-70:]))
        return 0
    lock=(STATE/'watch.lock').open('w')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: raise Failure('Another watcher is running')
    if args.stop_local:
        stop_child(); retire_agent(); say('Local service stopped'); return 0
    saved=load('local.json',{}) or {}
    if args.ai is None: args.ai=saved.get('ai',False)
    if args.model is None: args.model=saved.get('model','qwen2.5:7b')
    if args.restart_local:
        if not CURRENT.is_symlink(): raise Failure('No installed release')
        old=load('local.json',{}) or {}; release=CURRENT.resolve()
        try: launch(release,args.ai,args.model); wait_health(URL,local_version())
        except Exception: launch(release,old.get('ai',False),old.get('model','qwen2.5:7b')); raise
        save('local.json',{**old,'ai':args.ai,'model':args.model}); say('Local service restarted'); foreground_wait()
    if args.diagnose:
        # No secrets, environment files, case documents or logs are printed.
        print(ssh('printf "=== Litigant infrastructure ===\\n"; command -v certbot || true; command -v nginx || true; systemctl is-active litigant-click || true; test ! -d /var/www/litigant.click || echo RELEASE_DIRECTORY_EXISTS; test ! -f /etc/letsencrypt/live/litigant.click/fullchain.pem || echo CERTIFICATE_EXISTS; getent ahosts litigant.click || true; if command -v nginx >/dev/null; then nginx -t; fi')); return 0
    if args.server_rollback:
        ssh('python3 /var/www/litigant.click/current/deploy/install.py --rollback',timeout=160); h=health(PUBLIC); save('production.json',{'version':h['version'] if h else '0.0.0'}); say('Production rollback completed; evidence and Git history unchanged'); return 0
    if args.rollback:
        old=load('local.json',{}) or {}; previous=Path(old.get('previous') or '/nonexistent'); current=CURRENT.resolve()
        if previous.parent!=LOCAL or not previous.is_dir(): raise Failure('No previous local release')
        backup_local(); switch(previous)
        try: launch(previous,old.get('ai',False),old.get('model','qwen2.5:7b')); wait_health(URL,previous.name[1:])
        except Exception: switch(current); launch(current,old.get('ai',False),old.get('model','qwen2.5:7b')); raise
        save('local.json',{**old,'version':previous.name[1:],'previous':str(current)}); say('Local rollback completed; evidence unchanged'); foreground_wait()
    say('Watcher v'+VERSION+' | '+('LOCAL + UBUNTU + GITHUB' if args.deploy else 'LOCAL + GITHUB' if args.publish else 'LOCAL ONLY'))
    if not args.dry_run and CURRENT.is_symlink():
        launch(CURRENT.resolve(),args.ai,args.model); wait_health(URL,local_version())
    last_pull=0; retry={}; restart_at=0
    while True:
        if not args.dry_run and CURRENT.is_symlink() and (CHILD is None or CHILD.poll() is not None) and time.monotonic()>=restart_at:
            restart_at=time.monotonic()+15
            say('Foreground Flask process exited; restarting current release')
            try: launch(CURRENT.resolve(),args.ai,args.model); wait_health(URL,local_version())
            except Exception as e: say('Restart failed: '+str(e))
        if args.pull and not args.dry_run and (last_pull==0 or time.monotonic()-last_pull>=60):
            try: pull(); last_pull=time.monotonic()
            except Exception as e: say('Git pull deferred: '+str(e)); last_pull=time.monotonic()
        items=candidates(args)
        if not items:
            if args.dry_run: say('No eligible release ZIP found'); return 1
            if args.once:
                if CHILD is not None and CHILD.poll() is None: foreground_wait()
                say('No eligible release ZIP found'); return 1
        else:
            v,archive=items[0]
            if args.once or args.dry_run or (time.time()-archive.stat().st_mtime>=5 and time.monotonic()>=retry.get(str(archive),0)):
                try: process(archive,args)
                except BadArchive as e:
                    say('REJECTED: '+str(e))
                    if not args.dry_run and archive.parent in (UPDATES,UPLOADS,ROOT): os.replace(archive,REJECTED/(str(time.time_ns())+'-'+archive.name))
                    if args.once or args.dry_run:return 1
                    retry[str(archive)]=time.monotonic()+90
                except Exception as e:
                    say('FAILED: '+str(e)); say('Release retained for retry; local installation is not undone by production/DNS failure')
                    if args.once or args.dry_run:return 1
                    retry[str(archive)]=time.monotonic()+90
                else:
                    if args.dry_run:return 0
                    if args.once: foreground_wait()
        time.sleep(args.interval)
if __name__=='__main__':
    def interrupted(signum,frame): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    try: sys.exit(main())
    except KeyboardInterrupt: print('\nStopping watcher and Flask application...',flush=True); sys.exit(0)
    except Exception as e: say('ERROR: '+str(e)); sys.exit(1)
    finally: stop_child()
LITIGANT_WATCH_PY
