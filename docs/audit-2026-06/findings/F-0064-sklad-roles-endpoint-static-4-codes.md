---
id: F-0064
flow: sklad-pages-roles
dimension: data-integrity
severity: P3
confidence: confirmed
services: [rusaisklad_back]
status: open
---

## Симптом

`GET /roles` (справочник для форм создания/редактирования участников проекта) возвращает только 4 кода `{admin, manager, supervisor, promoter}`, тогда как реальные Core membership-роли — 11 строк. UI не сможет корректно отобразить/назначить роль `agent` и прочие Core-роли.

## Доказательства (file:line)

- `rusaisklad_back/app/Http/Controllers/.../RoleController.php` (`index`/`get`) — `Role::orderBy('hierarchy')->get()`, читает таблицу `roles`.
- Таблица `roles` содержит только 4 кода: `database/seeders/RoleSeeder.php:17-20`, миграция `2025_02_03_000001_create_roles_and_rusaifin_user_fields.php:34-37`.

## Триггер / repro

Фронт строит выпадашку ролей участников из `/roles` → в списке нет `agent` (и прочих Core-ролей) → невозможно корректно показать или назначить роль агента в sklad UI.

## Корневая причина (гипотеза)

То же расхождение словарей 4 (sklad) vs 11 (Core), что и F-0061, спроецированное в справочник `/roles`. Отдельный симптом того же корня.

## Радиус поражения

UI форм ролей в sklad. Минор/латент относительно F-0061 (pages). Не порча данных, а неполнота справочника.

## Направление фикса

Синхронизировать справочник `roles` (или ответ `/roles`) с Core-словарём ролей — часть общего фикса F-0061.
