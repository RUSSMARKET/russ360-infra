---
id: F-0054
flow: staff-visibility
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---
## Симптом
Для REGIONAL_DIRECTOR / PROJECT_MANAGER товарная матрица (видимость продуктов) берётся только из ПЕРВОГО доступного проекта; продукты остальных проектов viewer'а невидимы.

## Доказательства (file:line)
- `app/Services/User/UserService.php:337-350` — `$accessibleProjectIds = …accessibleLocalProjectIdsForViewer($user) ?? []; … DB::table('projects_products')->where('project_id', $accessibleProjectIds[0])`. Используется только `[0]`, хотя метод возвращает список ВСЕХ проектов-членств.

## Триггер / repro
RG/РП, привязанный к 2+ проектам, открывает список продуктов → видит товары только одного (первого по выборке) проекта.

## Корневая причина (гипотеза)
Жёсткое `[0]` вместо `whereIn($accessibleProjectIds)`.

## Радиус поражения
Видимость продуктов у мультипроектных RD/PM. Граничный, но реалистичный кейс (РГ обычно ведёт несколько проектов).

## Направление фикса (1-2 строки, НЕ реализовано)
Заменить `->where('project_id', $accessibleProjectIds[0])` на `->whereIn('project_id', $accessibleProjectIds)`.
