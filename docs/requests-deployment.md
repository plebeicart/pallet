# Заявки: эксплуатация и развёртывание

По умолчанию `REQUESTS_ENABLED=false`. До подтверждения юридической готовности
не менять этот флаг. Backend не читает тело отключённой заявки, возвращает 503,
а браузер только проверяет поля локально и сообщает, что заявка не отправлена.
Запрос конфигурации не содержит данных формы. Согласия и юридические документы
сохранены; включение флага само по себе не подтверждает их достаточность.

## Что подключено

Две существующие формы в `index.html`: `main` (имя, телефон, выбранная услуга,
задача) и `modal` (имя, телефон, выбранный товар/услуга/звонок).
Все кнопки `data-request` и шесть `data-service` используют прежний общий диалог.
Новых видимых форм нет; CSS, содержимое сайта, анимации и документы не переписаны.

`GET /api/health` — состояние процесса, без проверки SMTP.
`GET /api/requests/config` — выключенный режим либо разрешение отправки и
подписанный временный токен. Ответы API имеют `Cache-Control: no-store`.

`POST /api/requests`, `Content-Type: application/json`, точный разрешённый
заголовок `Origin`. Контракт:

```json
{
  "name": "Иван",
  "phone": "+7 (999) 117-88-28",
  "subject": "Поддон 1200×800",
  "message": "100 штук",
  "form": "main",
  "consent": "on",
  "website": "",
  "token": "токен из GET /api/requests/config",
  "request_id": "канонический UUID"
}
```

Обязательны `name` (2–80), `phone` (10–15 ASCII-цифр, до 24 символов,
необязательный начальный `+`, пробелы, скобки, дефисы), `form` (`main`/`modal`),
`consent` (только строка `on`), `token`, `request_id`. `subject` до 200 символов,
`message` до 2000; оба необязательны. `website` — пустая ловушка для ботов.
Неизвестные поля запрещены. Тело до 16 KiB, время чтения до 5 секунд.
Токен действует 2 часа и принимается спустя минимум 2 секунды после выдачи.
Время проверяет сервер. Поля не помещаются в URL или заголовки письма.

Ответ: `{"ok": true|false, "message": "понятное сообщение"}`.

| Код | Значение |
| --- | --- |
| 200 | SMTP принял письмо либо ранее подтверждён этот же запрос |
| 403 | Недопустимый/отсутствующий Origin или cross-site запрос |
| 408 / 413 / 415 | Тайм-аут чтения / большое тело / неверный Content-Type |
| 422 | Поля, согласие, токен или антиспам-проверка не прошли |
| 409 | Такой запрос уже выполняется либо UUID использован для иных данных |
| 429 | Превышен лимит; есть Retry-After |
| 502 | Отправка не подтверждена; внутренние сведения скрыты |
| 503 | Приём отключён или исчерпана одновременная ёмкость |

Caddy/Uvicorn могут вернуть свои ответы на уровне транспорта. Клиент не
показывает успех при HTTP-ошибке, невалидном JSON или `ok`, отличном от `true`.
Во время отправки поля и кнопка заблокированы. При ошибке данные сохранены,
в том числе после закрытия и повторного открытия модального окна.

## Безопасность и ограничения

- SMTP строго `smtp.yandex.ru:465`, SSL с проверкой сертификата, тайм-аут 10 секунд
  на блокирующую операцию. Отправитель `petor.zhu@yandex.ru`, получатель
  **`vip@xn--80akrarw.com`**. Оба SMTP envelope-адреса и заголовки заданы сервером.
  Пользователь не может выбрать адресата, From, Subject, Cc или Bcc.
- UTF-8 используется в MIME-теле и кодированных заголовках; Unicode-домен не
  передаётся SMTP. Включать SMTPUTF8 не требуется.
- 5 попыток за 10 минут на IP, 100 SMTP-попыток в час на весь процесс; ошибки валидации
  учитываются только в лимите источника. Не более 3 SMTP-отправок одновременно.
  Низкий общий лимит — осознанный предохранитель для коммерческого лендинга;
  он может временно заблокировать клиентов после спам-атаки.
- UUID и содержимое заявки дедуплицируются на 24 часа. В памяти остаются HMAC-хеши,
  срок действия и статус, без имён, телефонов, текста и исходных IP.
  Отправка повторного UUID с другими данными запрещена. Даже другой UUID с тем
  же содержимым не приводит к новому письму. Неоднозначная SMTP-ошибка также
  фиксируется: автоматической пересылки нет, посетителю предложено позвонить.
- **Ровно один worker**, без `--reload` в production. Лимиты, ключ токенов и
  защита от дублей сбрасываются при рестарте/аварии. Без постоянного хранилища
  нельзя гарантировать exactly-once между перезапусками. Не перезапускать сервис
  во время спорной доставки ради повторной отправки. База/файлы заявок не создаются.
- SMTP-успех означает принятие SMTP-сервером, не гарантирует попадание во входящие.
  Письма сохраняются у почтовых провайдеров и в корпоративном ящике; сроки хранения
  и доступ к ним нужно определить компании.
- Honeypot, задержка и Origin снижают простой спам, но скрипт может получить токен
  и подделать Origin. Это не полноценная защита от распределённой атаки.
- CORS не включён. IP берётся из ASGI client, не разбирается из пользовательских
  заголовков. systemd доверяет proxy headers только от `127.0.0.1`; Caddy
  перезаписывает X-Forwarded-For реальным адресом соединения.
  Фрагмент рассчитан на прямой доступ клиентов к Caddy. При CDN/балансировщике
  сначала отдельно настроить доверенные адреса этого прокси; не ставить `*`.
- Приложение пишет только фиксированные категории ошибок. Не включать SMTP debug,
  логирование тел/заголовков, APM с захватом запросов или debug-режим. Uvicorn
  access log выключен, запросы `/api/*` исключаются из access log Caddy.
  Доступ к системному journal и почте должен быть ограничен администраторами.
- Служебный код и секрет находятся вне web root. Фрагмент Caddy разрешает только
  публичные HTML, CSS, JS, assets; `.git`, backend, `.env`, тесты и документация
  не должны быть доступны по HTTP. Не размещать секреты даже внутри assets.

## Локальный запуск (без настоящих писем)

Python 3.11+; проверено на Python 3.12.3. На Ubuntu установить `python3-venv`.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
node --check js/main.js
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers --no-access-log
```

В другом терминале `python3 -m http.server 8080 --bind 127.0.0.1` и открыть
`http://127.0.0.1:8080`. Это статический preview: `/api/requests/config` на нём
получит 404, интерфейс безопасно останется демонстрационным. Для локальной
same-origin интеграции можно использовать Caddy-фрагмент с локальным HTTP
адресом, изменив root на каталог проекта. Не включать реальный SMTP для QA.
`.env.example` — шаблон, приложение не читает `.env` автоматически: в production
окружение передаёт systemd. Создавать `.env` для выключенного запуска не требуется.

Браузерные регрессии используют mock API и встроенный временный localhost-сервер:

```bash
# При уже установленном Playwright указать путь к его модулю.
PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright node tests/browser.cjs
# При необходимости: CHROMIUM_PATH=/absolute/path/to/chromium
```

Браузерные инструменты не нужны рабочему сайту. Python-тесты автоматически
подменяют SMTP_SSL во всех сценариях и не отправляют реальные письма.

## Подготовка VPS: выполнять вручную

Ни одна команда ниже не выполнена на VPS. Нужен административный SSH-сеанс,
Ubuntu с Python 3.11+, действующий Caddy и доступ к GitHub.
Неизвестны URL репозитория, утверждённый commit и фактический Caddyfile; они
запрашиваются/проверяются вручную, а не подменяются выдуманными значениями.
В примерах путь конфигурации — стандартный `/etc/caddy/Caddyfile`; сначала
проверить `systemctl cat caddy` и использовать реальный путь, если он иной.

```bash
set -euo pipefail
sudo apt update
sudo apt install python3 python3-venv git rsync
python3 --version
caddy version
systemctl cat caddy
sudo useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin pallet-api
sudo install -d -m 0755 /opt/pallet-api/releases
sudo install -d -m 0700 /etc/pallet-api /var/backups/pallet
read -r -p 'URL существующего GitHub-репозитория (без токена): ' REPO_URL
sudo install -d -o "$USER" -g "$(id -gn)" -m 0750 /opt/pallet-src
git clone "$REPO_URL" /opt/pallet-src
```

Если служебный пользователь/checkout уже существуют, не создавать их повторно.
Для приватного GitHub использовать существующую SSH-аутентификацию или отдельный
read-only deploy key. Не включать токен в URL, историю shell или Caddyfile.

## Подготовка и проверка релиза

Этот блок применим при первом развёртывании и обновлениях. Сначала изменения
должны быть вручную закоммичены и опубликованы вами в GitHub.

```bash
git -C /opt/pallet-src fetch --prune origin
read -r -p 'Утверждённый полный commit SHA из GitHub: ' APPROVED_COMMIT
COMMIT=$(git -C /opt/pallet-src rev-parse --verify "${APPROVED_COMMIT}^{commit}")
test "$COMMIT" = "$APPROVED_COMMIT"
RELEASE_ID="$(date -u +%Y%m%dT%H%M%SZ)-${COMMIT:0:12}"
RELEASE_DIR="/opt/pallet-api/releases/$RELEASE_ID"
sudo install -d -o "$USER" -g "$(id -gn)" -m 0750 "$RELEASE_DIR"
git -C /opt/pallet-src archive "$COMMIT" | tar -x -C "$RELEASE_DIR"
QA_ENV_DIR="/tmp/pallet-qa-$RELEASE_ID"
python3 -m venv "$QA_ENV_DIR"
"$QA_ENV_DIR/bin/python" -m pip install -r "$RELEASE_DIR/requirements-dev.txt"
cd "$RELEASE_DIR"
env REQUESTS_ENABLED=false "$QA_ENV_DIR/bin/python" -m pytest -q
python3 -m venv "$RELEASE_DIR/.venv"
"$RELEASE_DIR/.venv/bin/python" -m pip install -r "$RELEASE_DIR/requirements.txt"
node --check js/main.js
"$RELEASE_DIR/.venv/bin/python" -m pip check
sudo chown -R root:pallet-api "$RELEASE_DIR"
sudo chmod -R u=rwX,g=rX,o= "$RELEASE_DIR"
```

Node нужен здесь только для дополнительной проверки JS (если установлен),
не для сервиса. При отсутствии Node выполнить `node --check` заранее локально.
Глобальный шаблон тайм-аутов: `deploy/Caddy-global.fragment`; объединить с
существующим глобальным блоком, не создавать второй.
Все команды выполнять с контролем exit code; при ошибке **не продолжать**.
Для bash-сессии развёртывания рекомендуется заранее `set -euo pipefail`.
Не перемещать готовую `.venv` между каталогами: пути в ней абсолютные.
Старые релизы сохранять для отката. Не запускать pip от root.

## Секрет и выключенный режим

```bash
sudo install -m 0600 -o root -g root "$RELEASE_DIR/.env.example" /etc/pallet-api/pallet-api.env
sudoedit /etc/pallet-api/pallet-api.env
```

Команда `install` предназначена только для первого запуска! На обновлении
**не перезаписывать существующий env**. В редакторе оставить
`REQUESTS_ENABLED=false`, задать `SMTP_PASSWORD` паролем приложения и
`ALLOWED_ORIGINS` фактическими HTTPS-origin сайта из Caddy, например список
ASCII/Punycode адресов без завершающего `/`, без `*`.
Домен получателя почты не доказывает, какие домены обслуживает Caddy.
Не добавлять неиспользуемые www-домены и не угадывать их.

Использовать синтаксис `EnvironmentFile` systemd: `KEY=value`, при необходимости
заключить значение в кавычки. Не писать `export`, shell-подстановки или пароль
в командной строке. Не выполнять `cat`/`printenv` для секрета, не публиковать
скриншоты файла. systemd прочитает root-only файл до снижения прав пользователя.
При компрометации отозвать пароль приложения Яндекса и создать новый.

## Backup, systemd и Caddy

Перед переключением записать старый релиз и сохранить оба изменяемых файла сайта:

```bash
sudo install -m 0700 "$RELEASE_DIR/deploy/rollback.py" /opt/pallet-rollback.py
sudo tar -C /var/www/pallet -czf "/var/backups/pallet/web-$RELEASE_ID.tgz" index.html js/main.js
sudo cp -a /etc/caddy/Caddyfile "/var/backups/pallet/Caddyfile-$RELEASE_ID"
if sudo test -L /opt/pallet-api/current; then
    sudo readlink -f /opt/pallet-api/current | sudo tee "/var/backups/pallet/previous-$RELEASE_ID.txt"
else
    printf 'none\n' | sudo tee "/var/backups/pallet/previous-$RELEASE_ID.txt"
fi
if test -f /etc/systemd/system/pallet-api.service; then
    sudo cp -a /etc/systemd/system/pallet-api.service "/var/backups/pallet/service-$RELEASE_ID"
fi
sudo ln -s "$RELEASE_DIR" /opt/pallet-api/current.next
sudo mv -Tf /opt/pallet-api/current.next /opt/pallet-api/current
sudo install -m 0644 "$RELEASE_DIR/deploy/pallet-api.service" /etc/systemd/system/pallet-api.service
sudo systemd-analyze verify /etc/systemd/system/pallet-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now pallet-api
sudo systemctl restart pallet-api
curl --fail --silent --show-error http://127.0.0.1:8000/api/health
curl --fail --silent --show-error http://127.0.0.1:8000/api/requests/config
sudo ss -ltnp 'sport = :8000'
```

Проверить, что показан **только `127.0.0.1:8000`**, конфигурация возвращает
`{"enabled":false}`. Порт 8000 не открывать в security group Яндекс Cloud/UFW.
Сервис не должен иметь прав записи в web root или каталог релиза.

Открыть `sudoedit /etc/caddy/Caddyfile`. Внутрь **существующего блока домена**
внести `deploy/Caddyfile.fragment`, сохранив имя сайта, HTTPS, сертификаты,
редиректы и прочие нужные маршруты. Прежний общий `root`/`file_server` заменить
статическим `handle @public` из фрагмента, чтобы не раздавать backend и `.git`.
Не использовать `handle_path /api/*`: он удаляет префикс `/api`.
Для Caddy до 2.8 директива `log_skip` называется `skip_log`; проверить версию.
Если Caddy получает трафик через другой прокси, сначала настроить доверие к нему.

```bash
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
# Обновляем только реально изменённые публичные файлы, без удаления остальных.
sudo install -m 0644 "$RELEASE_DIR/index.html" /var/www/pallet/index.html.next
sudo install -m 0644 "$RELEASE_DIR/js/main.js" /var/www/pallet/js/main.js.next
sudo mv -f /var/www/pallet/js/main.js.next /var/www/pallet/js/main.js
sudo mv -f /var/www/pallet/index.html.next /var/www/pallet/index.html
read -r -p 'Фактический HTTPS origin сайта, ASCII/Punycode, без / в конце: ' SITE_ORIGIN
curl --fail --silent --show-error "$SITE_ORIGIN/api/health"
curl --fail --silent --show-error "$SITE_ORIGIN/api/requests/config"
curl -sS -o /dev/null -w '%{http_code}\n' "$SITE_ORIGIN/.env"
curl -sS -o /dev/null -w '%{http_code}\n' "$SITE_ORIGIN/.git/config"
curl -sS -o /dev/null -w '%{http_code}\n' "$SITE_ORIGIN/backend/app.py"
curl -sS -o /dev/null -w '%{http_code}\n' -H 'Content-Type: application/json' -d '{}' "$SITE_ORIGIN/api/requests"
```

Служебные пути должны вернуть 404; выключенный POST — 503. Главная, картинки,
privacy и consent должны открываться, формы — сообщать о демонстрационном режиме.
Если перед сайтом есть CDN, не кэшировать `/api/*`; после обновления очистить
кэш `index.html` и `js/main.js`. Проверить браузером без старого кэша.

## Включение только после юридического подтверждения

Вручную подтвердить готовность компании, актуальность оператора/контактов,
политики и отдельного согласия, организационные процедуры обработки данных,
доступ и сроки хранения в почте. Это организационное решение, не результат теста.

```bash
sudoedit /etc/pallet-api/pallet-api.env
# В редакторе: REQUESTS_ENABLED=true; точные ALLOWED_ORIGINS; SMTP_PASSWORD.
sudo systemctl restart pallet-api
curl --fail --silent --show-error http://127.0.0.1:8000/api/requests/config
```

Обновить страницу. Текст кнопки станет «Отправить заявку», demo-уведомления
скроются. После подтверждения готовности вручную отправить одну согласованную
контрольную заявку и проверить корпоративный ящик (включая спам).
До этого тесты использовать только с mock SMTP. При проблеме немедленно вернуть
`REQUESTS_ENABLED=false` и перезапустить сервис. Сам frontend-флаг не защищает API:
ограничение обязательно проверяет backend на каждом POST.

## Наблюдение и обновления

```bash
sudo systemctl status pallet-api --no-pager
sudo journalctl -u pallet-api -n 100 --no-pager
sudo journalctl -u pallet-api -f
sudo journalctl -u caddy -n 100 --no-pager
```

Категории ошибок: `smtp_rejected_before_acceptance` — явный отказ, проверить
настройки SMTP и доступность сервера;
`smtp_delivery_failed` — сеть/TLS/отказ SMTP; `delivery_internal_error` и
`request_internal_error` — ошибка приложения. В логи намеренно не включены
SMTP-ответы, поля заявки и traceback. Не включать debug ради диагностики с
реальными данными; воспроизводить проблему локально с mock SMTP.

Для обновления повторить блоки подготовки релиза, backup и переключения.
Текущий `/etc/pallet-api/pallet-api.env` сохранить. Перед обслуживанием безопаснее
временно отключить приём и предупредить ответственных; перезапуск сбросит
временную защиту от дублей. Не делать `git pull` прямо поверх работающего backend:
каждый релиз имеет свою `.venv`, текущий путь переключается symlink.

## Откат

При первом развёртывании старого API нет: отключить сервис, восстановить оба
публичных файла и прежний Caddyfile. При обновлении восстановить ещё symlink и unit.
Сначала выключить приём; при rollback автоматически не включать реальные заявки.

```bash
sudoedit /etc/pallet-api/pallet-api.env
# REQUESTS_ENABLED=false
read -r -p 'RELEASE_ID неудачного развёртывания из имени backup: ' FAILED_RELEASE
sudo python3 /opt/pallet-rollback.py "$FAILED_RELEASE"
sudo systemctl status pallet-api --no-pager
```

Проверить главную и формы, затем при наличии старого API `/api/health`.
Неудачный релиз и backup сохранить для разбора. Не использовать `git reset --hard`,
не удалять каталог работающего релиза и не восстанавливать секрет из Git.

Справочные первоисточники: [Python SMTP_SSL](https://docs.python.org/3/library/smtplib.html),
[FastAPI за reverse proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/),
[Caddy reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy),
[Caddy log_skip](https://caddyserver.com/docs/caddyfile/directives/log_skip).


## Уточнения после аудита Astra

Откат выполняется `deploy/rollback.py` целиком через sudo: root читает backup 0700.
Отсутствие manifest/backup или недоступность предыдущего релиза — ошибка, а не
признак первого запуска. Первый запуск явно записывает `none`. Скрипт сначала
проверяет все файлы и Caddy-конфигурацию, затем останавливает сервис и восстанавливает
symlink, unit и публичные файлы. Старые релизы не удаляются. При ошибке после
остановки сервис остаётся остановленным: исправить причину и повторить откат.
Перед переключением нового релиза сохранить root-owned копию rollback.py вне
переключаемого каталога (например `/opt/pallet-rollback.py`) и использовать её,
если GitHub checkout недоступен. Команда: `sudo install -m 0700
"$RELEASE_DIR/deploy/rollback.py" /opt/pallet-rollback.py` (одной строкой).

Рекомендуется тестировать релиз в отдельном QA-окружении с requirements-dev.txt,
а рабочую `.venv` наполнять requirements.txt. Тестовые пакеты сервису не нужны.

Лимит попыток: 5/10 минут для IPv4 либо IPv6 /64, включая некорректные запросы.
Выдача конфигурации: 30/10 минут на тот же источник. Подписанный токен связан
с источником и одной заявкой; для новой заявки после успеха JS получает новый.
Смена сети или рестарт требует обновления страницы. Общий бюджет 100/час
расходуется только на SMTP-попытки, после проверок и дедупликации. Retry-After
для общего лимита вычисляется по времени освобождения. Redis не добавлен:
один worker достаточен для этого сайта, состояние теряется при рестарте.
Распределённые корректные заявки всё ещё могут исчерпать аварийный бюджет.

Явный отказ подключения/авторизации либо отрицательный SMTP-ответ возвращает
503 с Retry-After: 30; после паузы та же заявка может быть повторена. Неопределённый
обрыв при send_message возвращает 502 и блокирует автоматическую пересылку на
сутки. Успех означает принятие SMTP-сервером, а не гарантированное попадание
во входящие. В логах явный отказ отмечается smtp_rejected_before_acceptance.

Без JavaScript обе кнопки disabled; дополнительный inline обработчик отменяет
native submit, method явно post. JS устанавливает обработчики до разблокировки.
Имена и телефоны не попадают в URL даже при недоступном js/main.js.

Для Caddy read_header/read_body тайм-ауты задаются в существующем глобальном блоке
servers с учётом установленной версии (например read_header 10s, read_body 10s).
Не путать response_header_timeout upstream с тайм-аутом загрузки клиента.
Приложение дополнительно ограничивает чтение JSON пятью секундами.
Не заменять /api handle на handle_path; backend должен видеть /api/requests.
