"""Скорер качества детекции ПД против разметки генератора.

Читает разметку генератора (JSON) и результат работы pipeline, для каждого
типа считает Precision/Recall/F1 по спанам (точное совпадение границ),
плюс долю негативных примеров с ложными срабатываниями.

CLI: python tools/score.py --dataset <path> --out <path>
Возвращает код 0, если F1 >= 0.95 по каждому типу и доля ложных
срабатываний <= 0.05, иначе код 1.
"""

import argparse
import json
import os
import sys

# Корень проекта (родитель каталога tools/) — чтобы импортировать app
# независимо от того, из какого каталога запущен скорер.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# UTF-8 для stdout/stderr (Windows-консоль по умолчанию cp1252 не выводит кириллицу).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from app.core.pipeline import Pipeline
from app.core.resolver import resolve
from app.detectors import all_detectors
from app.vault.memory import MemoryVault

#: Порог F1 по каждому типу (строгий режим).
_F1_THRESHOLD = 0.95
#: Допустимая доля ложных срабатываний на негативных примерах.
_FP_THRESHOLD = 0.05


def _pipeline_spans(pipeline: Pipeline, detectors: list, text: str) -> list:
    """Спаны, которые выдаёт pipeline: детекция + резолвер пересечений."""
    raw = pipeline._detect(text)
    return resolve(raw, detectors)


def _score_type(gold_spans: list[dict], pred_spans: list) -> tuple[float, float, float]:
    """Precision/Recall/F1 для одного типа по точному совпадению границ.

    Совпадение спана — точное совпадение границ [start:end] с эталоном.
    """
    gold = {(s["start"], s["end"]) for s in gold_spans}
    pred = {(s.start, s.end) for s in pred_spans}
    tp = len(gold & pred)
    fp = len(pred - gold)
    fn = len(gold - pred)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def _format_table(results: dict, fp_rate: float) -> str:
    """Форматирует таблицу F1 по типам."""
    lines = []
    lines.append(f"{'Тип':<16}{'Precision':>12}{'Recall':>12}{'F1':>12}")
    lines.append("-" * 52)
    for type_ in sorted(results):
        r = results[type_]
        lines.append(
            f"{type_:<16}{r['precision']:>12.4f}{r['recall']:>12.4f}{r['f1']:>12.4f}"
        )
    lines.append("-" * 52)
    lines.append(f"{'Ложные срабатывания (негатив)':<16}{fp_rate:>36.4f}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Скорер качества детекции ПД")
    parser.add_argument("--dataset", default="tests/golden_set.json", help="путь к разметке генератора")
    parser.add_argument("--out", default="tests/score_result.json", help="путь к выходному JSON")
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as f:
        dataset = json.load(f)

    pipeline = Pipeline(MemoryVault())
    detectors = all_detectors()

    # Собираем эталонные и предсказанные спаны по типам.
    gold_by_type: dict[str, list[dict]] = {}
    pred_by_type: dict[str, list] = {}
    negative_total = 0
    negative_fp = 0

    for example in dataset:
        text = example["text"]
        gold_spans = example["spans"]
        pred_spans = _pipeline_spans(pipeline, detectors, text)

        if example.get("negative"):
            negative_total += 1
            if pred_spans:
                negative_fp += 1

        for span in gold_spans:
            gold_by_type.setdefault(span["type"], []).append(span)
        for span in pred_spans:
            pred_by_type.setdefault(span.type, []).append(span)

    # Считаем метрики по каждому типу.
    types = sorted(set(gold_by_type) | set(pred_by_type))
    results: dict[str, dict] = {}
    for type_ in types:
        precision, recall, f1 = _score_type(
            gold_by_type.get(type_, []), pred_by_type.get(type_, [])
        )
        results[type_] = {"precision": precision, "recall": recall, "f1": f1}

    fp_rate = negative_fp / negative_total if negative_total else 0.0

    # Вывод таблицы.
    print(_format_table(results, fp_rate))

    # Общий результат.
    all_pass = all(r["f1"] >= _F1_THRESHOLD for r in results.values())
    fp_pass = fp_rate <= _FP_THRESHOLD
    overall = all_pass and fp_pass
    print(f"\nОбщий результат: {'PASS' if overall else 'FAIL'}")
    print(f"  F1 >= {_F1_THRESHOLD} по всем типам: {'да' if all_pass else 'нет'}")
    print(f"  Доля ложных срабатываний <= {_FP_THRESHOLD}: {'да' if fp_pass else 'нет'}")

    # Запись результата в JSON.
    payload = {
        "per_type": results,
        "false_positive_rate": fp_rate,
        "negative_total": negative_total,
        "negative_false_positives": negative_fp,
        "overall_pass": overall,
    }
    parent = os.path.dirname(args.out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())