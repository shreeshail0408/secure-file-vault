#!/usr/bin/env python3
"""
decrypt_tool.py - decrypt Secure File Vault .enc files offline.

Standalone: needs only Python 3.8+ and `pip install cryptography`.
Works on Linux, macOS and Windows. Does not need Django or the server.

The key is read from the FERNET_KEY environment variable or from --key-file.
It is deliberately NOT accepted as a command-line argument, because arguments
end up in shell history and in the process list where other users can see them.

Usage
-----
  # Linux / macOS
  export FERNET_KEY='<key>'
  python decrypt_tool.py vault-export/              # a whole unzipped export
  python decrypt_tool.py vault-export/abc...123.enc # one file

  # Windows (PowerShell)
  $env:FERNET_KEY = '<key>'
  python decrypt_tool.py vault-export\\

  # or keep the key in a file (just the key, or a .env line FERNET_KEY=...)
  python decrypt_tool.py vault-export/ --key-file key.txt --out restored/

With manifest.json (from the export), every file gets its original name back
and is checked against the sha256 and size recorded at upload time.

Exit code: 0 = every file decrypted (and verified, where a manifest exists),
           1 = at least one file failed or was missing,
           2 = could not start (no key, bad input, unreadable manifest).
"""

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    sys.exit("This tool needs the 'cryptography' package: pip install cryptography")

# Stored names are always "<32 hex chars>.enc"; anything else in a manifest is refused,
# so a malicious manifest can't make us READ files outside the export folder.
STORED_NAME = re.compile(r"^[0-9a-f]{32}\.enc$")

# Used to pick an extension when there is no manifest.
MAGIC_BYTES = [(b"%PDF-", ".pdf"), (b"\x89PNG\r\n\x1a\n", ".png"), (b"\xff\xd8\xff", ".jpg")]

# Characters and names Windows does not allow in file names.
WINDOWS_BAD_CHARS = set('<>:"/\\|?*')
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {
    f"LPT{i}" for i in range(1, 10)}

MAX_NAME = 200  # leaves room for " (123)" and stays well under OS limits


class ToolError(Exception):
    """A problem that stops the tool before it can process any file (exit code 2)."""


def symbol(preferred, fallback):
    """Use ✓/✗ when the console can print them (old Windows consoles can't)."""
    try:
        preferred.encode(sys.stdout.encoding or "ascii")
        return preferred
    except (UnicodeEncodeError, LookupError):
        return fallback


OK = symbol("✓", "OK")
BAD = symbol("✗", "X ")


def say(text):
    # errors="replace" so an odd file name can never crash the tool on any console.
    encoding = sys.stdout.encoding or "utf-8"
    print(text.encode(encoding, errors="replace").decode(encoding))


# --- Key --------------------------------------------------------------------

def load_key(key_file):
    if key_file:
        try:
            text = Path(key_file).read_text(encoding="utf-8")
        except OSError as error:
            raise ToolError(f"Could not read key file {key_file}: {error.strerror}")
        key = text.strip()
        # Also accept a .env-style file: use the FERNET_KEY=... line if there is one.
        for line in text.splitlines():
            if line.strip().startswith("FERNET_KEY="):
                key = line.split("=", 1)[1].strip().strip("'\"")
                break
    else:
        key = os.environ.get("FERNET_KEY", "").strip()

    if not key:
        raise ToolError("No key given. Set the FERNET_KEY environment variable or use --key-file FILE.")
    try:
        return Fernet(key)
    except ValueError:
        # Never print the key itself.
        raise ToolError("The key is not a valid Fernet key (expected 44 url-safe base64 characters).")


# --- File names -------------------------------------------------------------

def safe_filename(name, fallback):
    """Turn a name from the manifest into a plain file name that stays inside --out."""
    name = str(name).replace("\\", "/").split("/")[-1]  # drop folders: "../../x" -> "x"
    name = "".join(
        ch for ch in name
        if not unicodedata.category(ch).startswith("C") and ch not in WINDOWS_BAD_CHARS
    )
    name = name.strip(" .")  # no leading dots (hidden files) or trailing dots/spaces (Windows)
    if not name:
        name = fallback
    if name.split(".")[0].upper() in WINDOWS_RESERVED:  # "CON.pdf" can't exist on Windows
        name = "_" + name
    if len(name) > MAX_NAME:
        stem, ext = os.path.splitext(name)
        name = stem[: MAX_NAME - len(ext)] + ext
    return name


def write_new_file(out_dir, name, data):
    """Write data to out_dir/name without ever overwriting: report.pdf, report (1).pdf, ..."""
    stem, ext = os.path.splitext(name)
    number = 0
    while True:
        candidate = out_dir / (name if number == 0 else f"{stem} ({number}){ext}")
        # Belt and braces: the final path must be directly inside out_dir.
        if candidate.resolve().parent != out_dir.resolve():
            raise ValueError(f"refusing to write outside the output folder: {candidate}")
        try:
            with open(candidate, "xb") as f:  # "x" = fail if the file already exists
                f.write(data)
            return candidate
        except FileExistsError:
            number += 1


def guess_extension(data):
    for magic, ext in MAGIC_BYTES:
        if data.startswith(magic):
            return ext
    return ".bin"


# --- Decrypting -------------------------------------------------------------

def load_manifest(folder):
    path = folder / "manifest.json"
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest.get("files"), list):
            raise ValueError("'files' list is missing")
        return manifest
    except (ValueError, AttributeError) as error:
        raise ToolError(f"manifest.json is not valid: {error}")


class Results:
    def __init__(self):
        self.ok = self.failed = self.missing = 0

    def line(self, good, label, name, detail=""):
        mark = OK if good else BAD
        say(f"  {mark} {label:<10} {name}" + (f"  ({detail})" if detail else ""))


def decrypt_entry(fernet, folder, entry, out_dir, results):
    """Decrypt + verify one manifest entry. Never raises; records the outcome."""
    stored_name = str(entry.get("stored_name", ""))
    shown_name = str(entry.get("original_name") or stored_name)

    if not STORED_NAME.match(stored_name):
        results.failed += 1
        return results.line(False, "FAILED", shown_name, f"invalid stored_name {stored_name!r} in manifest")

    enc_path = folder / stored_name
    if not enc_path.is_file():
        results.missing += 1
        return results.line(False, "MISSING", shown_name, f"{stored_name} not found")

    try:
        data = fernet.decrypt(enc_path.read_bytes())
    except InvalidToken:
        results.failed += 1
        return results.line(False, "FAILED", shown_name, "wrong key, or the .enc file was modified")

    if hashlib.sha256(data).hexdigest() != entry.get("sha256") or len(data) != entry.get("size"):
        results.failed += 1  # decrypted, but not the file that was uploaded: don't write it
        return results.line(False, "MISMATCH", shown_name, "sha256/size differ from manifest")

    fallback = stored_name[:-4] + guess_extension(data)
    written = save(out_dir, safe_filename(shown_name, fallback), data, shown_name, results)
    if written:
        results.ok += 1
        results.line(True, "verified", written.name, f"{len(data) / 1024:.1f} KB")


def save(out_dir, name, data, shown_name, results):
    """write_new_file, but a write problem (disk full, permissions...) only fails this file."""
    try:
        return write_new_file(out_dir, name, data)
    except (OSError, ValueError) as error:
        results.failed += 1
        results.line(False, "FAILED", shown_name, f"could not write output: {error}")
        return None


def decrypt_unlisted(fernet, enc_path, out_dir, results):
    """Decrypt a .enc that has no manifest entry. Fernet's HMAC still proves it is
    intact, but there's no sha256 to compare and no original name."""
    try:
        data = fernet.decrypt(enc_path.read_bytes())
    except InvalidToken:
        results.failed += 1
        return results.line(False, "FAILED", enc_path.name, "wrong key, or the .enc file was modified")
    written = save(out_dir, enc_path.stem + guess_extension(data), data, enc_path.name, results)
    if written:
        results.ok += 1
        results.line(True, "decrypted", written.name, "no manifest entry: sha256 not checked")


def run(argv=None):
    parser = argparse.ArgumentParser(
        description="Decrypt Secure File Vault .enc files (key from FERNET_KEY or --key-file).",
        allow_abbrev=False,  # otherwise "--key SECRET" would be accepted as "--key-file SECRET"
    )
    parser.add_argument("input", help="a .enc file, or an unzipped export folder with manifest.json")
    parser.add_argument("--out", default="decrypted", help="output folder (default: ./decrypted)")
    parser.add_argument("--key-file", help="file containing the key (or a FERNET_KEY=... line)")

    argv = sys.argv[1:] if argv is None else argv
    if any(arg == "--key" or arg.startswith("--key=") for arg in argv):
        say("Refusing --key: a key on the command line leaks into shell history and the process list.")
        say("Use the FERNET_KEY environment variable or --key-file FILE instead.")
        return 2
    args = parser.parse_args(argv)

    try:
        fernet = load_key(args.key_file)
        source = Path(args.input)
        if not source.exists():
            raise ToolError(f"Input not found: {source}")
        folder = source if source.is_dir() else source.parent
        manifest = load_manifest(folder)
    except ToolError as error:
        say(f"Error: {error}")
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = Results()
    entries = {str(e.get("stored_name")): e for e in manifest["files"]} if manifest else {}

    say(f"Decrypting {source} -> {out_dir}" + ("" if manifest else "  (no manifest.json: names and sha256 unavailable)"))

    if source.is_file():
        entry = entries.get(source.name)
        if entry:
            decrypt_entry(fernet, folder, entry, out_dir, results)
        else:
            decrypt_unlisted(fernet, source, out_dir, results)
    elif manifest:
        # Note: the same original name twice is handled by write_new_file -> "name (1).ext"
        for entry in manifest["files"]:
            decrypt_entry(fernet, folder, entry, out_dir, results)
        for name in manifest.get("missing", []):  # already missing when the export was made
            results.missing += 1
            results.line(False, "MISSING", str(name), "was missing on the server at export time")
        unlisted = sorted(p.name for p in folder.glob("*.enc") if p.name not in entries)
        if unlisted:
            say(f"  Note: {len(unlisted)} .enc file(s) not in manifest.json were skipped: {', '.join(unlisted)}")
    else:
        for enc_path in sorted(folder.glob("*.enc")):
            decrypt_unlisted(fernet, enc_path, out_dir, results)

    say(f"Summary: {results.ok} ok, {results.failed} failed, {results.missing} missing")
    return 0 if results.failed == 0 and results.missing == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
