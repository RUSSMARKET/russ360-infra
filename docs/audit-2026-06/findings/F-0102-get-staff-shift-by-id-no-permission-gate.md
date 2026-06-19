---
id: F-0102
flow: results-reporting
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
`GET /api/staff/result/{user_id}/shift/{shift_id}` (`getStaffShiftById`) не имеет permission-гейта на роуте: любой аутентифицированный не-disabled пользователь (CLIENT, BUSINESS_COACH, ANALYST — любая роль кроме AGENT/REGISTERED) может читать данные смены и отчёты любого пользователя. Шире, чем F-0101.

## Доказательства (file:line)
- `rusaifin/routes/api.php:227` — `->middleware(['auth:oauth', UserIsNotDisabled::class])` (нет `CheckPermission`, в отличие от роутов 222-225).
- `rusaifin/app/Http/Controllers/Staff/PlansController.php:971-998` — единственная проверка `:983-990` блокирует только AGENT/REGISTERED, читающих чужой `user_id`; для всех прочих ролей сверки зоны нет.

## Триггер / repro
Пользователь с ролью CLIENT/BUSINESS_COACH → `GET /api/staff/result/{любой_user_id}/shift/{shift_id}` (shift валидируется как принадлежащий user_id) → 200 с отчётами смены. Перебор id → выгрузка чужих смен.

## Корневая причина (гипотеза)
Отсутствует permission-гейт на роуте + нет per-row scope в контроллере для не-AGENT ролей. Read-only операционные данные, внутренние акторы → P2 (но широкий охват ролей — кандидат на повышение).

## Радиус поражения
Любая роль вне AGENT/REGISTERED → чтение смен/отчётов любого пользователя.

## Направление фикса
Добавить `CheckPermission:staff.management` на роут 227 + scope-сверку `hasAccessToUser($user_id)` для непривилегированных.
