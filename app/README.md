# Litigant Click

Private Employment Tribunal evidence workspace — https://litigant.click/ (production only when explicitly deployed).

## First installation on macOS (Zsh)

The watcher and the release ZIP are separate deliverables. The ZIP is a trusted code release, not an evidence archive. Do not extract it into the repository manually. Do not accept code archives from untrusted parties: a checksum manifest detects corruption, not malicious authorship or a compromised repository.

Prerequisites: existing Python 3.12 recommended, Git, and Tesseract for OCR. LibreOffice is optional. The watcher does not install or upgrade Homebrew packages, FFmpeg, or system Python. Use your existing dependencies.

```zsh
export PATH="/opt/homebrew/opt/python@3.12/libexec/bin:$PATH"
cd ~/Documents/works/litigant-click
mkdir -p updates
cp ~/Downloads/watch-litigant-click.sh .
chmod 700 watch-litigant-click.sh
cp ~/Downloads/LITIGANT_CLICK_RELEASE_v0.1.1.zip updates/
./watch-litigant-click.sh
```

The watcher starts the installed Flask application in a supervised foreground child process, streams its stdout/stderr and safe HTTP route logs to the same terminal, and watches for newer ZIPs. It retires only the old Litigant LaunchAgent. It builds and tests each release in an isolated virtual environment before replacing the active process. Ctrl+C stops both watcher and app. No automatic start on login. Visit http://127.0.0.1:8767/ while the watcher runs. `--once` installs a single release then keeps the app running in the terminal until Ctrl+C; it does not continue watching for releases. `--dry-run` validates archive integrity and syntax without running the application. No Homebrew changes are made.

Logs are also appended to `.litigant/watch.log` and `.litigant/local-service.log`. HTTP logs use route templates, not query strings. Application progress logs omit case text, filenames, search terms, prompts and secrets; unexpected third-party exception traces may still include sensitive paths, so review before sharing. The UI binds only to loopback and must not be exposed publicly.

## Release watcher

From the cloned repository root:

```zsh
./watch-litigant-click.sh                  # watch updates/, uploads/, repo root, releases/; local only
./watch-litigant-click.sh --pull           # also fetch/fast-forward GitHub main every 60 seconds
./watch-litigant-click.sh --publish --once # publish verified source + release ZIP to GitHub main
./watch-litigant-click.sh --deploy --once  # local + Ubuntu + verified GitHub publication
./watch-litigant-click.sh --status        # local health and last recorded production version
./watch-litigant-click.sh --tail          # local watcher/service logs (do not share sensitive contents)
./watch-litigant-click.sh --rollback      # switch to previous local code; not evidence rollback
./watch-litigant-click.sh --stop-local
./watch-litigant-click.sh --restart-local
```

A continuously running watcher polls every three seconds by default. It selects the highest semantic numeric version; archive names must be exactly `LITIGANT_CLICK_RELEASE_vX.Y.Z.zip` (no browser duplicate suffix). Copy large releases under a temporary extension and atomically rename to `.zip` when ready. Success moves local inbox ZIPs to `updates/processed/`; invalid local ZIPs go to `updates/rejected/`. A failed install remains available for retry; the long-running watcher retries after 90 seconds. `--deploy` or `--publish` can use the already installed release in `processed/`, without reimporting evidence. New code versions must be bumped; same-version changed manifests are rejected. The watcher itself is included and checksum-verified; a newer watcher can be published with the release and takes effect after restarting the watcher process. For a local-only watcher upgrade, replace the standalone file explicitly with its trusted updated copy.

The Git workflow uses the expected SSH origin and `main`, refuses tracked/staged edits, fetches and rejects divergence, stages only the release's manifest-listed application source, watcher and ZIP under `releases/`, and verifies the pushed commit. It does not overwrite an unrelated root README, commit case evidence, or copy data to the server. `--pull` is opt-in because pulling and executing releases from a repo is a code trust decision. Git publication is also opt-in, except that `--deploy` includes it. Keep the GitHub repo private and never put evidence or credentials in it. `uploads/` is a release inbox, not an evidence import path.

## Optional local AI

```zsh
 # Use an existing Ollama installation if available.
ollama serve                         # separate terminal, unless Ollama already running
ollama pull qwen2.5:7b                # another terminal; download model weights only
./watch-litigant-click.sh --restart-local --ai --model qwen2.5:7b
```

Stop the active watcher before restart/rollback operations. The assistant retrieves SQLite FTS5-ranked excerpts and can send them to the local Ollama process at loopback only. No cloud API keys or API calls are included. Production AI is disabled. AI citations are draft text, not validated facts; always open each retrieved source and compare the original. This is keyword retrieval, not semantic/vector RAG. The model may omit context, misinterpret evidence or invent a reference. Select a locally installed model suitable for the machine's RAM.

## Ubuntu production (same host as the supplied Paint Lab workflow)

The watcher uses the same SSH destination and port as the supplied Paint Lab watcher by default, but new service, directory, port, data and certificate paths. It never copies your local private evidence. It uses your existing SSH agent/key and strict host-key verification; no SSH keys, passwords or secrets are packaged. The execution environment that produced this archive has no access to your Mac's SSH key/agent, so server changes have not been executed or verified here.

First stop any continuously running watcher. From the Mac, perform read-only infrastructure diagnostics:

```zsh
./watch-litigant-click.sh --diagnose
```

The host key must already be trusted on your Mac; if it is not, verify its fingerprint with the server provider before adding it. Do not turn off host-key checking. The domain is assumed to be exactly `litigant.click` (apex). Set the Joker.com A record to the same server IP as Paint Lab; if an AAAA record exists, remove it unless the intended server is correctly configured for IPv6. This installer deliberately requires all resolved addresses to match the configured expected IP; dual-stack deployment requires a future explicit multi-address configuration. The DNS gate runs before installing packages or changing Nginx/service configuration. If it reports DNS_PENDING, wait for propagation and retry. Port 80 must be externally accessible for ACME validation and 443 for HTTPS. The production port 18767 is loopback only, not exposed in the firewall.

```zsh
# Only if the server has no existing Let's Encrypt account:
export LITIGANT_CERTBOT_EMAIL='your-real-email@example.com'
# Optional: enable legacy Office conversion on Ubuntu (can install large packages)
export LITIGANT_INSTALL_LIBREOFFICE=1
./watch-litigant-click.sh --deploy --once
```

Do not set the placeholder email literally. If the server already has a Let's Encrypt production account, the installer reuses it without exporting its credentials; it requests a new certificate only for litigant.click. Override SSH host/port/expected IP with `LITIGANT_SSH_HOST`, `LITIGANT_SSH_PORT`, `LITIGANT_EXPECTED_IP` only if needed. An optional `LITIGANT_CERTBOT_ACCOUNT` selects an existing account; do not share account private keys. The installer checks missing system components, installs only required packages, checks domain/port/unit ownership collisions, verifies staged checksums, creates an isolated non-login service account, runs full app tests as that account, and verifies internal health, HTTPS version, unauthenticated 401 and authenticated UI. It refuses unmanaged vhost/unit conflicts and attempts rollback after activation failure. It never replaces Paint Lab configuration or reuses its certificate. Nginx configuration reload affects the shared process normally, not the existing Paint Lab site definitions. Certificate issuance can still fail for DNS, firewall, CA limits or conflicting vhosts; package installation and successful certificate issuance are not undone during application rollback. If the production release succeeds but GitHub push fails, the local/production release remains installed and the archive is retained for a later verified push.

Production HTTP Basic authentication runs over TLS. Username: `litigant`. The random password is generated on the server in `/var/lib/litigant-click/access.key` (0600). Obtain it only in your own trusted SSH terminal using your existing authenticated connection; do not paste it into GitHub, ChatGPT, shell arguments, or shared logs. Use a password manager. The `session.key` is separate and never needs to be displayed. No public signup or sharing exists. Only `/api/health` and `/version.json` are intentionally public; they expose code version and service state, not evidence. Production is a single-user deployment; use VPN/IP restrictions in addition to TLS/authentication before importing real tribunal files, if feasible. Do not expose the private evidence workspace to other users.

`--server-rollback` switches to the previously verified server code release; SQLite data, original evidence, certificates and Git history remain intact. An explicit deployment flag is required for subsequent server upgrades.

## Paths

| Purpose | macOS | Ubuntu |
|---|---|---|
| Live code | `<repo>/.litigant/current` | `/var/www/litigant.click/current` |
| Versioned code | `<repo>/.litigant/local-releases/vX.Y.Z` | `/var/www/litigant.click/releases/vX.Y.Z` |
| Venv | per local release `.venv` | `/opt/litigant-click/venvs/vX.Y.Z` |
| Evidence | `~/.local/share/litigant-click` | `/var/lib/litigant-click` |
| Service | watcher-owned foreground process | `litigant-click.service` |
| Address | `http://127.0.0.1:8767` | `https://litigant.click` |
| Nginx | not used | `/etc/nginx/sites-available/litigant.click` |
| TLS | not used | `/etc/letsencrypt/live/litigant.click/` |

SQLite snapshots are taken before updates and rollback. These are not full evidence backups. Back up the entire evidence directory (SQLite database via consistent backup, originals, derivatives, notes and secret files), using encrypted storage and an appropriate retention policy. Originals are content-addressed with SHA-256 and never modified by the application; this is not a certified forensic chain-of-custody system. The local and server repositories are independent; no evidence sync is implemented.

## Evidence features and limitations

Import up to 20 files (100 MiB total practical limit) per request. Import originals via the UI, not the Git repo. PDF text and rendered pages, image OCR, EML headers/body/attachments (bounded recursion), DOCX, XLSX, PPTX, text and optional LibreOffice conversion are supported. Unsupported files are kept with a review flag. Imported scanned material uses Tesseract if installed; failed OCR and incomplete extractions may miss evidence. LibreOffice derivatives may change pagination, and some original content (tracked changes, hidden cells, comments, embedded items) may not be captured. Do not treat OCR or generated previews as replacements for originals.

Search literal case-insensitive substrings, up to 20 lines; ALL means across a document's indexed units, ANY means at least one string. Search counts are non-overlapping occurrences. Filters include disclosure source, format, collection, manually entered document date, metadata, issue tag and index status. Click a matched unit to see extracted text highlighted and a rendered original or derivative preview. CSV output protects leading spreadsheet formula characters. Literal search scans indexed text for correctness rather than approximate retrieval; very large collections may be slower. FTS5 supports ranked assistant excerpts. Text is bounded per unit; no exhaustive assurance. Case-folded Unicode can shift snippet offsets in edge cases.

Bundle collections have virtual units; they are not a formal tribunal hearing-bundle PDF or agreed pagination. No formal bundle export, splitting, drag-and-drop, version comparison, or automatic document segmentation is implemented yet. An existing paginated PDF can be imported as one document. Chronology events are manually entered and linked to a source unit. Issue tags/notes are manual. No AI chronology, evidence matrix or automated contradiction report yet.

SAR review flags apparent dark rectangles, image-based pages, incomplete email headers, duplicates and extraction problems. These are technical heuristics, not proof that redactions are improper, that correspondence is missing, or that a SAR is legally incomplete. Attachments and email header values are extracted where present. Cropping/completeness analysis, reliable missing-attachment cross-reference, screenshot comparison, vector search and advanced forensic classification remain future work.

This first version indexes synchronously; large scanned bundles may take a long time and block an import request. A persistent queue, sandboxed converters, stronger resource limits, comprehensive malware scanning, application-level encryption, multi-user permissions, rate limiting and full security review are not included. Use trusted case files locally first. Never import suspicious executables; do not expose office/PDF parsers to untrusted public upload traffic. No legal advice or automatic tribunal filing is provided.

## Development and release creation

After `--publish`, source is visible under `app/` in Git. For local-only development copy source from the verified archive into a separate working directory (not the live runtime). Edit, update the changelog, bump version and build a trusted release from the repository root:

```zsh
python3 app/deploy/build_release.py --version 0.1.1 --output updates
./watch-litigant-click.sh --dry-run
./watch-litigant-click.sh --once
```

Do not package evidence, .env files, SQLite files, runtime state, SSH keys or tokens. The build helper packages source extensions from the defined code folders, not the evidence directory. Review the manifest and source before executing or publishing. A ZIP's SHA-256 manifest provides integrity, not a digital signature.

## Verification at delivery

The v0.1.1 foreground watcher is syntax-checked and its archive validated. Actual macOS process takeover and Flask integration tests require the target machine.

Python compilation, JavaScript syntax, Jinja template parsing, and extraction unit tests were executed in the build environment. Flask was unavailable and outbound package installation failed there; the Flask integration suite must pass on target machines before activation. Neither macOS foreground process lifecycle nor the Ubuntu SSH/Nginx/Certbot path was executed here. Production deployment is intentionally not automatic.
