---
id: F-0024
flow: registration-auth
dimension: correctness
severity: P3
confidence: likely
services: [rusaiauth]
status: open
---
## Симптом
Повторный запрос OTP (resend) инвалидирует прежний код, а троттлинг идёт по IP, не по телефону → на параллельных вкладках/устройствах для одного номера «код неверный».

## Доказательства (file:line)
- `rusaiauth/app/Domain/Identity/Services/OtpService.php:28-32` — `issue` помечает `consumed_at` всем активным кодам канал+destination.
- `OtpService.php:60-87` — `verify` берёт `orderByDesc('id')` единственный активный.
- `routes/api.php:23-24` — `startPhone` троттлится `throttle:5,1` по IP, не по phone.

## Триггер / repro
Два startPhone на один phone (две вкладки) → второй инвалидирует код первого; UX-сбой «код не верный». Порчи данных нет.

## Корневая причина (гипотеза)
Троттлинг по IP, не по destination; resend всегда инвалидирует прежний код.

## Радиус поражения
Редкий UX-кейс; не data-integrity.

## Направление фикса (1-2 строки, НЕ реализовано)
Троттлить resend по phone; опционально cooldown между issue.
