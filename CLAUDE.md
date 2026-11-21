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
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── decrypt_tool.py              # standalone offline decryptor
│   ├── storage/                     # *.enc files live here (git-ignored)
│   ├── config/                      # Django project: settings.py, urls.py
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
    ├── .env.example                 # VITE_API_URL=http://localhost:8000/api
    └── src/
        ├── main.jsx, App.jsx        # router setup
        ├── api/client.js            # axios instance + JWT interceptor
        ├── auth/ProtectedRoute.jsx
        ├── pages/  Login.jsx, Register.jsx, Dashboard.jsx, Upload.jsx
        └── components/  FileCard.jsx, PreviewModal.jsx, RenameReplaceModal.jsx, ConfirmDelete.jsx
```

---

## Environment variables (`backend/.env`)

```
SECRET_KEY=change-me
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3          # prod: postgres://... or mysql://...
FERNET_KEY=<generate, see below>
FRONTEND_URL=http://localhost:5173
ALLOWED_HOSTS=localhost,127.0.0.1
```

Generate a key:
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

Settings must **fail loudly at startup** if `FERNET_KEY` is missing or invalid.
Losing the key means losing every file — warn about this in the README.

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

Depends only on `cryptography` — no Django.

```
python decrypt_tool.py --key <FERNET_KEY> --input file.enc --output file.pdf
python decrypt_tool.py --key <FERNET_KEY> --input export_dir/ --output out_dir/   # uses manifest.json if present
```

Key may also come from `FERNET_KEY` env var. Print a clear error on a wrong key
(`InvalidToken`).

---

## Frontend design

- `api/client.js`: axios instance with `baseURL = import.meta.env.VITE_API_URL`.
  - Request interceptor adds `Authorization: Bearer <access>`.
  - Response interceptor: on 401, call `auth/refresh/` once, retry the original
    request; if refresh fails, clear tokens and redirect to `/login`.
    Queue concurrent requests so only one refresh happens.
- Tokens stored in `localStorage` (simple; mention the XSS trade-off in review).
- `ProtectedRoute`: no token → `<Navigate to="/login" />`.
- Routes: `/login`, `/register`, `/` (Dashboard), `/upload`.
- **Dashboard:** card grid (name, type badge, size, date), search box (debounced
  ~300 ms), type filter dropdown (All / PDF / Image), pagination, actions per card:
  Preview, Download (always), Rename/Replace, Delete (**only when `file.can_edit`**).
  "Export all" button visible only to admins. Hiding buttons is just UX — the API
  still returns 403; show that error if it ever happens.
- **PreviewModal:** fetch `preview/` with axios as a **blob** (the auth header can't be
  sent from a plain `<iframe src>`), then `URL.createObjectURL(blob)`:
  PDF → `<iframe>`, image → `<img>`. Revoke the object URL on close.
- **Download / Export:** fetch as blob, create a temporary `<a download>` link.
- **Rename/Replace modal:** text input for rename (PATCH), file input for replace (PUT).
- **Delete:** confirm dialog, then DELETE and refresh the list.
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
| 11 | **Polish & README**: setup steps, key handling warning, review talking points | Fresh clone → follow README → app runs |

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
python manage.py runserver      # http://localhost:8000
python manage.py test

# Frontend
cd frontend
npm install
cp .env.example .env
npm run dev                     # http://localhost:5173
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
