---
id: F-0048
flow: sklad-assignments
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaisklad_back]
status: open
---
## Симптом
`updatePromoters` возвращает 200 с полным списком запрошенных промоутеров, но для части из них ассигнмент к запрошенному supervisor мог быть НЕ создан (тихо пропущен). UI считает перепривязку успешной, фактически промоутер остался у старого/чужого supervisor. При другой раскладке гонки тот же путь даёт 500 (unique-violation).

## Доказательства (file:line)
- `app/Services/Assignments/AssignmentService.php:140-153` — в цикле создания: `$exists = Assignment::where('project_id',…)->where('promoter_id',$promoterId)->exists(); if (!$exists) { Assignment::create(...) }`. Если строка уже есть (вставлена параллельным запросом между cross-check на `:127-137` и циклом), `create` молча пропускается.
- `:155-158` — ответ строится из входного списка: `User::whereIn('id', $promoterIds)->get()`, а не из фактически записанных assignment-строк.
- `app/Http/Controllers/API/Assignments/AssignmentController.php:~331-350` — cross-supervisor pre-check выполняется ДО `DB::transaction` (нетранзакционный TOCTOU), затем сервис повторяет проверку уже после деструктивного `delete` (`:122-124`).
- Уникальный индекс `(project_id, promoter_id)` (миграция `2024_01_15_000004`) — при гонке без exists-skip даёт `QueryException`/500.

## Триггер / repro
Два почти одновременных `updatePromoters` для разных supervisor (A и B) с одним промоутером X. B проходит cross-check (X ещё не у A), затем A коммитит вставку X→A; в B `exists` уже true → X→B молча пропускается, B получает 200 со списком, содержащим X. X фактически у A.

## Корневая причина (гипотеза)
«Defensive» `exists`-skip конвертирует конфликт уникальности в тихий no-op вместо ошибки; ответ формируется из входного списка, а не из реально записанных строк; внешний pre-check нетранзакционный и дублирует внутренний.

## Радиус поражения
Рассинхрон UI/факта по иерархии supervisor↔promoter. Далее затрагивает `takeFromPromoter` и снапшот балансов инвентаризации (читают supervisor из `Assignment`). Проявляется при конкурентной ручной перепривязке.

## Направление фикса (1-2 строки, НЕ реализовано)
Убрать тихий skip — полагаться на unique-constraint и ловить `QueryException`, либо строить ответ из фактически записанных assignment-строк; всю логику (delete+check+insert) держать в одной транзакции без внешнего pre-check.
