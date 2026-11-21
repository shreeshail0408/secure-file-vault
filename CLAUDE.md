# Secure File Vault

A web app where logged-in users upload, preview, download, rename, replace and delete
PDF and image files. Every file is **encrypted at rest** with Fernet. All users can
see and read one shared file pool, but only a file's uploader or an admin can change
or delete it. Admins can export every encrypted file as a ZIP, and a mentor can
decrypt those files offline with `decrypt_tool.py`.

---

## Golden rules (read first)

1. **Simple and readable beats clever.** The author has to explain every line in a
   code review. Prefer plain functions, explicit code, and short files. No magic,
   no premature abstraction, no unused "just in case" features.
2. **Build in phases.** Finish a phase, test it, and get confirmation before starting
   the next one. Do not jump ahead.
3. **Never hardcode secrets.** `FERNET_KEY`, `SECRET_KEY`, and DB credentials come
   from `.env` only. `.env` is git-ignored; `.env.example` is committed.
4. **Plaintext never touches disk.** Uploads are encrypted in memory and written as
   `.enc`. Decryption happens in memory, only while serving a response.
5. Add short comments explaining *why*, not *what*. Keep functions small.

---

## Tech stack

| Area      | Choice                                                            |
|-----------|-------------------------------------------------------------------|
| Python    | 3.12, installed with `uv` (`uv python install 3.12`, no sudo)     |
| Backend   | Django 5.2 LTS + Django REST Framework 3.18                       |
| Auth      | JWT via `djangorestframework-simplejwt` (access + refresh tokens) |
| Database  | SQLite locally; PostgreSQL or MySQL in prod via `DATABASE_URL` (`dj-database-url`) |
| Crypto    | `cryptography` → `Fernet`                                         |
| Seed data | `reportlab` (PDFs), `Pillow` (images)                             |
| Config    | `python-dotenv` (or `django-environ`) reading `backend/.env`      |
| CORS      | `django-cors-headers`, allowing `FRONTEND_URL`                    |
| Frontend  | React + Vite, `react-router-dom`, `axios`, Bootstrap              |

---

## Project layout

```
file-encryption/
├── CLAUDE.md
├── README.md                        # overview, security design, setup, tests, mentor demo, limitations
├── DEPLOY.md                        # PythonAnywhere step by step
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── decrypt_tool.py              # standalone offline decryptor
│   ├── storage/                     # *.enc files live here (git-ignored)
│   ├── staticfiles/                 # collectstatic output (git-ignored, .gitkeep only)
│   ├── config/                      # settings.py, urls.py, views.py (React index + JSON 404), test_production.py
│   ├── accounts/                    # register endpoint (login/refresh = simplejwt)
│   └── files/
│       ├── models.py                # FileRecord
│       ├── crypto.py                # encrypt_bytes / decrypt_bytes (only place Fernet is used)
│       ├── storage.py               # save_encrypted / read_decrypted / delete_file
│       ├── permissions.py           # IsOwnerOrAdmin
│       ├── serializers.py
│       ├── views.py
│       ├── urls.py
│       ├── tests.py
│       └── management/commands/seed_files.py
└── frontend/
    ├── package.json
    ├── .env.example                 # VITE_API_URL=http://localhost:8077/api
    ├── .env.production              # VITE_API_URL=/api (committed, used by npm run build)
    ├── vite.config.js               # port 5173 (strict), base "/static/" for build, vitest config
    └── src/
        ├── main.jsx, App.jsx        # router setup
        ├── api/  client.js (axios + interceptors), tokens.js, errors.js (describeError)
        ├── auth/ AuthContext.jsx (AuthProvider), useAuth.js, ProtectedRoute.jsx, PublicOnlyRoute.jsx
        ├── pages/  Login.jsx, Register.jsx, Dashboard.jsx (holds which dialog is open + toast)
        ├── api/files.js             # listFiles, fetchBlob, downloadFile, filenameFromDisposition, describeBlobError
        ├── hooks/  useFileFilters.js (URL state), useFileList.js (fetch + derived loading),
        │           useFileUpload.js (pick + pre-check + progress + errors, for Upload and Replace)
        ├── utils/  format.js (formatSize, formatDate), fileCheck.js (checkFile, acceptFor)
        ├── components/  Navbar, Spinner, TextField, SubmitButton, AuthCard, BusyButton, Modal, Toast
        ├── components/files/  SearchBar, FileResults, FileCard, LoadingGrid, Pagination, PreviewModal,
        │                      UploadModal, EditModal (Rename / Replace tabs), DeleteDialog, FilePicker, UploadProgress
        └── test/  setup.js, fakeServer.jsx (fake axios adapter + renderApp), fileFixtures.js; *.test.js(x) next to code
```

---

## Environment variables (`backend/.env`)

```
SECRET_KEY=change-me
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3          # relative = backend/db.sqlite3; prod: postgres://... or mysql://...
FERNET_KEY=<generate, see below>
FRONTEND_URL=http://localhost:5173
ALLOWED_HOSTS=localhost,127.0.0.1
```

Generate a key:
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

Settings must **fail loudly at startup** if `FERNET_KEY` is missing or invalid.
Losing the key means losing every file — warn about this in the README.

Production-only (see `DEPLOY.md`): `CSRF_TRUSTED_ORIGINS`, `NUM_PROXIES=1`,
`SECURE_HSTS_SECONDS` (default 3600 when `DEBUG=False`), `SECURE_SSL_REDIRECT`
(default `not DEBUG`).

### Production settings (`DEBUG=False`)

- `manage.py check --deploy --fail-level WARNING` must stay clean (`DeployCheckTests`
  runs it in a subprocess). Only `security.W021` (HSTS preload) is silenced: not
  possible on a `*.pythonanywhere.com` subdomain.
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` (PythonAnywhere's
  proxy); SSL redirect, secure session/CSRF cookies, HSTS + includeSubDomains,
  `X_FRAME_OPTIONS = "DENY"`, nosniff, `same-origin` referrer.
- `REST_FRAMEWORK["NUM_PROXIES"]` from env, default **0** (ignore X-Forwarded-For).
  DRF's default `None` trusts the whole header, so a client could fake it and dodge
  the login throttle. PythonAnywhere: 1 → last XFF entry (added by the proxy).
  Tested in `accounts.tests.ThrottleClientIpTests`.
- **Single host:** Django serves the React build. `FRONTEND_DIST = frontend/dist`
  is in `STATICFILES_DIRS` (only if it exists); `collectstatic` → `STATIC_ROOT =
  backend/staticfiles`; WhiteNoise (`CompressedStaticFilesStorage`, no manifest since
  Vite hashes names; `/static/assets/` marked immutable). On PythonAnywhere a
  `/static/` static-files mapping serves the same folder.
- `config/urls.py` catch-all `^(?!(?:api|admin|static)(?:/|$)).*$` →
  `config.views.frontend_app` (index.html, `Cache-Control: no-cache`, GET/HEAD only,
  503 "run npm run build" if missing). Before it, `^api/(?:.*/)?$` →
  `config.views.api_not_found` (csrf-exempt JSON 404 `{"detail": "Not found."}`):
  a route, not `handler404`, so it is JSON even with `DEBUG=True`. Only URLs ending
  in `/`, so `APPEND_SLASH` still redirects `/api/files` → `/api/files/`.
- MySQL (optional, `mysqlclient`): settings add `charset=utf8mb4` and
  `STRICT_TRANS_TABLES`. SQLite stays the default.

---

## Backend design

### Model: `FileRecord`

| Field          | Type                                  | Notes                              |
|----------------|---------------------------------------|------------------------------------|
| `id`           | auto PK                               |                                    |
| `original_name`| CharField(255)                        | what the user sees / renames       |
| `file_type`    | CharField choices `pdf` / `image`     | used for filtering                 |
| `mime_type`    | CharField(100)                        | e.g. `application/pdf`, `image/png`|
| `size`         | PositiveIntegerField                  | original (plaintext) size in bytes |
| `sha256`       | CharField(64)                         | hex SHA-256 of the plaintext, set at upload/replace; used by export manifest |
| `stored_name`  | CharField(255), unique                | `<uuid4>.enc` — never the user's name |
| `uploaded_by`  | FK → User, `SET_NULL`, nullable       | the owner; files survive user deletion (then only admins can edit) |
| `created_at`   | DateTimeField(auto_now_add)           |                                    |
| `updated_at`   | DateTimeField(auto_now)               |                                    |

### Encryption flow

- `files/crypto.py`: `encrypt_bytes(data) -> bytes`, `decrypt_bytes(token) -> bytes`.
  Reads `settings.FERNET_KEY`. This is the **only** module that imports Fernet.
- `decrypt_bytes` wraps Fernet's `InvalidToken` in `crypto.DecryptionError`
  ("modified or encrypted with a different key"). Phase 4 views must catch it and
  return a clean JSON error, never a traceback.
- `files/storage.py`: `save_encrypted(data) -> stored_name`, `read_decrypted(name)`,
  `delete_file(name)`.
  - Names are `uuid4().hex + ".enc"`; `_path_for` rejects anything else, so user
    input can never reach the filesystem.
  - Atomic writes: ciphertext → `mkstemp` in `STORAGE_DIR` → `fsync` → `os.replace`.
    The temp file only ever holds ciphertext; on error it is removed.
  - `delete_file` is a no-op if the file is already gone.
- A `post_delete` signal on `FileRecord` deletes the `.enc` via
  `transaction.on_commit`, so bulk deletes are covered and a rolled-back delete
  never loses the file.
- **Upload:** read file bytes → validate type → `encrypt_bytes` → write
  `storage/<uuid>.enc` → create `FileRecord`.
- **Preview/download:** load record → read `.enc` → `decrypt_bytes` → `HttpResponse`
  with `Content-Type = mime_type` and
  `Content-Disposition: inline` (preview) or `attachment` (download) + filename.
- **Replace:** encrypt new bytes, write a new `.enc`, update record, then delete the old `.enc`.
- **Delete:** delete record and its `.enc` file.

### Upload validation

All in `files/validation.py`; every failure is a 400 with a clear message.

- **Content decides the type** (magic bytes): `%PDF-` → pdf, `\x89PNG\r\n\x1a\n` → png,
  `\xFF\xD8\xFF` → jpg. The client's Content-Type is ignored. The extension must
  also match the content (`.pdf` / `.png` / `.jpg`, `.jpeg`).
- **Size:** > `MAX_UPLOAD_SIZE` (10 MB) is rejected before reading or encrypting.
  Request bodies over `FILE_UPLOAD_MAX_MEMORY_SIZE` (10 MB + 1 MB form overhead)
  are rejected from `CONTENT_LENGTH` before Django parses them. Empty files rejected.
- **In-memory uploads only:** `FILE_UPLOAD_HANDLERS = [MemoryFileUploadHandler]`.
  Django's default would spill uploads > 2.5 MB into a temp file, which would put
  plaintext on disk.
- **Names** (upload and rename): folder parts are dropped (`../../x` → `x`), Unicode
  control/format characters are removed (`\n`, `\r`, `\x1b`, U+202E RTL override);
  NUL is refused by DRF's `CharField`. Empty names → 400; max 255 characters.
- **Rename keeps the extension:** everything before the last dot + the current
  extension (`hack.exe` → `hack.pdf`, `notes` → `notes.pdf`, `.pdf` → 400).
- **Replace:** the new file must have the same `file_type` (pdf↔pdf, image↔image).
  PNG→JPG is allowed and updates `mime_type` and the name's extension. The old
  `.enc` is deleted via `on_commit`.

### API (all under `/api/`)

| Method | Endpoint                         | Auth      | Purpose                                  |
|--------|----------------------------------|-----------|------------------------------------------|
| POST   | `auth/register/`                 | public, throttled | username, email, password, confirm_password → 201 + user |
| POST   | `auth/login/`                    | public, throttled | simplejwt `TokenObtainPairView` subclass |
| POST   | `auth/refresh/`                  | public    | simplejwt `TokenRefreshView`             |
| GET    | `auth/me/`                       | user      | exactly `id, username, email, is_staff`  |
| GET    | `files/?search=&type=pdf\|image` | user      | list (paginated), search by name, filter |
| POST   | `files/`                         | user      | upload (multipart, field `file`)         |
| GET    | `files/<id>/`                    | user      | metadata                                 |
| PATCH  | `files/<id>/`                    | owner/admin | rename (`original_name`)               |
| PUT    | `files/<id>/replace/`            | owner/admin | replace content (multipart)            |
| DELETE | `files/<id>/`                    | owner/admin | delete record + `.enc`                 |
| GET    | `files/<id>/preview/`            | user      | decrypted, `inline`                      |
| GET    | `files/<id>/download/`           | user      | decrypted, `attachment`                  |
| GET    | `files/export/`                  | admin     | ZIP of all `.enc` files + `manifest.json`|

- Auth rules (`accounts/`):
  - Register runs Django's password validators; duplicate username or email
    (case-insensitive) → 400 with a clear message.
  - `RegisterSerializer` reads only its four fields and calls `create_user`, so
    sending `is_staff`/`is_superuser` can never create an admin.
  - No response ever contains the password or its hash (`UserSerializer` is the
    only user output).
  - Login and register are throttled per IP via `AUTH_THROTTLE_RATES` (5/min) and
    `accounts.throttles.AuthRateThrottle`, which reads the rate at request time so
    tests can override it. Tests run with throttling off, except `ThrottleTests`.
- Use a DRF `ModelViewSet` + `@action`s for preview/download/replace/export to keep it in one readable file.
- Search: `?search=` → `original_name__icontains`. Filter: `?type=` → `file_type`
  (anything other than `pdf`/`image` → 400).
- `FileRecordViewSet` has no `update`, so `PUT /files/<id>/` → 405; content
  changes go through `replace/`.
- Unknown or malformed id → 404 (from `get_object`).
- Preview/download errors → JSON 500, logged, never a traceback:
  `DecryptionError` → `{"detail": "Could not decrypt file: ..."}`, missing `.enc` →
  `{"detail": "The stored file is missing on the server."}`.
- `Content-Disposition` via `django.utils.http.content_disposition_header`: quotes
  escaped; non-ASCII or control characters → `filename*=utf-8''...`. Responses also
  send `Cache-Control: private, no-store`.
- `FileRecordSerializer` exposes `can_edit` and the uploader's username, never
  `stored_name`.
- Permissions:
  - `IsAuthenticated` on everything; export also uses `IsAdminUser`.
  - **Read** (list, search, metadata, preview, download): every logged-in user, every file.
  - **Write** (rename, replace, delete): only the uploader or an admin (`is_staff`).
    Enforced by `IsOwnerOrAdmin` in `files/permissions.py`:
    ```python
    class IsOwnerOrAdmin(BasePermission):
        def has_object_permission(self, request, view, obj):
            if request.method in SAFE_METHODS:
                return True
            return request.user.is_staff or obj.uploaded_by_id == request.user.id
    ```
    Applied to the viewset's `update`, `partial_update`, `destroy` and the `replace`
    action. A non-owner gets **403**, no matter what the frontend shows.
  - The serializer adds a read-only `can_edit` boolean (same rule) so the frontend
    doesn't duplicate the logic.
- **Export** (`GET files/export/`, `files/export.py`), admin only (no token → 401,
  non-admin → 403), filename `vault-export-YYYY-MM-DD.zip`:
  - ZIP root: every `<uuid>.enc` (still encrypted, byte-for-byte), `manifest.json`,
    `README.txt` (how to use `decrypt_tool.py`; says the key is NOT included).
  - `manifest.json`: `exported_at`, `file_count`, `missing` (original names whose
    `.enc` was gone, logged as a warning), and `files[]` with `stored_name,
    original_name, mime_type, size, sha256`.
  - `sha256` is of the **plaintext**, stored on `FileRecord` at upload/replace, so
    export **never decrypts**.
  - Built into an anonymous `tempfile.TemporaryFile` (ciphertext only, deleted on
    close) with `ZIP_STORED`, adding `.enc` files one at a time, which streams them
    in chunks. Sent with `FileResponse` (chunked).
  - `FERNET_KEY` must never be in the ZIP. A test scans every entry and the raw ZIP
    for the key (text, raw bytes, both halves) and `SECRET_KEY`.

### `seed_files` management command

`python manage.py seed_files [--count N] [--reset]` — content in `files/seed_content.py`,
command in `files/management/commands/seed_files.py`.

- 50 **real** PDFs (`reportlab` platypus, 2–4 pages, all with tables): invoices
  (`invoice_2026_01..12.pdf`), reports (`report_sales_q2.pdf`, …), certificates
  (`certificate_ai_ml.pdf`, landscape), meeting minutes, project specs (some embed
  large photos, so they are about 1 MB).
- 50 **real** images (`Pillow`, 30 PNG / 20 JPG, 640×480 up to 2400×1600): bar and
  pie charts, banners, ID badges, gradient posters, photo-like landscapes (grain
  makes them about 1–2 MB). Total about 16.5 MB plaintext.
- Deterministic: each file uses `random.Random(name)`; the list alternates
  PDF/image so `--count N` gives a mix. Tests use `--count 4`.
- Every file goes through `validation.validate_file` (same rules as an upload) and
  `FileRecord.create_from_upload` (same encrypt+store path as the upload view).
- **Idempotent:** `FileRecord.seed_key` (= generated name, NULL for real uploads);
  existing keys are skipped even if renamed. `--reset` deletes only seeded records
  (the signal removes their `.enc`).
- Seeded files are **owned by the admin user**: `uploaded_by` = first superuser.
  If no superuser exists, stop with a clear error ("run createsuperuser first").
- Use a fixed random seed so output is reproducible.

### `decrypt_tool.py` (standalone)

`backend/decrypt_tool.py`: Python 3.8+, only stdlib + `cryptography` (a test checks
the imports), no Django. Works on Linux, macOS and Windows.

```
export FERNET_KEY='<key>'                               # or: --key-file key.txt (.env line OK)
python decrypt_tool.py vault-export/ --out decrypted/   # unzipped export, uses manifest.json
python decrypt_tool.py vault-export/<uuid>.enc          # one file (manifest beside it if present)
```

- **Never `--key`:** a key on the command line leaks into shell history and `ps`.
  `--key`/`--key=` are refused (exit 2), and the key is never printed.
  `allow_abbrev=False`, so `--key` can't silently match `--key-file`.
- **With a manifest:** original names restored; sha256 + size checked; per-file
  `✓ verified` / `✗ MISMATCH` / `✗ FAILED` / `✗ MISSING`, then
  `Summary: N ok, N failed, N missing`. Mismatched files are not written.
  Without a manifest: the extension comes from the magic bytes, and the output
  says "sha256 not checked".
- **Safe output:** names are cleaned (folders, control chars, Windows `<>:"/\|?*`,
  `CON`/`NUL`/`COM1`…, trailing dots); manifest `stored_name` must match
  `<32 hex>.enc`. Files are opened with `"xb"` (never overwrite), so duplicates become
  `report (1).pdf`; the final path must be directly inside `--out`.
- **Keeps going:** wrong key, tampered file, or a write error only fails that file.
  Exit 0 = all ok/verified, 1 = any failed/missing, 2 = can't start (no/invalid
  key, bad input, broken manifest).
- Uses `✓`/`✗` only if the console can print them (falls back to `OK`/`X`).

---

## Frontend design

React 19 + Vite 8 + react-router 7 + axios + Bootstrap 5. Plain JS, no TypeScript,
no Redux. Small components.

- `api/client.js`: `api` = axios instance with `baseURL = import.meta.env.VITE_API_URL`.
  - Request interceptor adds `Authorization: Bearer <access>`, but **not** to
    login/register/refresh (a stale token must not break them; the backend's
    `RegisterView` also sets `authentication_classes = []`).
  - Response interceptor, on 401 (not from auth URLs, one retry per request):
    **single in-flight refresh**: all concurrent 401s await the same
    `refreshPromise`, so there is one `POST auth/refresh/`, then every request is
    replayed. A 401 for a request sent with an already-replaced token reuses the
    new token without refreshing again. The refresh uses a separate `refreshClient`
    (no interceptors). Refresh fails → `clearTokens()` + `window` event
    `auth:logout` → AuthProvider sets user to null → ProtectedRoute → `/login`.
- `api/errors.js` `describeError(err)` → `{message, fieldErrors}`: DRF 400 field
  errors go under each input (`TextField`), `detail`/`non_field_errors` go in the
  alert, 429 → "Too many attempts, wait a minute…", no response → "Cannot reach
  the server".
- Tokens in `localStorage` (`vault.access`, `vault.refresh`). Simple; XSS trade-off
  noted in `tokens.js`.
- `AuthProvider`: `loading` starts `true` only if tokens exist, then `GET /auth/me/`
  (auto-refreshes if needed). `user` = `{id, username, email, is_staff}`. `login()`
  = POST login → store tokens → GET me. `logout()` clears tokens.
- `ProtectedRoute`: loading → `<Spinner/>` (no flash of the login page); no user →
  `/login` (remembers `from`). `PublicOnlyRoute` (login/register) → `/` if logged in.
- Forms: submit button disabled with a spinner while sending. Register logs in
  automatically after success.
- Routes: `/login`, `/register`, `/` (Dashboard), `*` → `/`.
- Tests: `npm test` (Vitest + Testing Library + jsdom). `test/fakeServer.jsx` swaps
  axios's adapter so the real interceptors run, with no network.
- **Dashboard** (`pages/Dashboard.jsx` + `components/files/*`):
  - `FileCard`: Bootstrap Icons type icon (no thumbnails; that would mean decrypting
    every image on the page), name, PDF/Image badge, size (`utils/format.js`:
    B/KB/MB), date (`21 Nov 2026`, en-GB), uploader. Preview + Download always;
    Edit/Delete **only when `file.can_edit`**.
    Hiding is just UX; the API still returns 403.
  - **URL is the state** (`hooks/useFileFilters.js`): `?search=&type=&page=`, so
    reload and Back work. A new search or type → page 1. Page/type changes push a
    history entry; search uses `replace` (no history entry per word).
  - `SearchBar`: 300 ms debounce via `setTimeout` in onChange; syncs its text when the
    URL changes from outside (Back / Clear) using the "adjust state during render"
    pattern (no effect).
  - `hooks/useFileList.js`: fetch on filter change with `AbortController`; `loading`
    is derived (`result.key !== key`), not set inside the effect.
  - `FileResults`: `LoadingGrid` skeleton → error alert + Retry → page-404 ("Go to
    page 1") → empty state (`No files match "xyz".` + Clear filters) → grid +
    `Pagination` ("Showing 21–40 of 100", Prev / "Page X of Y" / Next).
    `PAGE_SIZE = 20` in `api/files.js` must match the backend's `PAGE_SIZE`.
  - "Export all" (admins only) → `downloadFile("/files/export/")`.
- **PreviewModal:** `fetchBlob(preview/)` (an `<iframe src>` can't send the JWT). The
  blob is re-wrapped with the stored `mime_type` (never HTML), shown via
  `URL.createObjectURL` (PDF → `<iframe>`, image → `<img>`), and **revoked** on
  close/unmount; the request is aborted if closed early. Spinner while decrypting.
  Errors: blob bodies are parsed as JSON (`describeBlobError`), so the backend's
  "Could not decrypt file…" is shown. Escape, backdrop or Close dismiss it.
- **Download / Export:** `downloadFile(url, fallbackName)` → blob → name from
  `Content-Disposition` via `filenameFromDisposition` (prefers RFC 5987 `filename*`,
  un-escapes quoted `filename`, falls back to `original_name`) → `saveBlob`
  (temporary `<a download>`, URL revoked after 1 s). Needs
  `CORS_EXPOSE_HEADERS = ["Content-Disposition"]` (backend settings).
- **Modals:** one `Modal` component (Bootstrap classes, no Bootstrap JS); Escape,
  × and backdrop close it, except while `busy` (mid-upload/save). Dashboard keeps
  one `dialog` state (`{kind, file}`), so only one is open at a time.
- **Upload** (`UploadModal`): `FilePicker` (click or drag-and-drop) → browser
  pre-check `utils/fileCheck.js` (`.pdf/.png/.jpg/.jpeg` + MIME, not empty, ≤
  `MAX_UPLOAD_MB` = 10, must match the backend). Only for fast feedback; the backend
  still decides by magic bytes. `uploadFile` sends `FormData` with
  `onUploadProgress` → `UploadProgress` bar. Backend `{"file": [...]}` errors show
  under the picker. Success → toast, `setPage(1)` + `retry()` (newest first).
- **EditModal**, tab **Rename**: prefilled `TextField`, says the extension is kept
  (the backend forces it), `original_name` field errors under the input. Tab
  **Replace file**: explains it must be the same type; `accept` and the pre-check
  allow only that type; same progress/error handling (`useFileUpload`).
- **Delete** (`DeleteDialog`): names the file, Cancel / Delete. If it was the only
  card on a page > 1 → previous page, otherwise `retry()`.
- `describeChangeError` (`api/errors.js`): 403 → "You can't modify this file: only
  its uploader or an admin can.", 404 → "This file no longer exists…". The dialog
  stays open on errors. Success messages go in a `Toast` (auto-hides after 4 s).
- Show loading and error messages for every request.

---

## Build phases

Each phase ends with its checks passing. Stop and confirm before the next phase.

| # | Phase | Done when |
|---|-------|-----------|
| 1 | **Backend skeleton**: Django project, apps, `.env` loading, `DATABASE_URL`, CORS, DRF + simplejwt settings | `runserver` starts; missing `FERNET_KEY` gives a clear error |
| 2 | **Auth API**: register, login, refresh, me | Tests + curl: register → login → refresh works; bad password → 401 |
| 3 | **Crypto + storage + model**: `crypto.py`, `storage.py`, `FileRecord`, migrations | Unit test: encrypt→decrypt round-trip; `.enc` bytes ≠ original |
| 4 | **File API + `IsOwnerOrAdmin`**: list/search/filter, upload, preview, download, rename, replace, delete | API tests for each endpoint incl. 401 without token, 400 on bad file type, and ownership: **user B cannot delete user A's file (403, file + `.enc` still exist)**, B also can't rename/replace it, B *can* preview/download it, admin *can* delete it |
| 5 | **Admin export** | Non-admin → 403; admin gets ZIP with `.enc` files + manifest |
| 6 | **`seed_files`** | 100 records + 100 `.enc` files; random samples decrypt to valid PDF/PNG/JPG |
| 7 | **`decrypt_tool.py`** | Decrypts a seeded file and an exported ZIP folder; wrong key → clear error |
| 8 | **Frontend setup**: Vite, router, Bootstrap, axios client, Login/Register, ProtectedRoute | Can register/log in; protected page redirects when logged out; token auto-refresh works |
| 9 | **Dashboard**: grid, search, filter, pagination, preview modal, download | Search & filter work against seeded data; PDF and images preview correctly |
| 10 | **Upload, Rename/Replace, Delete, Export button** | Full manual walkthrough of every feature passes |
| 11 | **Production readiness + docs**: `check --deploy` clean, proxy-aware throttling, Django serves `frontend/dist` (WhiteNoise + catch-all), README, DEPLOY.md | Tests pass; `DEBUG=False` smoke run serves app + JSON 404s; fresh clone → README → app runs |
| 12 | **Deploy to PythonAnywhere** following `DEPLOY.md` | Live site passes DEPLOY.md step 9 checks |

---

## Commands

```bash
# Backend
cd backend
uv venv --python 3.12 --seed .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then set FERNET_KEY and SECRET_KEY
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_files
python manage.py runserver 8077 # http://localhost:8077  (port 8000 is used by another project here)
python manage.py test

# Frontend (Node >= 20.19)
cd frontend
npm install
cp .env.example .env            # VITE_API_URL=http://localhost:8077/api
npm run dev                     # http://localhost:5173 (must match FRONTEND_URL for CORS)
npm test                        # vitest run
npm run lint && npm run build   # build → dist/ with /static/ asset URLs and VITE_API_URL=/api

# Production-like, single host
cd frontend && npm run build && cd ../backend
python manage.py collectstatic --noinput
python manage.py check --deploy  # with DEBUG=False etc. in the environment
```

---

## Security notes (for the review)

- Encryption at rest with Fernet (AES-128-CBC + HMAC-SHA256, authenticated).
- Stored filenames are random UUIDs; original names exist only in the DB.
- `storage/` is outside any static/media URL — files are only reachable through
  authenticated API views.
- Download filenames are sanitized in `Content-Disposition`.
- `.env`, `storage/`, `db.sqlite3` are git-ignored.
- Ownership is enforced server-side (`IsOwnerOrAdmin` → 403); the frontend only
  hides buttons.
- Known simplifications: every user can read every file (shared pool by design),
  tokens in `localStorage`, whole file decrypted in memory (fine for ≤10 MB files).
