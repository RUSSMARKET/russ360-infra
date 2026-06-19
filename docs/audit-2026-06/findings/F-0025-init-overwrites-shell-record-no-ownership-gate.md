---
id: F-0025
flow: registration-auth
dimension: correctness
severity: P3
confidence: likely
services: [rusaifin]
status: open
---
## Симптом
`init` поднимает существующую незавершённую shell-запись и перезаписывает `name`/`surname`/`referal` без проверки владения → подмена ФИО/реферала чужой незавершённой регистрации.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Internal/Registration/RegistrationInternalController.php:53-79` — если `User::where('phone')` существует и `password === null`, то `$existing->fill($payload)->save()` (перезапись name/surname/referal). Гейта владения нет.

## Триггер / repro
startPhone на чужой ещё-не-завершённый phone (shell без password) → перезапись ФИО/referal shell-записи. Пароль без OTP не поставится, поэтому эскалация ограничена подменой ФИО/referal до завершения настоящим владельцем.

## Корневая причина (гипотеза)
`init` идемпотентно мутирует чужую незавершённую запись без привязки к подтверждённой OTP-сессии.

## Радиус поражения
Узкий; смягчён OTP-гейтом на setPassword. (Граничит с security — в scope как correctness, не блокирующее.)

## Направление фикса (1-2 строки, НЕ реализовано)
`init` только создаёт при отсутствии; обновление ФИО — после подтверждения OTP; либо хранить referal/ФИО на стороне identity до setPassword.
