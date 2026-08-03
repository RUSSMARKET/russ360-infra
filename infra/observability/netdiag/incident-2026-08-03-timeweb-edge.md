# Инцидент 2026-08-03: выборочная недоступность rusaifin.ru

## Итог диагностики

Origin, nginx, Nuxt и API остаются работоспособными. Сбой возникает на пути
между российской пользовательской сетью и публичным адресом Timeweb до HTTP.
VPN и авиарежим создают новый сетевой путь и временно восстанавливают доступ.

Наиболее вероятный класс причины — выборочная фильтрация/деградация трафика
на промежуточном оборудовании российских операторов (в том числе ТСПУ) для
маршрута к сети Timeweb. Timeweb описывал такой же внешний инцидент 5 июня
2026 года: зависимость от оператора и браузера при штатной работе серверов.

Источники:

- [Сообщение Timeweb об избирательной недоступности](https://hosting.kitchen/timeweb/seychas-chast-polzovateley-stalkivaetsya-s-nedostupnostyu-podklyucheniya-k-infrastrukture-pri-ispolzovanii-setey-rossiyskih-operatorov-svyazi.html)
- [Текущий статус инфраструктуры Timeweb](https://timeweb.cloud/live)
- [Инструкция Timeweb по сетевой недоступности](https://timeweb.com/ru/docs/virtualnyj-hosting/vozmozhnye-oshibki-i-ih-ustranenie/setevaya-nedostupnost/)

## Наблюдаемые доказательства

- iPhone 15, iOS 18.7, Yota без VPN воспроизводит бесконечную загрузку.
- При одном воспроизведении HTML, API и документы завершились с `200`, а
  TCP capture не показал потерь после установленного TLS-сеанса.
- В параллельной iPhone-сессии в 14:05–14:06 МСК новый HTTP/2-сеанс сначала штатно
  получил HTML, CSS и основной Nuxt bundle (~329 КБ), полностью подтверждённый
  TCP ACK. Приложение смонтировалось за 901 мс, `/api/auth/session` и
  `/api/auth/csrf` вернули `200`. Затем одновременно получили transport error
  `/api/user/types` и группа динамических Nuxt chunks. На origin ни один из
  этих запросов не пришёл. Это фиксирует исчезновение маршрута посреди
  работающей пользовательской сессии, а не ошибку TLS, Nuxt или API. Эта
  сессия не атрибутируется тестовому телефону Yota.
- Без VPN, Wi-Fi, авиарежима или иных действий путь восстановился сам. В
  14:14:20 МСК Safari открыл новое HTTP/2-соединение с подтверждённым Yota
  CGNAT-IP `94.25.*`
  (`connection_requests=1`), после чего HTML, API и изображения снова штатно
  пришли с `200`. Это не продолжение старого HTTP-ответа, а успешный retry после
  окончания временного сетевого blackhole.
- После полного закрытия и нового запуска Safari сбой сразу вернулся. В
  14:17:06–14:17:35 МСК capture зафиксировал четыре новых TCP-потока: во всех
  завершились `SYN -> SYN/ACK -> ACK`, но ни в одном TLS ClientHello не дошёл
  до origin. Поэтому на этом шаге nginx и приложение ещё не участвуют.
- При последующих чистых открытиях Safari сервер не получил HTTP-запрос.
- В одном зависшем потоке телефон передал ClientHello, после чего почти весь
  TLS-ответ сервера остался без ACK и многократно retransmit-ился.
- В отдельном capture новые TCP-потоки завершали SYN/SYN-ACK/ACK, но
  ClientHello не доходил до origin.
- После авиарежима изменился CGNAT-путь: HTML, API и все фотографии снова
  пришли с `200` за десятки миллисекунд.
- VPN стабильно восстанавливал работу как на мобильном интернете, так и Wi-Fi.
- Три разных имени и сертификата на одном IP показывали одинаковый сбой:
  `fintech.rusaifin.ru`, `fintech.russ-market.ru`, `a.shake.fvds.ru`.
- DNS A-записи корректны: четыре authoritative NS возвращают один IPv4,
  публичные резолверы согласованы. AAAA отсутствует, потому что origin пока не
  имеет глобального IPv6-адреса или IPv6 default route.
- DNSSEC не является причиной инцидента, но настроен незавершённо: зона отдаёт
  DNSKEY/RRSIG, а в родительской зоне `.ru` отсутствует DS. Кроме того, `ns3`
  отдаёт DNSKEY, отличный от остальных Timeweb NS. Сейчас валидирующие
  резолверы считают зону unsigned; публиковать DS до синхронизации ключей
  Timeweb нельзя.

## Отброшенные гипотезы и canary

- HTTP/2: fintech-only HTTP/1.1 canary не помог и полностью откатан.
- Размер сертификата: ECDSA сократил цепочку примерно с 6 КБ до 3,2 КБ и
  дал один успешный заход, но повторный чистый запуск снова завис.
- Обычный PMTU blackhole: runtime `tcp_mtu_probing=2`, MSS 1024 не помог;
  настройка возвращена в исходное значение `0`.
- DNS и приложение: не объясняют отсутствие HTTP и зависание нескольких
  разных SNI на одном адресе; кроме того, приложение успевает смонтироваться
  до синхронного transport failure запросов, не дошедших до nginx.
- Порт 8443: один раз отдал HTML и assets, но прямой Apache закономерно
  вернул `404` на same-origin `/api/*`, потому что BFF proxy находится в nginx.

## Текущее состояние после canary

- fintech снова использует HTTP/2.
- `net.ipv4.tcp_mtu_probing=0` (исходное значение).
- RSA-сертификаты сохранены как fallback.
- На fintech и server добавлены валидные ECDSA-сертификаты как безопасная
  оптимизация, но они не считаются корневым исправлением.
- Диагностические nginx-логи, метрики, bounded pcap и iOS beacon активны.

## Второй публичный ingress-canary

На существующем резервном VDS `a1.shake.fvds.ru` поднят отдельный вход для
проверки гипотезы о проблемном публичном IP/маршруте:

- `edge2.rusaifin.ru` указывает на `82.146.45.198`, основной origin остаётся
  на `82.146.57.149`;
- nginx принимает HTTP/2 и TLS 1.2/1.3, а затем проксирует запросы на origin с
  SNI и проверкой его сертификата;
- сертификат Let's Encrypt для `edge2.rusaifin.ru` действителен до
  2026-11-01, автоматическое продление и reload nginx включены;
- firewall узла принимает только SSH, HTTP и HTTPS;
- HTML, `/products/`, Nuxt bundle, API, OIDC discovery и OAuth redirect
  проверены снаружи; ответы помечаются заголовком
  `X-Rusaifin-Canary-Ingress: a1-shake`;
- API и OIDC XHR в runtime HTML направляются на тот же canary-origin, поэтому
  проверка не зависит от cross-origin CORS;
- в OAuth-клиент `rusaifin-spa` добавлены callback URI
  `https://edge2.rusaifin.ru/auth/callback` и временный прямой IP callback.

На 15:58 МСК все четыре authoritative NS Timeweb отдавали одинаковую A-запись
и SOA serial `2026080300`; публичные резолверы также видели новый адрес.

Ограничение: оба VDS находятся у FirstVDS/Timeweb. Новый адрес относится к
другой подсети, но не даёт независимость от провайдера/ASN. Поэтому это точный
canary для различения «конкретный IP/подсеть» и «вся сеть провайдера», но не
окончательная отказоустойчивая архитектура.

Первый реальный тест с iPhone/Yota без VPN в 16:36–16:39 МСК не воспроизвёл
транспортное зависание: HTML, основной bundle, динамические chunks и SSO
callback стабильно доходили через `edge2` с `200`. OAuth token exchange также
завершался с `200`. При этом SPA показывала белый экран и повторяла SSO-поток:
после token exchange запрос `/api/auth/me` не приходил на canary. Причина —
раннее разрешение legacy API hostname в уже собранном production bundle до
гидрации Nuxt runtime config. На canary добавлен ранний same-origin shim для
`fetch`/XHR, который оставляет такие запросы на новом ingress даже при
закешированном bundle. Это прикладная совместимость тестового hostname, а не
изменение вывода о сетевом инциденте.

Повторный тест в 16:48–16:51 МСК снова стабильно получил с `edge2` HTML
`/products/` и `/auth/`, но ни один следующий `/oauth/authorize` на canary не
пришёл. В журнале origin SSO новых запросов от Yota-IP также не было. Значит,
после отрисовки страницы браузер уходил на абсолютный `sso.rusaifin.ru` и
возвращался на старый проблемный публичный путь. После этого canary расширен
на полный SSO browser-flow: OIDC runtime issuer, authorize/token/logout,
страницы входа, SSO API и их статические assets остаются на
`edge2.rusaifin.ru`, а внутренняя прокси-связь использует SNI
`sso.rusaifin.ru`. Внешняя проверка подтвердила цепочку
`authorize -> edge2/auth/login` и загрузку SSO assets.

Canary access log переведён на отдельный безопасный формат без query string,
referrer, cookies и authorization headers, чтобы OAuth callback codes не
попадали в новые записи. Error log оставляет только critical-события.

## Аудит инфраструктуры 2026-08-03

- Основные `rusaifin.ru` vhost, API, SSO discovery, HTTP/2, TLS 1.2/1.3,
  ECDSA и RSA fallback прошли внешние smoke-тесты.
- Все активные сертификаты rusaifin действительны. Автоматические staging
  renewal-тесты для ECDSA fintech/server прошли успешно.
- `mail.rusaifin.ru` был исправлен: HTTPS отдавал просроченный сертификат, а
  IMAP/POP3 — сертификат на другое имя. HTTPS, SMTP, IMAP и POP3 теперь
  используют единый сертификат `mail.rusaifin.ru`; Certbot переведён с
  ручного DNS-01 на автоматический HTTP-01 и установлен deploy hook.
- Для Dovecot подключены штатные 4096-bit DH parameters; TLS 1.2 DHE и TLS 1.3
  проходят проверку.
- Backup-файл `nginx.ssl.conf_nocache.bak.20260624`, случайно попадавший под
  wildcard include, перенесён из активного vhost в recoverable backup.
- Включён persistent Hestia firewall с `INPUT DROP`. Публично разрешены только
  заявленные Hestia-порты; MySQL `3306` и прямые Apache `8080/8443` закрыты,
  локальный путь Nginx к Apache сохранён.
- Ресурсы сервера, диски, conntrack, интерфейс, основные systemd-сервисы,
  контейнеры, Prometheus targets и ежедневные Hestia/shift backups в норме.
- Остались hardening-задачи, не связанные с инцидентом: конфликтующий legacy
  mail vhost и три legacy vhost с просроченными сертификатами (два уже не имеют
  DNS, один suspended). Их нельзя смешивать с исправлением пользовательского
  маршрута.

## Корневое исправление

Нужен второй публичный ingress в другой сети/ASN. Origin, приложения и БД
переносить не требуется. Подходящие варианты: российский CDN/L7-balancer либо
небольшой reverse-proxy узел у другого провайдера.

Ingress должен обслуживать согласованно:

- `fintech.rusaifin.ru` — HTML и статические Nuxt assets;
- `/api/*` и `/document/*` — проксирование на текущий backend;
- SSO callback/login-потоки;
- websocket `/app/*` с Upgrade;
- cookies, `Set-Cookie`, `Host`, `X-Forwarded-Proto` и реальный IP клиента.

Динамические, auth- и document-ответы нельзя кешировать. Кеш допустим только
для immutable `/_nuxt/*` и явно публичных статических файлов.

## Порядок переключения

1. Создать ingress в отличном от текущего ASN и подключить его к origin.
2. Закрыть origin от подмены Host и сохранить корректный client IP.
3. Проверить canary-host с Yota/iOS без VPN и с домашнего Wi-Fi.
4. Уменьшить DNS TTL, переключить сначала fintech, затем server и SSO.
5. Наблюдать HTTP/TLS errors и пользовательские beacons не менее суток.
6. Rollback: вернуть A-записи на текущий origin; приложения и БД не меняются.
