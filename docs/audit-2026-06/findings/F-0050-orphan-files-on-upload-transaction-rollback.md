---
id: F-0050
flow: transfer-documents
dimension: data-integrity
severity: P2
confidence: confirmed
services: [rusaisklad_back]
status: open
---
## Симптом
При откате транзакции загрузки документа (`uploadSenderDocument`/`uploadReceiverDocument`/`adminAttachReceiverFile`) физический файл остаётся на диске (`public/inventory-docs/...`), хотя строки `inventory_document_files` откатываются. Накапливаются orphan-файлы, недостижимые через API, но физически лежащие на публичном диске.

## Доказательства (file:line)
- `app/Services/Inventory/InventoryDocumentService.php:~781` — `$path = $file->store($directory, $disk)` (local-драйвер пишет на диск синхронно) вызывается ВНУТРИ `DB::transaction` (например внутри `uploadReceiverDocument` `:342-412`, цикл `:375-377`).
- `:~784` — `InventoryDocumentFile::create(...)` откатится при любом последующем исключении в транзакции (`$transfer->save()`, deadlock на `lockForUpdate`, ошибка в `markPendingManagerReview`), но `Storage::delete` для уже записанного файла не вызывается — компенсации нет.
- Единственное физическое удаление — `deleteDocumentForTransfer` (`:~944`); на путь отката не распространяется.

## Триггер / repro
Загрузка файла → после `store()` транзакция падает (deadlock на `lockForUpdate`, гонка статусов, любое исключение в `$document->save()`/`$transfer->save()`). Файл на диске остаётся без записи в БД.

## Корневая причина (гипотеза)
Сайд-эффект на файловой системе выполняется внутри DB-транзакции без отложенного коммита/компенсации (`DB::afterCommit` или `Storage::delete` в catch).

## Радиус поражения
Дисковое пространство, orphan-файлы в `public/inventory-docs` (публичный диск) без ссылки из БД. Целостность учётных данных не страдает; латентное накопление мусора + потенциальная утечка публично-доступных файлов.

## Направление фикса (1-2 строки, НЕ реализовано)
Писать файлы вне транзакции (store → собрать пути → транзакция только на БД) либо регистрировать `Storage::delete` на откате (try/catch) / коммитить пути через `DB::afterCommit`.
