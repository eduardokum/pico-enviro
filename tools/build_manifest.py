#!/usr/bin/env python3
import os, json, hashlib, re
import os, json, hashlib, re

# filtros de exclusão
EXCLUDE_DIRS = {"tools", "__pycache__", "enviro/html", "phew", "documentation"}
EXCLUDE_FILES = {
    "manifest.json",
    "config.py",
    "install-on-device-fs",
    "enviro/version.py",
    ".micropico",
    "documentation.md",
    "lib/ota_light.py",
    "install-on-device-fs.ps1",
    "LICENSE",
    "README.md",
    "uf2-manifest.txt",
    "sync_time.txt",
    "last_time.txt",
    "daily_stats.json",
}
EXCLUDE_EXTENSIONS = {".pyc", ".zip", ".DS_Store"}

MANIFEST_PATH = "releases/manifest.json"
VERSION_FILE = "enviro/version.py"
BASE_URL = "https://raw.githubusercontent.com/eduardokum/enviro/main/"


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def read_current_version():
    try:
        with open(VERSION_FILE) as f:
            text = f.read()
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
        return match.group(1) if match else "0.0.0"
    except FileNotFoundError:
        return "0.0.0"


def write_new_version(version):
    os.makedirs(os.path.dirname(VERSION_FILE), exist_ok=True)
    content = f'__version__ = "{version}"\n'
    with open(VERSION_FILE, "w") as f:
        f.write(content)
    print(f"Atualizado {VERSION_FILE} → {version}")


def main():
    current = read_current_version()
    print(f"Versão atual: {current}")
    new_version = input("Nova versão (ENTER para auto-incrementar): ").strip()
    if not new_version:
        # auto-incrementa o último número semântico
        parts = current.split(".")
        if len(parts) < 3:
            parts += ["0"] * (3 - len(parts))
        parts[-1] = str(int(parts[-1]) + 1)
        new_version = ".".join(parts)
    print(f"Nova versão: {new_version}")
    write_new_version(new_version)

    files = []
    for d in ".":
        for root, dirs, names in os.walk(d):
            # ignora diretórios ocultos e listados
            dirs[:] = [
                x
                for x in dirs
                if not x.startswith(".")
                and not any(
                    skip in os.path.join(root, x).replace("\\", "/")
                    for skip in EXCLUDE_DIRS
                )
                and x not in EXCLUDE_DIRS
            ]

            for name in names:
                path = os.path.join(root, name)
                rel = os.path.relpath(path, ".").replace("\\", "/")

                # ignora arquivos ocultos e listados
                if (
                    name.startswith(".")
                    or name in EXCLUDE_FILES
                    or rel in EXCLUDE_FILES
                ):
                    continue
                ext = os.path.splitext(name)[1]
                if ext in EXCLUDE_EXTENSIONS:
                    continue

                if not os.path.isfile(path):
                    continue

                print(f"Adicionando arquivo {rel}")

                url = BASE_URL + rel
                sha = file_sha256(path)
                files.append({"path": "/" + rel, "url": url, "sha256": sha})

    manifest = {"version": new_version, "files": files}

    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Manifesto salvo em {MANIFEST_PATH} com {len(files)} arquivos.")


if __name__ == "__main__":
    main()
