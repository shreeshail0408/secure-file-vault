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
| `stored_name`  | CharField(255), unique                | `<uuid4>.enc` — never the user's name |
| `uploaded_by`  | FK → User, `SET_NULL`, nullable       | the owner; files survive user deletion (then only admins can edit) |
| `created_at`   | DateTimeField(auto_now_add)           |                                    |
| `updated_at`   | DateTimeField(auto_now)               |                                    |

### Encryption flow

- `files/crypto.py`: `encrypt_bytes(data) -> bytes`, `decrypt_bytes(token) -> bytes`.
  Reads `settings.FERNET_KEY`. This is the **only** module that imports Fernet.
- **Upload:** read file bytes → validate type → `encrypt_bytes` → write
  `storage/<uuid>.enc` → create `FileRecord`.
- **Preview/download:** load record → read `.enc` → `decrypt_bytes` → `HttpResponse`
  with `Content-Type = mime_type` and
  `Content-Disposition: inline` (preview) or `attachment` (download) + filename.
- **Replace:** encrypt new bytes, write a new `.enc`, update record, then delete the old `.enc`.
- **Delete:** delete record and its `.enc` file.

### Upload validation

- Allowed: `application/pdf`, `image/png`, `image/jpeg` (optionally `image/gif`, `image/webp`).
- Check both extension and content (PDF starts with `%PDF`; images open with Pillow).
- Max size from settings (e.g. 10 MB). Reject everything else with 400.

### API (all under `/api/`)

| Method | Endpoint                         | Auth      | Purpose                                  |
|--------|----------------------------------|-----------|------------------------------------------|
| POST   | `auth/register/`                 | public    | create user                              |
| POST   | `auth/login/`                    | public    | simplejwt `TokenObtainPairView`          |
| POST   | `auth/refresh/`                  | public    | simplejwt `TokenRefreshView`             |
| GET    | `auth/me/`                       | user      | current user (username, `is_staff`)      |
| GET    | `files/?search=&type=pdf\|image` | user      | list (paginated), search by name, filter |
| POST   | `files/`                         | user      | upload (multipart, field `file`)         |
| GET    | `files/<id>/`                    | user      | metadata                                 |
| PATCH  | `files/<id>/`                    | owner/admin | rename (`original_name`)               |
| PUT    | `files/<id>/replace/`            | owner/admin | replace content (multipart)            |
| DELETE | `files/<id>/`                    | owner/admin | delete record + `.enc`                 |
| GET    | `files/<id>/preview/`            | user      | decrypted, `inline`                      |
| GET    | `files/<id>/download/`           | user      | decrypted, `attachment`                  |
| GET    | `files/export/`                  | admin     | ZIP of all `.enc` files + `manifest.json`|

- Use a DRF `ModelViewSet` + `@action`s for preview/download/replace/export to keep it in one readable file.
- Search: `?search=` → `original_name__icontains`. Filter: `?type=` → `file_type`.
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
- Export ZIP contains the **still-encrypted** `.enc` files plus `manifest.json`
  mapping `stored_name → original_name, mime_type`, so the mentor can restore names.

### `seed_files` management command

`python manage.py seed_files [--clear]`

- 50 **real** PDFs with `reportlab`: 2–5 pages each, title, paragraphs, and at least
  one table (e.g. fake invoice / report data). Names like `report_07.pdf`.
- 50 **real** images with `Pillow`: mix of PNG and JPG, shapes/gradients + text label.
- Generate in memory → `encrypt_bytes` → save `.enc` → create `FileRecord`.
  Reuse `storage.py`, don't duplicate logic.
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
