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
    ".kilo",  # рабочие каталоги агентов и их worktree
    "logs",   # рантайм-логи
}

#: Файлы, которые исключаются из архива. Пути — через "/".
_EXCLUDE_FILES = {
    ".gitignore", ".gitattributes", "solution.zip",
    # Датасеты и отчёты прогонов: ТЗ §7.1 запрещает их в архиве,
    # пересоздаются через tools/gen_dataset.py и tools/score.py.
    "tests/golden_set.json", "tests/score_result.json",
    # Рабочие файлы агентов — не исходный код решения.
    "AGENTS.md", "WORKLOG.md",
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _should_exclude(rel_path: str) -> bool:
    # Путь нормализуем к "/": на Windows relpath даёт "\", и сравнение
    # с _EXCLUDE_FILES по сырому пути молча не срабатывало бы.
    norm = rel_path.replace("\\", "/")
    return any(p in _EXCLUDE_DIRS for p in norm.split("/")) or norm in _EXCLUDE_FILES


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