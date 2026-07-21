---
id: F-0110
flow: motivation
dimension: data-integrity
severity: P1
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
Модель `Compensations` указывает на таблицу с КИРИЛЛИЧЕСКОЙ `с` (homoglyph U+0441) — `сompensation`, тогда как миграция создаёт ЛАТИНСКУЮ `compensation`. Все операции с компенсациями идут не в ту таблицу, что создаёт миграция.

## Доказательства (file:line)
- `rusaifin/app/Models/Compensations.php:13` — `protected $table = 'сompensation'`; hexdump строки: `27 d1 81 6f 6d 70 65 6e 73…` — байты `d1 81` = UTF-8 кириллической `с` (U+0441).
- `rusaifin/app/Http/Controllers/Motivation/CompensationController.php:243` — `'exists:сompensation,id'` (тоже кириллица — самосогласован с моделью).
- `rusaifin/database/migrations/2025_04_21_135214_create_sallary_tables.php:23` — `Schema::create('compensation', …)` (латиница).

## Триггер / repro
Свежий `php artisan migrate` создаёт латинскую `compensation`; любой запрос к `/api/compensations` обращается к кириллической `сompensation` → `Base table not found` (1146). На проде, вероятно, кириллическая таблица создана вручную/иным путём (иначе фича не работала бы) → дефект латентный: при пересоздании БД (dev-refresh, новый стенд) компенсации молча ломаются, dev-данные уходят в другую таблицу, чем прод.

## Корневая причина (гипотеза)
Опечатка-homoglyph при объявлении `$table`, рассинхрон с миграцией.

## Радиус поражения
Весь домен компенсаций (деньги/начисления). DR/CI/dev-refresh риск; расхождение dev↔prod схемы.

## Направление фикса
Привести имя таблицы к латинскому `compensation` в модели и `exists`-правиле; на проде проверить фактическое имя (`SHOW TABLES LIKE '%ompensation%'`) ПЕРЕД переименованием (возможна реальная кириллическая таблица с данными).

## Проверка статуса

**2026-07-21 — сверено с `origin/main`: дефект НА МЕСТЕ.**
`Compensations.php:13` — таблица `сompensation` с кириллической `с`; миграция создаёт латинскую `compensation`.
