---
id: F-0003
flow: hiring-onboarding
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaifin]
status: open
---
## Симптом
Аудит-лог (`history`) при оформлении и смене статусов теряет, КТО выполнил действие: поле `who` затирается id целевого пользователя, `whom` не заполняется. Невозможно установить ответственного за кадровое действие.

## Доказательства (file:line)
- `rusaifin/app/Http/Controllers/Staff/StaffRegistrationController.php:1003-1008` (и идентичные блоки `:1081-1086, :373-378, :470-475, :652-657, :715-720, :785-790, :853-858, :1176-1180`) — `History::Create([... 'who' => $who->...->id, 'who' => $whom->...->id, ...])`: ДУБЛИРУЮЩИЙСЯ ключ `'who'`; PHP оставляет последний → `who = whom = target`, актёр потерян, ключ `'whom'` отсутствует.
- Контраст — корректные методы: `confirmRegistrationData()` `:1228-1232` и `unconfirmRegistrationData()` `:1273-1277` пишут `'who'`+`'whom'`.
- `app/Models/System/History.php:12-19` — fillable содержит и `who`, и `whom` (колонка существует, должна писаться).

## Триггер / repro
Любой `setRegistrationRole`, `setRegistrationStatus`, `setNewRegistrationStatus`, `updateRegistration`, `updateRegistrationPassport`, `deleteRegistrationStaff`, `unblockRegistrationStaff`, `setStaffSigning` → запись истории с подменённым актёром.

## Корневая причина (гипотеза)
Copy-paste: второй `'who'` должен был быть `'whom'`.

## Радиус поражения
Весь аудит-trail раздела «Оформление» (8+ методов). Поведение пользователя не ломается, но данные истории недостоверны — нельзя выяснить ответственного.

## Направление фикса (1-2 строки, НЕ реализовано)
Заменить второй `'who'` на `'whom'` во всех перечисленных блоках `History::Create`.
