---
id: F-0103
flow: results-reporting
dimension: correctness
severity: P3
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
`getAgentResult` обращается к `$validated['date']` при правиле `sometimes` → запрос без `date` даёт undefined array key / 500 вместо 422.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Staff/PlansController.php:1052-1056` — правило `'date' => 'sometimes|integer|min:1|max:12'`, строкой ниже `$date = $validated['date'];` без `?? null`. OpenAPI декларирует `date` как required=true — рассинхрон с валидатором. (Доп.: параметр назван «дата», валидируется как номер месяца 1-12.)

## Триггер / repro
`GET /api/staff/{user_id}/result` без `date` → 500.

## Корневая причина (гипотеза)
Правило `sometimes` при последующем безусловном доступе к ключу.

## Радиус поражения
Запрос без `date`; 500 вместо корректного 422/дефолта.

## Направление фикса
`'date' => 'required|integer|min:1|max:12'` либо `$date = $validated['date'] ?? <default>`.
