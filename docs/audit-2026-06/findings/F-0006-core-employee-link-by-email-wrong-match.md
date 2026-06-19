---
id: F-0006
flow: hiring-onboarding
dimension: data-integrity
severity: P3
confidence: needs-verification
services: [rusaifin, rusaicore]
status: open
---
## Симптом
Свежий hire может быть привязан к ЧУЖОМУ Core-employee при совпадении email — `users.core_employee_external_id` указывает на employee другого человека, и все последующие membership/assignment пишутся в чужого employee.

## Доказательства (file:line)
- `rusaifin/app/Services/Staff/EnsureCoreEmployeeLinked.php:36,43-53` — `matchExistingByEmail()` линкует пользователя к ПЕРВОМУ Core-employee с тем же email (`findByEmail`) и записывает его `core_employee_external_id` до создания нового employee.

## Триггер / repro
Оформление пользователя, email которого уже привязан к другому Core-employee (переиспользованный/общий корпоративный email, дубль email в `users`).

## Корневая причина (гипотеза)
Дедупликация по email без гарантии 1:1 уникальности email в `users` и без сверки ФИО/телефона.

## Радиус поражения
Linkage Core-employee; влияет на все последующие membership/assignment этого пользователя. Масштаб зависит от фактической уникальности `users.email` (не проверено — отсюда needs-verification).

## Направление фикса (1-2 строки, НЕ реализовано)
Подтвердить уникальность `users.email`; матчить по нескольким полям или только при подтверждённой 1:1 уникальности, иначе создавать нового employee.
