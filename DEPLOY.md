# Deploying to PythonAnywhere

One host does everything: Django serves the API (`/api/`), the admin (`/admin/`),
the built React app (every other URL → `frontend/dist/index.html`) and its assets
(`/static/`). No CORS, no second server.

Replace **`<you>`** everywhere with your PythonAnywhere username. The site will be
`https://<you>.pythonanywhere.com`.

> **Free account notes:** 512 MB disk (the venv is about 120 MB, the 100 seeded files
> about 25 MB encrypted; `node_modules` would add about 140 MB); outbound internet is limited to an allow-list (PyPI and
> GitHub work); the web app must be extended every 3 months (button on the Web tab).

---

## 0. Before you start (on your own machine)

1. Push the repository to GitHub (a private repo is fine). `.env`, `db.sqlite3`,
   `storage/*.enc`, `node_modules` and `dist` are git-ignored and are **not** pushed.
2. Build the frontend; PythonAnywhere's Node may be too old for Vite (needs ≥ 20.19):
   ```bash
   cd frontend
   npm ci
   npm run build                  # uses .env.production → VITE_API_URL=/api, assets under /static/
   zip -r dist.zip dist
   ```

---

## 1. Get the code (PythonAnywhere → Consoles → Bash)

```bash
cd ~
git clone https://github.com/<github-user>/<repo>.git file-encryption
```

For a private repo, git asks for a username and password: use a GitHub
**fine-grained personal access token** (read-only "Contents") as the password. Don't
put the token in the URL, or it gets saved in `.git/config`.

---

## 2. Python environment

```bash
cd ~/file-encryption/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

(With uv instead: `pip install --user uv && ~/.local/bin/uv venv --python 3.12 --seed .venv`,
then the same `source` and `pip install` lines.)

---

## 3. `.env` on the server

Generate two **new** keys on the server:

```bash
cd ~/file-encryption/backend
python -c "import secrets; print(secrets.token_urlsafe(50))"                               # SECRET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # FERNET_KEY
```

Create the file and lock it down:

```bash
cp .env.example .env
chmod 600 .env          # only your user can read it
nano .env
```

```ini
SECRET_KEY=<the first value>
DEBUG=False
ALLOWED_HOSTS=<you>.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://<you>.pythonanywhere.com
DATABASE_URL=sqlite:///db.sqlite3
FERNET_KEY=<the second value>
FRONTEND_URL=https://<you>.pythonanywhere.com
NUM_PROXIES=1
SECURE_HSTS_SECONDS=3600
```

> ⚠️ **Copy `FERNET_KEY` into a password manager now.** If it is lost, every uploaded
> file is unreadable forever. It is also what the mentor needs for `decrypt_tool.py`.
> Run `clear` afterwards so the keys don't stay on screen.

What these do:
- `DEBUG=False` turns on the HTTPS redirect, secure cookies and HSTS (`config/settings.py`).
- `NUM_PROXIES=1`: PythonAnywhere has one proxy in front of Django, so login rate
  limiting uses the real visitor's IP, not the proxy's (step 9 checks this).
- `SECURE_HSTS_SECONDS=3600`: browsers stick to HTTPS for an hour. Raise it to
  `31536000` (1 year) once everything works.

Check the settings:

```bash
python manage.py check --deploy        # expect: System check identified no issues (1 silenced).
```

The silenced check is HSTS "preload", which isn't possible for a `*.pythonanywhere.com` subdomain.

---

## 4. Database, admin user, demo data

```bash
python manage.py migrate
python manage.py createsuperuser       # asks for username, e-mail, password
python manage.py seed_files            # optional: 100 demo files owned by that admin
```

---

## 5. Frontend build

**Option A, recommended: upload the build from step 0.**
Files tab → `/home/<you>/file-encryption/frontend/` → *Upload a file* → `dist.zip`. Then in Bash:

```bash
cd ~/file-encryption/frontend
unzip -o dist.zip && rm dist.zip
ls dist                                # index.html  assets/  favicon.svg
```

**Option B: build on PythonAnywhere.** Only if `node --version` shows ≥ 20.19, and it
costs about 140 MB of disk for `node_modules`:

```bash
cd ~/file-encryption/frontend && npm ci && npm run build && rm -rf node_modules
```

Then collect the static files (React build + Django admin CSS) into `backend/staticfiles/`:

```bash
cd ~/file-encryption/backend
python manage.py collectstatic --noinput
```

---

## 6. Create the web app (Web tab)

1. **Add a new web app** → your free domain → **Manual configuration** (not "Django") → **Python 3.12**.
2. **Virtualenv:** `/home/<you>/file-encryption/backend/.venv`
3. **Source code:** `/home/<you>/file-encryption/backend`
4. **Static files:** add one mapping, so PythonAnywhere's web server serves them directly:

   | URL        | Directory                                          |
   |------------|----------------------------------------------------|
   | `/static/` | `/home/<you>/file-encryption/backend/staticfiles`  |

   (WhiteNoise would serve them too; the mapping is just faster.)
5. **Security:** turn on **Force HTTPS**.

---

## 7. WSGI file

Web tab → click the **WSGI configuration file** link
(`/var/www/<you>_pythonanywhere_com_wsgi.py`), delete everything in it and paste:

```python
import os
import sys

# The folder that contains manage.py and the "config" package.
path = "/home/<you>/file-encryption/backend"
if path not in sys.path:
    sys.path.insert(0, path)

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

# config/settings.py loads backend/.env itself, so no secrets go in this file.
from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
```

Save.

---

## 8. Reload

Web tab → green **Reload** button. Open `https://<you>.pythonanywhere.com`.

If something is wrong, the Web tab links the **error log**
(`/var/log/<you>.pythonanywhere.com.error.log`).

---

## 9. Check it works

In the browser:
- `/` shows the login page. Log in as the superuser and you see the 100 files.
- Reload on `/register` still shows the page (the catch-all route works).
- Preview a PDF, download a file, upload one, export the ZIP.

From a console (yours or PythonAnywhere's):

```bash
SITE=https://<you>.pythonanywhere.com
curl -sI http://<you>.pythonanywhere.com/ | head -3     # 301 → https://
curl -s $SITE/api/nope/; echo                           # {"detail": "Not found."}  (JSON, not HTML)
curl -sI $SITE/ | grep -i strict-transport              # Strict-Transport-Security: max-age=3600; includeSubDomains
```

**Rate limiting uses the real IP and can't be tricked.** Each request fakes a
different `X-Forwarded-For`; the 6th must still be blocked:

```bash
for i in 1 2 3 4 5 6; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "X-Forwarded-For: 10.9.9.$i" \
       -d username=nobody -d password=wrong $SITE/api/auth/login/
done
# expected: 401 401 401 401 401 429   (then wait a minute before logging in from this IP)
```

Six `401`s would mean the proxy doesn't add the client IP the way `NUM_PROXIES=1`
expects. In that case, set `NUM_PROXIES=0` (everyone then shares one limit, which is
strict but safe) and investigate.

---

## Updating after a change

```bash
cd ~/file-encryption && git pull
cd backend && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
# new frontend? upload + unzip a fresh dist.zip (step 5), then:
python manage.py collectstatic --noinput
```

Then click **Reload** on the Web tab.

---

## Backups

Three things together make a full backup. Store the key **separately** from the other two:

1. `backend/db.sqlite3`: users, file names, owners, checksums.
2. `backend/storage/*.enc`: the encrypted files. The admin **Export all** ZIP also
   contains them, plus `manifest.json`.
3. `FERNET_KEY`: in your password manager. Without it, 1 and 2 are useless.

---

## Optional: MySQL instead of SQLite

SQLite is fine for this app. To use PythonAnywhere's MySQL:

1. **Databases** tab → set a MySQL password → create a database, e.g. `vault`
   (its full name becomes `<you>$vault`).
2. `pip install mysqlclient` in the venv, and add it to `requirements.txt` with the
   version pip installed.
3. In `.env` (URL-encode special characters in the password, e.g. `@` → `%40`):
   ```ini
   DATABASE_URL=mysql://<you>:<password>@<you>.mysql.pythonanywhere-services.com/<you>$vault
   ```
   `config/settings.py` adds `charset=utf8mb4` and strict mode for MySQL automatically.
4. `python manage.py migrate`, `createsuperuser`, `seed_files`, then **Reload**.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `DisallowedHost` / 400 Bad Request | `ALLOWED_HOSTS` in `.env` doesn't match the domain |
| `FERNET_KEY is not set` in the error log | `.env` missing, or not in `backend/` |
| Endless redirect | **Force HTTPS** + `SECURE_PROXY_SSL_HEADER` are both fine; check you didn't edit `SECURE_PROXY_SSL_HEADER` |
| Page says "The frontend is not built yet" | `frontend/dist/index.html` is missing: redo step 5 |
| Blank page, `/static/assets/...` 404 | Run `collectstatic`, then check the `/static/` mapping path and Reload |
| Admin login: "CSRF verification failed" | `CSRF_TRUSTED_ORIGINS` must be exactly `https://<you>.pythonanywhere.com` |
| Every file shows "Could not decrypt file" | `FERNET_KEY` differs from the one the files were encrypted with |
