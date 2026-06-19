---
id: F-0017
flow: project-support-membership
dimension: correctness
severity: P2
confidence: needs-verification
services: [rusaifin]
status: open
---
## Симптом
`deactivateProject` может падать с обращением к null-свойству (`$user->user->id`) после того, как проект уже деактивирован в обоих хранилищах → 500 и не записанный аудит-лог.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Project/ProjectController.php:821` — `'who' => $user->user->id`, тогда как соседние ветки используют `$user->id` (`activateProject():749`, `setProjectSupport():585`).
- `$user` — `UserService`; обращение `->user->id` отличается от соседних веток (нужна проверка контракта `UserService->user`).

## Триггер / repro
Если `UserService->user` для какого-то пути аутентификации null/не-объект → `History::Create` бросит на `->id` уже ПОСЛЕ `setDisabled(true)` и Core `update(status:inactive)` → проект деактивирован, запрос 500, History не записан.

## Корневая причина (гипотеза)
Копипаст-расхождение в обращении к автору действия.

## Радиус поражения
Только аудит-лог + код ответа деактивации; сама деактивация уже применена в обоих хранилищах. needs-verification: зависит от контракта `UserService->user`.

## Направление фикса (1-2 строки, НЕ реализовано)
Привести к `$user->id`, как в `activateProject`.
