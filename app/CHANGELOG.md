# Litigant Click — development log

## v0.1.1 — foreground watcher and live application logs

- Watcher owns the local Flask/Waitress child, streams stdout and stderr live, retires the legacy Litigant-only LaunchAgent, and shuts the child down with Ctrl+C.
- Automatic restart on successful release activation; prior release restored after failed activation. Dependency and test output visible during installation.
- HTTP request start/status/duration and safe operational logs for imports, OCR, PDF pages, search and AI retrieval/generation. No query strings, evidence text, names or prompts intentionally logged.
- Reuse existing Python and Tesseract; no Homebrew updates, package removals or FFmpeg changes.

## v0.1.0 — initial local-first release

- Private Flask workspace, local SQLite, immutable-by-convention hashed original storage, document preview and extracted text.
- PDF and image OCR, email headers and attachments, Office/native text extraction with optional LibreOffice derivatives, unsupported-file preservation.
- Exact literal multiple-string search, document-level ANY/ALL, source/type/tag/date/metadata/status/collection filters, CSV output and extracted-text highlights.
- Working bundle collections, manual chronology, notes and issue tags, disclosure-review heuristics, FTS5 ranked retrieval and opt-in local Ollama answers.
- Checksummed release archives, macOS launch agent with per-version environments, optional GitHub publication, opt-in SSH deployment with isolated Ubuntu service, HTTPS and authentication checks.

Known limitations: no formal hearing-bundle PDF export, semantic/vector search, automated gap proof, durable background ingestion, cloud AI, multi-user access, or complete legal-case analysis. First-release integration and deployment gates run on target machines.
