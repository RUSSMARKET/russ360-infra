---
id: F-0114
flow: tasks
dimension: correctness
severity: P3
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
`GET /api/tasks` для не-админ ролей возвращает soft-удалённые задачи (`deleted=1`), в которых юзер числится executor/co_executor/observer: некорректная группировка OR ломает scope `deleted=0`.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Tasks/TaskController.php:33` — `Task::where('deleted', 0)`.
- `…/TaskController.php:51-54` — `default`-ветка: `->where('manager_id',$id)->orWhere('executor_id',$id)->orWhere('co_executor_id',$id)->orWhere('observer_id',$id)`.
- Итоговый WHERE: `deleted=0 AND manager_id=X OR executor_id=X OR co_executor_id=X OR observer_id=X` → из-за приоритета AND над OR распадается на `(deleted=0 AND manager_id=X) OR executor_id=X OR …`. Ветки executor/co/observer игнорируют `deleted=0`.

## Триггер / repro
Не-админ дёргает `GET /api/tasks` → задачи, где юзер executor/co/observer, отдаются даже soft-удалённые.

ВАЖНО (верифицировано): все OR-ветки ссылаются на СВОЙ id (`=X`), поэтому утечки ЧУЖИХ задач нет (субагент ошибочно заявил cross-user leak — опровергнуто при верификации). Дефект ограничен обходом soft-delete для своих задач → P3.

## Корневая причина (гипотеза)
OR-группа не обёрнута в замыкание; `deleted=0` применяется только к первой ветке.

## Радиус поражения
Листинг задач: появление soft-удалённых задач у не-админ ролей.

## Направление фикса
Обернуть OR-блок в `->where(function($q){ $q->where(...)->orWhere(...); })`, чтобы `deleted=0` применялся ко всей группе.
