---
id: F-0053
flow: staff-visibility
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---
## Симптом
`StaffService::hasAccessToUser()` бросает фатал (500) вместо корректного отказа (4xx), когда целевой пользователь вне области видимости viewer'а. Fail-closed (доступ не выдаётся), но ломает запрос.

## Доказательства (file:line)
- `app/Services/Staff/StaffService.php:754` — `$this->getStaff($user->role_id)[0]->users()->firstWhere('id', $user->id)->exists();`
- `getStaff` (default-ветка, `StaffService.php:322-336`) — `Role::...->whereHas('users', whereIn rolesIds)->get()`. Если ни один user целевой роли не входит в scope viewer'а — роль исключается `whereHas`, коллекция пустая → `[0]` = `null` → `null->users()` фатал. Если роль есть, но `$user->id` не в scope — `firstWhere('id',…)` = `null` → `null->exists()` фатал.
- `app/Http/Controllers/Staff/PlansController.php:1468` — `if(!$staff->hasAccessToUser($user_id))` рассчитан на boolean (вернул бы 4xx), но до него исполнение не доходит из-за исключения.

## Триггер / repro
GROUP_LEADER/RG/PM вызывает добавление отчёта по смене (`PlansController` addReport) с `user_id`, который не входит в его область видимости (или агент выпал из scope из-за F-0052) → 500 вместо отказа.

## Корневая причина (гипотеза)
Небезопасное обращение `[0]` к возможно-пустой коллекции и цепочка `firstWhere(...)->exists()` без null-проверки.

## Радиус поражения
Любой вызов `hasAccessToUser` не-привилегированным viewer'ом для невидимого/несуществующего user'а (PlansController addReport; будущие вызовы). Fail-closed (нет утечки доступа), но 500 вместо 4xx ломает легитимные граничные запросы.

## Направление фикса (1-2 строки, НЕ реализовано)
`$roles = $this->getStaff($user->role_id); return $roles->isNotEmpty() && $roles[0]->users->contains('id', $user->id);` (через загруженную связь, с null-guard).
