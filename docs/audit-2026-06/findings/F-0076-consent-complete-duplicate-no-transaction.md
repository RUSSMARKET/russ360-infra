---
id: F-0076
flow: product-consent
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---

## Симптом
Конкурентный двойной `POST /consent-session/{token}/complete` создаёт дубли строк в `customer_profile_consents` (юридический артефакт согласия на обработку ПД) — идемпотентность держится только на неблокирующем чтении, без транзакции/lock и без UNIQUE.

## Доказательства (file:line)
- `rusaifin/app/Services/ProductConsent/ProductConsentService.php:250-320` — `complete()` идёт БЕЗ `DB::transaction`/`lockForUpdate` (контраст: `startSession` обёрнут в транзакцию).
- `…/ProductConsentService.php:252` — единственная защита от повтора: `if ($session->consented_at) return …` — TOCTOU: два запроса читают `null` до того, как любой запишет `consented_at` (строка 313).
- `…/ProductConsentService.php:291` — `createFullConsent(...)` вызывается безусловно → `CustomerProfileConsent::create(...)`.
- Миграция `customer_profile_consents` — нет `unique` на `product_consent_session_id`, БД дубль не ловит.

## Триггер / repro
Двойной клик / повтор сети на verified form-flow сессии → два одновременных `complete` оба видят `consented_at = null` → два вызова `createFullConsent` → 2 строки consent с одинаковым `product_consent_session_id`.

## Корневая причина (гипотеза)
Отсутствие транзакции с `lockForUpdate` по сессии + отсутствие уникального ключа на `customer_profile_consents.product_consent_session_id`. Тот же класс TOCTOU-идемпотентности, что F-0028/F-0042 в других потоках, но новый эндпоинт/таблица.

## Радиус поражения
Дубли юридических записей согласия → искажение аудита/отчётности по СОПД; неоднозначность «какое согласие действительно».

## Направление фикса
Обернуть `complete` в `DB::transaction` с `lockForUpdate` по сессии + UNIQUE на `customer_profile_consents(product_consent_session_id)` (или `session_id + consent_text_version`).
