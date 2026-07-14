"""AutoFixGuard (ТЗ §7.10).

Некоторые преобразования слишком рискованно применять вслепую: переоформлять
фрагменты кода, таблицы с особым форматированием, ячейки во вложенных
таблицах и т.п. AutoFixGuard агрегирует эвристики риска. Если предикат
вернул False, оркестратор вместо изменения документа выдаёт нарушение
для ручной правки.
"""

from __future__ import annotations

from services.core.vkr_core.engine.stats import ParagraphStats


def may_apply_heading(ps: ParagraphStats) -> bool:
    if ps.in_table:
        return False
    if ps.length == 0:
        return False
    return True
