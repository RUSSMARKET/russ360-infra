---
id: F-0022
flow: registration-auth
dimension: correctness
severity: P2
confidence: confirmed
services: [rusaiauth, rusaifin]
status: open
---
## Симптом
S2S HTTP-вызов `init` в rusaifin выполняется ВНУТРИ `DB::transaction` Postgres rusaiauth → длинная транзакция держит блокировки на время внешнего HTTP (до 5с).

## Доказательства (file:line)
- `rusaiauth/app/Http/Controllers/Auth/Registration/RegistrationController.php:90-117` — `DB::transaction(function() { $this->rusaifin->init(...); IdentityUser::firstOrCreate(...); $this->otp->issue(...); })`. `init` — сетевой вызов (timeout 5с).

## Триггер / repro
Медленный/висящий rusaifin на `init` → транзакция rusaiauth открыта до 5с (внутри `OtpService::issue` инвалидация+insert и `firstOrCreate`); под нагрузкой — рост открытых транзакций/коннекций к Postgres.

## Корневая причина (гипотеза)
HTTP-I/O внутри границы БД-транзакции.

## Радиус поражения
Деградация под нагрузкой/при тормозах rusaifin; не порча данных.

## Направление фикса (1-2 строки, НЕ реализовано)
Вынести `init` HTTP-вызов из транзакции; в транзакции держать только локальные записи.
