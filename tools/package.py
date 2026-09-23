"""Упаковка решения в чистый zip для проверки качества кода.

Исключает запрещённые каталоги (см. ТЗ §7.1): зависимости, сборку,
служебные каталоги. Включает только исходный код.
"""

import os
import sys
import zipfile

# UTF-8 для stdout (Windows-консоль cp1252 не выводит кириллицу).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

#: Каталоги, которые исключаются из архива.
_EXCLUDE_DIRS = {
    "node_modules", ".venv", "venv", "env",
    "target", "build", "dist", "out", "bin", "obj",
    ".git", ".idea", "__pycache__", ".pytest_cache", "coverage", ".work",
}

#: Файлы, которые исключаются из архива.
_EXCLUDE_FILES = {".gitignore", ".gitattributes", "solution.zip"}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _should_exclude(rel_path: str) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    return any(p in _EXCLUDE_DIRS for p in parts) or rel_path in _EXCLUDE_FILES


def main() -> None:
    out_path = os.path.join(ROOT, "solution.zip")
    count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            # Убираем исключённые каталоги из обхода.
            dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS]
            for fname in filenames:
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, ROOT)
                if _should_exclude(rel):
                    continue
                zf.write(full, rel)
                count += 1
    size = os.path.getsize(out_path)
    print(f"Создан {out_path}: {count} файлов, {size} байт")


if __name__ == "__main__":
    main()