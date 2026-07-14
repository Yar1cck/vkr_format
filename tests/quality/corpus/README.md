# Корпус для замера качества

Здесь лежат .docx, на которых считается F1 алгоритма обнаружения нарушений.

## Структура

```
tests/quality/corpus/
├── README.md           ← этот файл
├── synthetic/          ← синтетический корпус, генерируется автоматически
│   ├── clean_*.docx        # чистые работы (для precision)
│   ├── messy_*.docx        # с нарушениями (для recall)
│   ├── edge_*.docx         # edge-cases (объём)
│   └── _annotations.json   # эталон, сгенерирован вместе с .docx
└── user/               ← сюда кладите свои настоящие ВКР
    └── (пусто)
```

Содержимое (кроме README) — в gitignore. Корпус в репозиторий не коммитится:
синтетику можно перегенерировать одной командой, пользовательские ВКР —
персональные данные.

## Какие .docx нужны

Для честного замера precision/recall нужны **оба** типа:

| Тип | Зачем | Размер пула |
|-----|-------|-------------|
| **Чистые** — правильно оформленные ВКР | Считаем precision: алгоритм не должен ругаться на хорошую работу. Каждое ложное срабатывание = FP. | 3–5 |
| **«Грязные»** — реальные ВКР с известными нарушениями | Считаем recall: алгоритм должен найти настоящие проблемы. Каждое пропущенное = FN. | 5–10 |
| **Длинные** (80–150 страниц) | Замер производительности на реальных размерах | 1–2 |

Идеальный баланс: ~50/50 чистых и грязных, разной длины, разных тематик
(технические/экономические/гуманитарные — стили оформления варьируются).

## Как добавить свои ВКР

1. Положите .docx в [`tests/quality/corpus/user/`](user/).
2. Сгенерируйте шаблон разметки:
   ```bash
   python -m tests.quality.build_violation_annotations \
       --corpus tests/quality/corpus/user/ \
       --output tests/quality/corpus/user/_annotations.draft.json
   ```
3. Откройте `_annotations.draft.json` в редакторе. Для каждой записи проставьте:
   - `"expected": true` — это настоящее нарушение (TP, если алгоритм его нашёл)
   - `"expected": false` — это ложная тревога (FP)
4. Если алгоритм пропустил какое-то нарушение, добавьте запись вручную:
   ```json
   { "type": "heading_number_conflict", "expected": true, "_detected": false,
     "_note": "пропущена глава 3" }
   ```
5. Переименуйте в `_annotations.json` (без `.draft`).
6. Запустите замер:
   ```bash
   python -m tests.quality.measure_violations \
       --corpus tests/quality/corpus/user/ \
       --annotations tests/quality/corpus/user/_annotations.json \
       --output reports/user_violations_quality.json
   ```

## Регенерация синтетического корпуса

```bash
python -m tests.quality.generate_synthetic_corpus \
    --output tests/quality/corpus/synthetic/
```

Это перезапишет .docx и `_annotations.json` в синтетической папке. Содержимое
эталона детерминированно — два запуска подряд дают одинаковый результат.

## Замер на ОБЪЕДИНЁННОМ корпусе

`measure_violations.py` берёт по один путь --corpus. Чтобы прогнать на и
synthetic и user сразу — соберите оба корпуса под одним временным каталогом:

```bash
mkdir -p /tmp/full_corpus
cp tests/quality/corpus/synthetic/*.docx /tmp/full_corpus/
cp tests/quality/corpus/user/*.docx /tmp/full_corpus/
# объединить annotations:
python3 -c "
import json
a = json.load(open('tests/quality/corpus/synthetic/_annotations.json'))
b = json.load(open('tests/quality/corpus/user/_annotations.json'))
a['documents'].extend(b['documents'])
json.dump(a, open('/tmp/full_corpus/_annotations.json', 'w'), ensure_ascii=False, indent=2)
"
python -m tests.quality.measure_violations \
    --corpus /tmp/full_corpus \
    --annotations /tmp/full_corpus/_annotations.json \
    --output reports/full_violations_quality.json
```
