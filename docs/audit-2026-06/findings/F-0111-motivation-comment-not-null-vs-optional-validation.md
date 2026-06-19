---
id: F-0111
flow: motivation
dimension: correctness
severity: P2
confidence: likely
services: [rusaifin]
status: open
---

## Симптом
Создание штрафа/компенсации/реферала без `comment` → SQL-ошибка вставки (500, NOT NULL violation) вместо 422: столбец `comment` NOT NULL без default, а валидация делает поле опциональным.

## Доказательства (file:line)
- `rusaifin/database/migrations/2025_04_21_135214_create_sallary_tables.php:19,27,35` — `$table->string('comment')` (NOT NULL, без default).
- Валидация в трёх контроллерах: `'comment' => ''` (пустой ruleset = опционально): `PenaltiesController.php:126`, `CompensationController.php:125`, `BringFriendController.php:125`.
- `Penalties::Create($validated)` (`PenaltiesController.php:131`) — без `comment` в `$validated` → INSERT без столбца → 1364/NOT NULL.

## Триггер / repro
`POST /api/penalties` с `user_id` и `sum`, без `comment` → 500.

## Корневая причина (гипотеза)
Рассинхрон схемы (NOT NULL) и правил (опционально).

## Радиус поражения
add/update во всех трёх сущностях мотивации.

## Направление фикса
`comment` `nullable` в правилах + миграции, либо `'comment' => 'nullable|string'` и дефолт `''`.
