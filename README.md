# Secure File Vault

A small web app where logged-in users upload, preview, download, rename, replace and
delete **PDF and image files**. Every file is **encrypted at rest** with Fernet: the
server's disk only ever holds ciphertext. All users share one file pool and can read
every file, but only a file's uploader or an admin can change or delete it. Admins can
export all encrypted files as a ZIP, and someone holding the key can decrypt that
export offline with `backend/decrypt_tool.py`.

- **Backend:** Python 3.12, Django 5.2 LTS, Django REST Framework, JWT (simplejwt), `cryptography` (Fernet)
- **Frontend:** React 19 + Vite, React Router, axios, Bootstrap 5
- **Database:** SQLite by default; MySQL optional via `DATABASE_URL`

Deployment to PythonAnywhere is in **[DEPLOY.md](DEPLOY.md)**.

---

## Architecture

```
 Browser (React app)
   │  JWT in "Authorization: Bearer ..." header
   │  (dev: Vite on :5173 calls :8077/api with CORS;  prod: same site, /api)
   ▼
 Django + DRF ─────────────────────────────────────────────────────────────
   │ config/urls.py
   │   /api/auth/...   accounts/  register (throttled), login (throttled), refresh, me
   │   /api/files/...  files/views.py  FileRecordViewSet
   │                     ├─ permissions.py  IsOwnerOrAdmin  (write = owner or admin → else 403)
   │                     ├─ validation.py   magic bytes, size, names   (→ 400)
   │                     ├─ export.py       ZIP of .enc + manifest.json (admin only)
   │                     └─ models.py       FileRecord (metadata only, no file content)
   │   /admin/         Django admin
   │   /static/...     React build + admin CSS (WhiteNoise / PythonAnywhere static mapping)
   │   everything else → frontend/dist/index.html  (React Router)
   │
   ├─ files/crypto.py   encrypt_bytes / decrypt_bytes  ← the ONLY place Fernet is used
   │                     key = FERNET_KEY from backend/.env
   ├─ files/storage.py  save_encrypted / read_decrypted / delete_file
   │                     names = <uuid4>.enc, atomic write (temp file → fsync → rename)
   ▼
 backend/storage/<uuid>.enc  (ciphertext only)      db.sqlite3 (names, owner, sha256, ...)

 Offline:  vault-export-YYYY-MM-DD.zip ──► decrypt_tool.py (+ key) ──► original files, sha256-verified
```

**Upload, step by step:** browser pre-check (type, ≤ 10 MB) → `POST /api/files/`
(multipart, kept in memory) → `validation.py` checks the real content → `encrypt_bytes`
→ `storage/<uuid>.enc` → `FileRecord` row. **Preview/download:** read `.enc` →
`decrypt_bytes` in memory → response (`inline` / `attachment`). Plaintext is never
written to disk.

---

## Features

- Register / log in (JWT access + refresh tokens, silent auto-refresh, one refresh even
  for many parallel requests). Login and register are rate limited (5/min per IP).
- Dashboard: card grid with type icon, size, date and uploader; search (debounced),
  type filter and pagination, all kept in the URL (reload and Back work).
- Preview PDFs and images in a modal; download with the original file name.
- Upload by file picker or drag-and-drop, with a progress bar and instant checks.
- Rename (the extension is kept), replace the content (same type only), delete with
  confirmation. Buttons only appear on files you may change; the API enforces it anyway.
- Admins: "Export all" → ZIP of every encrypted file + `manifest.json` (with SHA-256).
- `seed_files`: 100 realistic demo files (50 PDFs with tables, 50 PNG/JPG images).
- `decrypt_tool.py`: standalone offline decryptor that verifies every file.

---

## Security design

### Encryption at rest
- **Fernet** (from `cryptography`): AES-128-CBC + HMAC-SHA256. It is *authenticated*, so
  a modified `.enc` file is detected and refused, not decrypted into garbage.
- Uploads are kept **in memory only** (`FILE_UPLOAD_HANDLERS = [MemoryFileUploadHandler]`).
  Django's default would write uploads over 2.5 MB to a temp file: plaintext on disk.
- `.enc` files are written atomically (temp file → `fsync` → `os.replace`); the temp
  file only ever holds ciphertext.
- Stored names are random `<uuid4>.enc`; user-chosen names live only in the database,
  and `storage.py` refuses any other name, so user input never reaches a file path.
- `storage/` is not under any static/media URL: the only way to a file is an
  authenticated API view.

### Key handling
- `FERNET_KEY` and `SECRET_KEY` come from `backend/.env` (git-ignored), never from code.
- Django **refuses to start** if `FERNET_KEY` is missing or invalid.
- **Losing `FERNET_KEY` means losing every file. There is no recovery.** Keep a copy
  in a password manager, outside the server.
- The export ZIP never contains the key (a test scans every entry and the raw ZIP for
  it). The key goes to the mentor separately.
- `decrypt_tool.py` refuses `--key` on the command line (it would leak into shell
  history and `ps`); it reads `FERNET_KEY` from the environment or `--key-file`.

### Permissions
- Every endpoint needs a valid JWT (`IsAuthenticated`), except register/login/refresh.
- **Read** (list, preview, download): every logged-in user, every file (shared pool).
- **Write** (rename, replace, delete): only the uploader or an admin, enforced by
  `IsOwnerOrAdmin` → **403** for anyone else, whatever the frontend shows. The API also
  sends a `can_edit` flag, so the UI only shows buttons that will work.
- Export: admins only (`IsAdminUser`).
- Register can never create an admin (`is_staff` / `is_superuser` in the request are ignored).

### Upload checks (`files/validation.py`, each failure → 400 with a clear message)
- The **content** decides the type (magic bytes `%PDF-`, PNG, JPEG); the browser's
  Content-Type is ignored, and the extension must match the content.
- Max 10 MB, checked from `Content-Length` before the body is even parsed. Empty files rejected.
- Names: folder parts dropped (`../../x` → `x`), control characters removed (incl. the
  right-to-left override trick), max 255 characters.
- Rename keeps the real extension (`hack.exe` → `hack.pdf`). Replace must keep the type.
- Download names are sent safely in `Content-Disposition` (quoted / RFC 5987).

### Production hardening (`DEBUG=False`)
- `manage.py check --deploy` is clean (a test runs it): HTTPS redirect, secure cookies,
  HSTS, `SECURE_PROXY_SSL_HEADER` for PythonAnywhere's proxy, `ALLOWED_HOSTS`,
  `CSRF_TRUSTED_ORIGINS`, `X-Frame-Options: DENY`, `nosniff`.
- Rate limiting uses the real client IP behind the proxy (`NUM_PROXIES=1`), and a
  faked `X-Forwarded-For` header can't reset the limit (tested).
- Unknown `/api/...` URLs return JSON 404s, never an HTML page.
- File responses send `Cache-Control: private, no-store`.

---

## Local setup

Needs **Python 3.12** and **Node ≥ 20.19**. Python via [uv](https://docs.astral.sh/uv/) (no sudo):
`curl -LsSf https://astral.sh/uv/install.sh | sh && uv python install 3.12`.

```bash
# 1. Backend
cd backend
uv venv --python 3.12 --seed .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
#    edit .env: set SECRET_KEY and FERNET_KEY (commands to generate them are in the file)
python manage.py migrate
python manage.py createsuperuser      # the admin; seeded files belong to this user
python manage.py seed_files           # 100 demo files (~16.5 MB), safe to run twice
python manage.py runserver 8077       # http://localhost:8077

# 2. Frontend (second terminal)
cd frontend
npm install
cp .env.example .env                  # VITE_API_URL=http://localhost:8077/api
npm run dev                           # open http://localhost:5173
```

The port 5173 must match `FRONTEND_URL` in `backend/.env` (CORS). Useful extras:
`python manage.py seed_files --count 10`, `python manage.py seed_files --reset`
(removes only seeded files).

**Production-like run locally** (Django serves the built app, no Vite):
```bash
cd frontend && npm run build          # uses .env.production: VITE_API_URL=/api
cd ../backend && python manage.py collectstatic --noinput
python manage.py runserver 8077       # with DEBUG=True: open http://localhost:8077
```

---

## Running the tests

```bash
cd backend && source .venv/bin/activate && python manage.py test   # 164 tests
cd frontend && npm test                                            # 84 tests (Vitest)
cd frontend && npm run lint && npm run build
```

- Backend tests cover crypto, storage, upload checks, every API endpoint incl.
  401/403/404, ownership (user B can't delete A's file, but can read it), export
  (no key in the ZIP), seeding, `decrypt_tool.py`, the production routing and the
  deploy check.
- Frontend tests use a fake axios adapter, so the real interceptors (token refresh) run
  without a network: login/register, routing, dashboard URL state, preview blob
  handling, upload progress, rename/replace/delete incl. 403 and 400 field errors.

---

## Demo script (for the mentor)

About 10 minutes. Log in as the admin (the `createsuperuser` account).

1. **Dashboard.** 100 seeded files, 20 per page. Search `invoice`, filter Images, go
   to page 2, reload: the same view comes back (state is in the URL). Back works too.
2. **Preview** `report_sales_q2.pdf` and a photo. *Talking point:* the browser gets the
   file as a blob through the API with the JWT; the server decrypts it in memory.
3. **Show the ciphertext on disk:**
   ```bash
   cd backend && ls storage | head -3            # random <uuid>.enc names
   head -c 64 storage/$(ls storage | head -1); echo   # gAAAAA... Fernet token, not a PDF
   ```
4. **Upload** a PDF (drag-and-drop). Then try a `.txt` renamed to `.pdf`: the browser
   accepts it, the backend rejects it by content (magic bytes).
5. **Rename** it to `notes.exe` → saved as `notes.pdf`. **Replace** it with another PDF;
   try an image: refused (same type only).
6. **Permissions.** In a private window, register a second user. They see every file
   but no Edit/Delete buttons. Show the API refusing anyway:
   ```bash
   # use the second user's access token from the browser (DevTools → Application → localStorage → vault.access)
   curl -i -X DELETE -H "Authorization: Bearer <token>" http://localhost:8077/api/files/1/   # → 403
   ```
7. **Export.** As admin, click **Export all** → `vault-export-YYYY-MM-DD.zip`. Unzip it:
   `<uuid>.enc` files (still encrypted), `manifest.json` (original names, sizes,
   SHA-256), `README.txt`. *The key is not in the ZIP.*
8. **Decrypt offline** with `decrypt_tool.py` (only needs Python + `cryptography`; no
   Django, no database). The key is handed over separately, never pasted on the command line:
   ```bash
   unzip vault-export-*.zip -d vault-export
   read -rs FERNET_KEY && export FERNET_KEY      # paste the key; it is not shown or saved in history
   python backend/decrypt_tool.py vault-export/ --out decrypted/
   #     ✓ verified   report_sales_q2.pdf  (48.3 KB)
   #   ...
   #   Summary: 100 ok, 0 failed, 0 missing
   ls decrypted/ | head
   ```
   (Or `--key-file key.txt`. On Windows PowerShell: `$env:FERNET_KEY = Read-Host -MaskInput`.)
9. **Tamper test.** Change one byte of a `.enc` in the export and run the tool again:
   that file is `✗ FAILED`, the rest still decrypt, exit code 1. With a wrong key, every
   file fails with a clear message; nothing wrong is written.

---

## Known limitations

- **One shared pool by design:** every logged-in user can read every file. Only
  changes are restricted.
- **Tokens in `localStorage`:** simple, but readable by injected JavaScript if there
  were ever an XSS bug. An HttpOnly cookie would be safer but needs CSRF handling.
- **Whole files in memory:** encryption and decryption happen on the full file. Fine
  for ≤ 10 MB; large files would need streaming encryption.
- **One key for everything, no rotation:** changing the key means re-encrypting all
  files (Fernet's `MultiFernet` could do this, not implemented). Losing it loses all files.
- **No thumbnails:** they would mean decrypting every image on each page.
- **Rate limits are per server process** (Django's in-memory cache). With several
  processes, use a shared cache (e.g. Redis) so the 5/min limit is global.
- **Encrypted at rest, not end-to-end:** the server holds the key and sees the
  plaintext while serving it. Whoever controls the server can read the files.
- **SQLite** is fine for a demo or a few users; use MySQL for heavier use.
- No password reset or e-mail verification.

##public url ----  https://shreeshaildivum.pythonanywhere.com/
