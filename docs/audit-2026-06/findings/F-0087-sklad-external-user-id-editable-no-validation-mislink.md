---
id: F-0087
flow: sklad-projects-admin
dimension: data-integrity
severity: P3
confidence: likely
services: [rusaisklad_back, rusaicore]
status: open
---

## Симптом
Admin store/update в sklad принимает `external_user_id` как `nullable|string|max:255` без проверки, что такой Core employee существует и не занят другим local-юзером. Это anchor-поле, по которому резолвится local↔Core маппинг → произвольное значение даёт silent mis-link.

## Доказательства (file:line)
- `rusaisklad_back/app/Http/Requests/.../StoreUserRequest`/`UpdateUserRequest::rules()` — `'external_user_id' => ['nullable','string','max:255']` (нет `exists`/uniqueness против Core).
- `rusaisklad_back/app/Services/User/UserManagementService.php:20-65` — пишет поле as-is (mass-assignment; `external_user_id` в `$fillable` модели `User`).
- `rusaisklad_back/app/Domain/Core/Projection/LocalExternalIdMap.php:114-138` — `userLocalId()`/`primeUserLocalIds()` резолвят local↔Core именно по `external_user_id`.

## Триггер / repro
Admin задаёт `external_user_id`, равный несуществующему/чужому Core external_id. Несуществующий → все Core-reads по юзеру тихо вернут пусто. Чужой при отсутствии DB-unique → два local-юзера на один Core employee → недетерминированный `userLocalByExternal`.

## Корневая причина (гипотеза)
Anchor-поле редактируемо руками без валидации против Core и (вероятно) без unique-индекса. Требует намеренного ввода admin'ом, поэтому P3.

## Радиус поражения
Неправильный маппинг Core-данных для затронутого юзера; при коллизии — недетерминированный резолв. Ограничено admin-операциями.

## Направление фикса
Убрать `external_user_id` из admin-editable полей (anchor должен ставиться только синком) либо валидировать против Core + добавить unique-индекс. Верифицировать наличие unique-индекса в миграции.
