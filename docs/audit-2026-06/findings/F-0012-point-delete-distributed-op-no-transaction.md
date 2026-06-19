---
id: F-0012
flow: point-agent-binding
dimension: data-integrity
severity: P3
confidence: likely
services: [rusaifin, rusaicore]
status: open
---
## Симптом
`PointService::delete()` (удаление точки) выполняет серию Core-вызовов (закрытие всех assignment'ов + архивирование location) и затем soft-delete локальной строки без единой транзакции/компенсации; сбой Core посередине оставляет частичное состояние.

## Доказательства (file:line)
- `rusaifin/app/Services/Project/PointService.php:144-170` — последовательно: листинг open-assignments → `update(status:ended)` в цикле → `update(status:archived)` location → `$this->point->delete()`; без охвата транзакцией.
- `PointService.php:148` — комментарий «Core location deactivation handled in PointController/Step 4» устарел: никакого Step 4 в `deleteProjectPoint` нет, архивирование выполняется здесь же.

## Триггер / repro
Сбой Core (timeout/5xx) на середине цикла закрытия assignment'ов или на архивировании location → часть assignment'ов закрыта, location не заархивирован, локальная точка НЕ удалена (исключение прервёт до `->delete()`). Повтор идемпотентен по уже закрытым, но промежуточное состояние наблюдаемо.

## Корневая причина (гипотеза)
Распределённая операция (N+1 Core-вызовов + локальный delete) без саги/идемпотентного ретрая на уровне всей операции; устаревший комментарий маскирует фактический порядок.

## Радиус поражения
Редкое частичное состояние при удалении точки во время Core-недоступности; преимущественно операторская аномалия, восстановимая повтором.

## Направление фикса (1-2 строки, НЕ реализовано)
Обновить вводящий в заблуждение комментарий; рассмотреть закрытие всех assignment'ов одним bulk Core-вызовом либо пометку точки «archiving» для безопасного повтора.
