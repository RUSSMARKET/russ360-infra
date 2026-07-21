---
id: F-0106
flow: requests-cards-magnit
dimension: correctness
severity: P1
confidence: confirmed
services: [rusaifin]
status: closed
---

## Симптом
`DELETE /api/ruchnik/{id}` без какой-либо проверки прав/владения: любой авторизованный пользователь (в т.ч. рядовой агент) может удалить ЛЮБОЙ ручник по id.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Requests/RequestController.php:526-540` — только `Validator … 'exists:ruchnik,id'`, затем `Ruchnik::find($id)->delete()`. Ни роли, ни `user_id == owner`.
- `rusaifin/routes/api.php:372` — `['auth:oauth', UserIsNotDisabled::class]` БЕЗ `CheckPermission` (контраст: motivation-роуты под `*.management`).
- `updateRuchnik` (`:399-416`) authz-гард имеет, `deleteRuchnik` — нет.

## Триггер / repro
Агент → `DELETE /api/ruchnik/{любой_id}` → 200, чужая запись удалена. Перебор id → массовое удаление.

## Корневая причина (гипотеза)
Забыт authz-гард + нет `CheckPermission` на роуте; деструктивная операция полностью открыта.

## Радиус поражения
Все ручники всех агентов/банков — деструктивный IDOR.

## Направление фикса
Добавить набор ролей/ownership как в `updateRuchnik`, либо `CheckPermission` на роут 372.

## Статус закрытия

Закрыто коммитом `5979d29` (rusaifin), проверено по коду на `origin/main` 2026-07-21.
В `deleteRuchnik` добавлена проверка владения (`user_id != $user->id` → 403).
