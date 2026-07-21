---
id: F-0119
flow: requests-cards-magnit
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом

`POST /api/ruchnik/export/{ruchnik_type_slug}` без `agent_id` выгружает ВСЕ ручники указанного типа по всем проектам. Гейт — только внутренний `roleIn` (роут вообще без `CheckPermission`), без membership/point/project-скоупа.

## Доказательства (file:line)

- `routes/api.php:384` — `ruchnik/export/{ruchnik_type_slug}` под `['auth:oauth', UserIsNotDisabled::class]` — НЕТ `CheckPermission`.
- `app/Http/Controllers/Requests/RequestController.php:707` (`exportRuchnik`) → `RuchnikExport` (≈:38-46) — выборка по типу без скоупа зоны; опциональный `agent_id` — единственное сужение.

## Триггер / repro

GROUP_LEADER/любая прошедшая `roleIn` роль: `POST /api/ruchnik/export/otp` без `agent_id` → выгрузка всех ручников типа OTP по всем агентам/проектам.

## Корневая причина (гипотеза)

Экспорт-путь не применяет `getRuchnikAssignableUserIds`/zone-скоуп, которым пользуются list-методы (`getRuchnik`); опирается на необязательный `agent_id`.

## Радиус поражения

Кросс-проектная утечка ручников (номеров заявок партнёра) + связанных PII агентов. P2.

## Направление фикса (не реализовано)

Скоупить выборку экспорта по зоне viewer'а (как `getRuchnik`/`getRuchnikAssignableUserIds`); привилегированным — явная проверка членства проекта.
