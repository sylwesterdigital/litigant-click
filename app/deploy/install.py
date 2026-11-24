#!/usr/bin/env python3
"""Trusted, checksum-verified release installer for Ubuntu; no changes to Paint Lab."""
import argparse, base64, hashlib, json, os, pwd, re, secrets, shutil, socket, sqlite3, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path
DOMAIN='litigant.click'; SERVICE='litigant-click'; PORT=18767; MARK='# LITIGANT_MANAGED_V1'
BASE=Path('/var/www/litigant.click'); DATA=Path('/var/lib/litigant-click'); CURRENT=BASE/'current'; RELEASES=BASE/'releases'; UNIT=Path('/etc/systemd/system/litigant-click.service'); SITE=Path('/etc/nginx/sites-available/litigant.click'); ENABLED=Path('/etc/nginx/sites-enabled/litigant.click'); CERT=Path('/etc/letsencrypt/live/litigant.click/fullchain.pem'); KEY=CERT.with_name('privkey.pem'); VENV=Path('/opt/litigant-click/venvs')
HTTP=MARK+'''\nserver {
 listen 80;
 listen [::]:80;
 server_name litigant.click;
 location ^~ /.well-known/acme-challenge/ { root /var/www/litigant.click/acme; try_files $uri =404; }
 location / { return 503; }
}\n'''
HTTPS=HTTP.replace('return 503;', 'return 301 https://litigant.click$request_uri;')+'''server {
 listen 443 ssl;
 listen [::]:443 ssl;
 server_name litigant.click;
 ssl_certificate /etc/letsencrypt/live/litigant.click/fullchain.pem;
 ssl_certificate_key /etc/letsencrypt/live/litigant.click/privkey.pem;
 ssl_protocols TLSv1.2 TLSv1.3;
 client_max_body_size 105m;
 access_log off;
 add_header Strict-Transport-Security "max-age=31536000" always;
 location / {
  proxy_pass http://127.0.0.1:18767;
  proxy_set_header Host litigant.click;
  proxy_set_header X-Forwarded-Proto https;
  proxy_set_header Authorization $http_authorization;
  proxy_read_timeout 600s;
 }
}\n'''
UNIT_TEXT=MARK+'''\n[Unit]
Description=Litigant private evidence workspace
After=network-online.target
[Service]
User=litigant-click
Group=litigant-click
WorkingDirectory=/var/www/litigant.click/current
Environment=LITIGANT_PRODUCTION=1
Environment=LITIGANT_DATA_DIR=/var/lib/litigant-click
ExecStart=/var/www/litigant.click/current/.venv/bin/waitress-serve --listen=127.0.0.1:18767 --threads=4 --max-request-body-size=110100480 backend.app:app
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/litigant-click
[Install]
WantedBy=multi-user.target
'''
def run(*args,timeout=180,check=True,**kw):
    return subprocess.run([str(a) for a in args],timeout=timeout,check=check,**kw)
def atomic(path,text,mode=0o644):
    tmp=path.with_name('.'+path.name+'.new'); tmp.write_text(text); tmp.chmod(mode); os.replace(tmp,path)
def switch(path):
    tmp=CURRENT.with_name('.current.new'); tmp.unlink(missing_ok=True)
    if path is None: CURRENT.unlink(missing_ok=True)
    else: tmp.symlink_to(path); os.replace(tmp,CURRENT)
def dns(expected):
    try: addresses={x[4][0] for x in socket.getaddrinfo(DOMAIN,80,type=socket.SOCK_STREAM)}
    except socket.gaierror: raise RuntimeError('DNS_PENDING: domain has no usable DNS answer; retry after propagation')
    if addresses!={expected}: raise RuntimeError('DNS_PENDING: all A/AAAA records must route to the configured Ubuntu host; no changes made')
    print('DNS_OK',flush=True)
def packages():
    required={'nginx':'nginx','certbot':'certbot','tesseract':'tesseract-ocr'}; missing=[p for c,p in required.items() if not shutil.which(c)]
    # venv --help does not prove ensurepip exists on Ubuntu
    if run('dpkg-query','-W','-f=${Status}','python3-venv',capture_output=True,check=False).stdout!=b'install ok installed': missing.append('python3-venv')
    if missing:
        run('apt-get','update',timeout=240); run('apt-get','install','-y','--no-install-recommends',*missing,timeout=420)
    # LibreOffice is optional; installation can be large and is explicitly enabled.
    if os.getenv('LITIGANT_INSTALL_LIBREOFFICE')=='1' and not shutil.which('libreoffice'): run('apt-get','install','-y','--no-install-recommends','libreoffice-writer','libreoffice-calc','libreoffice-impress',timeout=600)
def collision():
    for path in (SITE,UNIT):
        if path.is_symlink() or (path.exists() and MARK not in path.read_text()): raise RuntimeError('Unmanaged configuration exists: '+str(path))
    if ENABLED.is_symlink() and ENABLED.resolve()!=SITE.resolve() or ENABLED.exists() and not ENABLED.is_symlink(): raise RuntimeError('Unmanaged enabled site')
    if CURRENT.exists() and not CURRENT.is_symlink(): raise RuntimeError('Unmanaged current path')
    for path in (BASE,DATA,RELEASES):
        if path.is_symlink(): raise RuntimeError('Unexpected symlink: '+str(path))
    out=run('nginx','-T',capture_output=True,text=True,timeout=30).stdout; chunks=re.split(r'(?m)^# configuration file (.+?):\s*$',out)
    for i in range(1,len(chunks),2):
        conf='\n'.join(x.split('#',1)[0] for x in chunks[i+1].splitlines())
        if any(DOMAIN in names.split() for names in re.findall(r'\bserver_name\s+([^;]+);',conf)) and Path(chunks[i]).resolve()!=SITE.resolve(): raise RuntimeError('Domain already served by another vhost')
    with socket.socket() as s:
        s.settimeout(1)
        if s.connect_ex(('127.0.0.1',PORT))==0:
            try:
                with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{PORT}/api/health',headers={'Host':DOMAIN}),timeout=2) as r: good=json.load(r).get('project')==SERVICE
            except Exception: good=False
            if not good or not CURRENT.is_symlink(): raise RuntimeError('Backend port is occupied')
def verify(stage,version):
    m=json.loads((stage/'manifest.json').read_text())
    if m['project']!=SERVICE or m['version']!=version: raise RuntimeError('Manifest identity mismatch')
    for name,digest in m['sha256'].items():
        p=stage/name
        if not name.startswith('app/') or '..' in Path(name).parts or p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest: raise RuntimeError('Release checksum failed')
def health(version,public=False):
    root='https://'+DOMAIN if public else f'http://127.0.0.1:{PORT}'
    for _ in range(20):
        try:
            req=urllib.request.Request(root+'/api/health',headers={'Host':DOMAIN});
            with urllib.request.urlopen(req,timeout=4) as r: h=json.load(r)
            if h.get('project')==SERVICE and h.get('version')==version and h.get('ok'): return
        except Exception: pass
        time.sleep(1)
    raise RuntimeError('Health/version verification failed')
def verify_auth():
    url='https://'+DOMAIN+'/'
    try:
        with urllib.request.urlopen(url,timeout=10): pass
    except urllib.error.HTTPError as e:
        if e.code!=401: raise RuntimeError('Unexpected unauthenticated response')
    else: raise RuntimeError('Private workspace is not protected by authentication')
    token=base64.b64encode(('litigant:'+(DATA/'access.key').read_text().strip()).encode()).decode()
    req=urllib.request.Request(url,headers={'Authorization':'Basic '+token})
    with urllib.request.urlopen(req,timeout=15) as r:
        if r.status!=200 or b'litigant-version' not in r.read(200000): raise RuntimeError('Authenticated UI verification failed')
def nginx(): run('nginx','-t',timeout=30); run('systemctl','reload','nginx',timeout=30)
def backup():
    if (DATA/'evidence.sqlite3').exists():
        folder=DATA/'deploy-backups'; folder.mkdir(mode=0o700,exist_ok=True); dest=folder/('db-'+str(time.time_ns())+'.sqlite3')
        with sqlite3.connect(DATA/'evidence.sqlite3') as src, sqlite3.connect(dest) as dst: src.backup(dst)
        dest.chmod(0o600)
def certbot_identity():
    accounts=Path('/etc/letsencrypt/accounts/acme-v02.api.letsencrypt.org/directory')
    available=[p for p in accounts.iterdir() if (p/'regr.json').is_file() and re.fullmatch(r'[A-Za-z0-9_-]+',p.name)] if accounts.is_dir() else []
    selected=os.getenv('LITIGANT_CERTBOT_ACCOUNT','').strip()
    if selected:
        if selected not in [p.name for p in available]: raise RuntimeError('Selected Certbot account does not exist')
        return ['--account',selected]
    if available: return ['--account',max(available,key=lambda p:p.stat().st_mtime).name]
    email=os.getenv('LITIGANT_CERTBOT_EMAIL','').strip()
    if re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): return ['--email',email]
    raise RuntimeError('No existing Certbot account. Set LITIGANT_CERTBOT_EMAIL before first registration')
def install(stage,version,expected):
    if os.geteuid()!=0: raise RuntimeError('Root SSH required')
    verify(stage,version); dns(expected)
    # Check pre-existing nginx before package changes when available.
    if shutil.which('nginx'): collision()
    packages(); collision()
    certopts=certbot_identity() if not (CERT.is_file() and KEY.is_file()) else []
    try: account=pwd.getpwnam(SERVICE)
    except KeyError: run('useradd','--system','--user-group','--home-dir',str(DATA),'--shell','/usr/sbin/nologin',SERVICE); account=pwd.getpwnam(SERVICE)
    for p in (BASE,RELEASES,DATA,BASE/'acme',VENV): p.mkdir(parents=True,exist_ok=True)
    for p in (BASE,RELEASES,BASE/'acme',VENV,VENV.parent): p.chmod(0o755)
    DATA.chmod(0o700); os.chown(DATA,account.pw_uid,account.pw_gid)
    for name in ('access.key','session.key'):
        path=DATA/name
        if not path.exists():
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f: f.write(secrets.token_urlsafe(48))
            os.chown(path,account.pw_uid,account.pw_gid)
        elif path.is_symlink() or not path.is_file(): raise RuntimeError('Unexpected secret file type')
        os.chown(path,account.pw_uid,account.pw_gid); path.chmod(0o600)
    previous=CURRENT.resolve() if CURRENT.is_symlink() else None; release=RELEASES/('v'+version)
    if previous and tuple(map(int,previous.name[1:].split('.')))>tuple(map(int,version.split('.'))): raise RuntimeError('Downgrade refused')
    fingerprint=hashlib.sha256((stage/'manifest.json').read_bytes()).hexdigest()
    if previous==release:
        if not (release/'.manifest.sha256').is_file() or (release/'.manifest.sha256').read_text().strip()!=fingerprint: raise RuntimeError('Same-version release fingerprint mismatch')
        health(version); health(version,True); verify_auth(); print('DEPLOYED '+version); return
    if release.exists(): shutil.rmtree(release)
    shutil.copytree(stage/'app',release)
    # SCP may transfer a private 0700 staging tree; make code readable (not writable) by service.
    for p in [release,*release.rglob('*')]: p.chmod(0o755 if p.is_dir() else 0o644)
    (release/'.manifest.sha256').write_text(fingerprint+'\n')
    # Never run pip or application tests as root; build in isolated service-owned venv.
    venv=VENV/('v'+version)
    if venv.exists(): shutil.rmtree(venv)
    venv.mkdir(); os.chown(venv,account.pw_uid,account.pw_gid)
    run('runuser','-u',SERVICE,'--','python3','-m','venv',venv,timeout=180)
    py=venv/'bin/python'; run('runuser','-u',SERVICE,'--',py,'-m','pip','install','--no-input','--disable-pip-version-check','-r',release/'requirements.txt',timeout=600)
    # Test isolated data as service user; no production case data in tests.
    run('runuser','-u',SERVICE,'--',py,'-m','unittest','discover','-s','tests','-v',cwd=release,timeout=180)
    (release/'.venv').symlink_to(venv)
    # Freeze installed code and dependencies against service-user modification.
    run('chown','-hR','root:root',venv); run('chmod','-R','go-w',venv)
    old_site=SITE.read_text() if SITE.exists() else None; old_unit=UNIT.read_text() if UNIT.exists() else None; old_enabled=ENABLED.is_symlink()
    backup()
    try:
        if not (CERT.is_file() and KEY.is_file()):
            atomic(SITE,HTTP)
            if not ENABLED.is_symlink(): ENABLED.symlink_to(SITE)
            nginx()
            # Reuse the existing ACME account, never another domain's certificate.
            run('certbot','certonly','--webroot','--non-interactive','--agree-tos',*certopts,'--deploy-hook','systemctl reload nginx','-w',BASE/'acme','-d',DOMAIN,timeout=300)
        atomic(UNIT,UNIT_TEXT); atomic(SITE,HTTPS)
        if not ENABLED.is_symlink(): ENABLED.symlink_to(SITE)
        run('nginx','-t',timeout=30); switch(release); run('systemctl','daemon-reload'); run('systemctl','enable',SERVICE); run('systemctl','restart',SERVICE); health(version); nginx(); health(version,True); verify_auth()
        if previous: atomic(BASE/'previous',str(previous))
        print('DEPLOYED '+version,flush=True)
    except Exception:
        switch(previous)
        if old_site is None: SITE.unlink(missing_ok=True)
        else: atomic(SITE,old_site)
        if not old_enabled: ENABLED.unlink(missing_ok=True)
        if old_unit is None: UNIT.unlink(missing_ok=True)
        else: atomic(UNIT,old_unit)
        run('systemctl','daemon-reload',check=False)
        if previous: run('systemctl','restart',SERVICE,check=False)
        else: run('systemctl','disable','--now',SERVICE,check=False)
        try: nginx()
        except Exception: print('ROLLBACK: nginx needs manual review',file=sys.stderr)
        raise

def rollback():
    collision(); previous=Path((BASE/'previous').read_text().strip()); current=CURRENT.resolve()
    if previous.parent!=RELEASES or not previous.is_dir(): raise RuntimeError('No valid previous release')
    backup(); switch(previous)
    try: run('systemctl','restart',SERVICE); health(previous.name[1:]); health(previous.name[1:],True); verify_auth(); atomic(BASE/'previous',str(current))
    except Exception: switch(current); run('systemctl','restart',SERVICE); raise
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--stage',type=Path); p.add_argument('--version'); p.add_argument('--expected-ip'); p.add_argument('--rollback',action='store_true'); a=p.parse_args()
    if a.rollback: rollback()
    elif a.stage and re.fullmatch(r'\d+\.\d+\.\d+',a.version or '') and a.expected_ip: install(a.stage,a.version,a.expected_ip)
    else: p.error('stage, version and expected-ip required')
