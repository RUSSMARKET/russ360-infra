---
id: F-0107
flow: requests-cards-magnit
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
`POST /api/ruchnik` принимает произвольный `user_id` из тела без проверки роли вызывающего → агент может создать ручник от имени любого другого пользователя (приписать код чужому).

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Requests/RequestController.php:285` — `user_id` валидируется как `exists:users,id`; `:294` — `$user_id = $validated['user_id'] ?? $user->id` без гейта по роли.
- `rusaifin/routes/api.php:370` — без `CheckPermission`.

## Триггер / repro
Агент → `POST /api/ruchnik` с `user_id` другого агента + уникальный `code` → запись создана на чужого.

## Корневая причина (гипотеза)
Нет гейта роли при `user_id != self`.

## Радиус поражения
Целостность принадлежности ручников; искажение выгрузок/мотивации, привязанной к ручникам.

## Направление фикса
Разрешать `user_id != self` только ролям руководителей (как в update/export).
