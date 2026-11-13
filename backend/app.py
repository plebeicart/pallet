"""Single-process, memory-only request delivery. No request payloads in logs."""
import asyncio
import hashlib
import hmac
import json
import ipaddress
import math
import logging
import os
import re
import secrets
import smtplib
import ssl
import time
from collections import deque
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.responses import JSONResponse

SENDER = 'petor.zhu@yandex.ru'
RECIPIENT = 'vip@xn--80akrarw.com'
MAX_BODY = 16384
DEDUPE_TTL = 86400
logger = logging.getLogger('pallet.delivery')


@dataclass(frozen=True)
class Settings:
    enabled: bool = False
    origins: tuple[str, ...] = ()
    password: str = field(default='', repr=False)
    ip_limit: int = 5
    global_limit: int = 100
    min_age: float = 2

    @classmethod
    def from_env(cls):
        flag = os.getenv('REQUESTS_ENABLED', 'false')
        if flag not in ('true', 'false'):
            raise RuntimeError('REQUESTS_ENABLED must be true or false')
        origins = tuple(s.strip() for s in os.getenv('ALLOWED_ORIGINS', '').split(',') if s.strip())
        password = os.getenv('SMTP_PASSWORD', '')
        if flag == 'true' and (not origins or not password):
            raise RuntimeError('Enabled delivery requires ALLOWED_ORIGINS and SMTP_PASSWORD')
        if any(not re.fullmatch(r'https?://[a-zA-Z0-9.:-]+', o) for o in origins):
            raise RuntimeError('Origins must be exact ASCII origins without paths')
        return cls(enabled=flag == 'true', origins=origins, password=password)


class Lead(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=10, max_length=24)
    subject: str = Field(default='', max_length=200)
    message: str = Field(default='', max_length=2000)
    form: Literal['main', 'modal']
    consent: Literal['on']
    website: str = Field(default='', max_length=200)
    token: str = Field(max_length=200)
    request_id: str = Field(max_length=36)

    @field_validator('name', 'subject', 'phone', 'message', mode='before')
    @classmethod
    def safe_text(cls, value, info):
        if isinstance(value, str):
            # Check before stripping: even leading CR/LF must not be accepted.
            allowed = '\n\r\t' if info.field_name == 'message' else ''
            if any((ord(c) < 32 and c not in allowed) or ord(c) == 127 for c in value):
                raise ValueError('Control characters are forbidden')
        return value

    @field_validator('phone')
    @classmethod
    def phone_format(cls, value):
        if not re.fullmatch(r'\+?[0-9 ()-]+', value) or not 10 <= len(re.sub(r'[^0-9]', '', value)) <= 15:
            raise ValueError('Invalid phone')
        return value

    @field_validator('request_id')
    @classmethod
    def uuid_format(cls, value):
        if str(UUID(value)) != value:
            raise ValueError('Invalid request ID')
        return value


def make_message(lead: Lead) -> EmailMessage:
    message = EmailMessage()
    # All headers and envelope addresses are controlled by the application.
    message['From'] = SENDER
    message['To'] = RECIPIENT
    message['Subject'] = 'Заявка с сайта Паллетной Компании'
    message['Date'] = format_datetime(datetime.now(timezone.utc))
    message['Message-ID'] = make_msgid(domain='yandex.ru')
    source = {'main': 'Основная форма — Оставить заявку', 'modal': 'Модальная форма — товар / услуга / звонок'}[lead.form]
    message.set_content(f'Форма: {source}\nИмя: {lead.name}\nТелефон: {lead.phone}\n'
                        f'Товар или услуга: {lead.subject or "Не указаны"}\n'
                        f'Задача: {lead.message or "Не указана"}\n'
                        'Согласие на обработку персональных данных: дано\n')
    return message


class DeliveryRejected(Exception):
    """The server has not accepted this message; a controlled retry is safe."""


def send_mail(lead: Lead, settings: Settings):
    # Build locally before connecting. Connection/login failures precede DATA.
    message = make_message(lead)
    try:
        smtp = smtplib.SMTP_SSL('smtp.yandex.ru', 465, timeout=10, context=ssl.create_default_context())
    except (smtplib.SMTPException, OSError) as error:
        raise DeliveryRejected() from error
    try:
        try:
            smtp.login(SENDER, settings.password)
        except (smtplib.SMTPException, OSError) as error:
            raise DeliveryRejected() from error
        try:
            refused = smtp.send_message(message, from_addr=SENDER, to_addrs=[RECIPIENT])
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
        except (smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused) as error:
            # Explicit negative SMTP reply: the transaction was rejected.
            raise DeliveryRejected() from error
        # Disconnect/timeout during send_message is ambiguous: do not retry.
    finally:
        try:
            smtp.close()
        except OSError:
            pass  # Closing a socket cannot revoke an already accepted DATA.


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    secret = secrets.token_bytes(32)
    attempts = {}
    global_attempts = deque()
    config_attempts = {}
    used_tokens = {}
    results = {}  # HMAC keys and status only; never names, phones or raw IPs.
    fingerprints = {}
    active = 0

    def digest(value):
        return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()

    def response(code, text, **headers):
        return JSONResponse({'ok': code == 200, 'message': text}, status_code=code,
                            headers={'Cache-Control': 'no-store', **headers})

    @app.middleware('http')
    async def private_errors(request, call_next):
        try:
            result = await call_next(request)
        except Exception:
            # No exception text, traceback, request body, or headers.
            logger.error('request_internal_error')
            result = response(500, 'Не удалось обработать заявку. Позвоните нам.')
        result.headers['Cache-Control'] = 'no-store'
        result.headers['X-Content-Type-Options'] = 'nosniff'
        return result

    def source(request):
        host = request.client.host if request.client else 'unknown'
        try:
            address = ipaddress.ip_address(host)
            host = str(ipaddress.ip_network(f'{address}/64', strict=False)) if address.version == 6 else str(address)
        except ValueError:
            pass
        return digest(host)

    def limit(mapping, key, maximum, now):
        for old in list(mapping):
            if mapping[old][-1] <= now - 600:
                del mapping[old]
        bucket = mapping.get(key, deque())
        while bucket and bucket[0] <= now - 600:
            bucket.popleft()
        if len(bucket) >= maximum:
            return max(1, math.ceil(bucket[0] + 600 - now))
        if key not in mapping and len(mapping) >= 10000:
            return 600
        mapping[key] = bucket
        bucket.append(now)
        return 0

    @app.get('/api/health')
    async def health():
        return {'ok': True}

    @app.get('/api/requests/config')
    async def config(request: Request):
        if not settings.enabled:
            return {'enabled': False}
        ip = source(request)
        retry = limit(config_attempts, ip, 30, time.monotonic())
        if retry:
            return response(429, 'Попробуйте позже.', **{'Retry-After': str(retry)})
        ticket = f'{int(time.time())}.{secrets.token_hex(16)}'
        return {'enabled': True, 'token': f'{ticket}.{digest(ticket + chr(124) + ip)}'}

    @app.post('/api/requests')
    async def submit(request: Request):
        nonlocal active
        if not settings.enabled:
            return response(503, 'Приём заявок пока отключён. Позвоните нам.')
        if request.headers.get('origin') not in settings.origins or request.headers.get('sec-fetch-site') == 'cross-site':
            return response(403, 'Отправка с этого сайта запрещена.')
        # Uvicorn proxy trust is configured separately. Never parse IP headers here.
        now = time.monotonic()
        ip = source(request)
        retry = limit(attempts, ip, settings.ip_limit, now)
        if retry:
            return response(429, 'Слишком много попыток. Попробуйте позже.', **{'Retry-After': str(retry)})
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            return response(415, 'Ожидается JSON.')
        try:
            body = bytearray()
            async with asyncio.timeout(5):
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > MAX_BODY:
                        return response(413, 'Заявка слишком большая.')
            lead = Lead.model_validate_json(bytes(body))
        except TimeoutError:
            return response(408, 'Время передачи истекло.')
        except (ValidationError, ValueError):
            return response(422, 'Проверьте имя, телефон, длину полей и согласие.')
        try:
            stamp, nonce, signature = lead.token.split('.')
            age = time.time() - int(stamp)
            valid_token = hmac.compare_digest(signature, digest(f'{stamp}.{nonce}|' + ip)) and settings.min_age <= age <= 7200
        except (ValueError, TypeError):
            valid_token = False
        if lead.website or not valid_token:
            return response(422, 'Обновите страницу и повторите заполнение формы.')
        for mapping in (results, fingerprints, used_tokens):
            for key in list(mapping):
                if mapping[key][0] <= now:
                    del mapping[key]
        fingerprint = digest(json.dumps(lead.model_dump(exclude={'token', 'request_id', 'website'}), sort_keys=True, ensure_ascii=False))
        key = digest(lead.request_id)
        if key in results:
            _, saved_fingerprint, code = results[key]
            if saved_fingerprint != fingerprint:
                return response(409, 'Для изменённой заявки нужен новый идентификатор.')
            return cached_result(code)
        if fingerprint in fingerprints:
            return cached_result(fingerprints[fingerprint][1])
        token_key = digest(lead.token)
        if token_key in used_tokens and used_tokens[token_key][1] != fingerprint:
            return response(429, 'Для новой заявки обновите страницу.', **{'Retry-After': '600'})
        while global_attempts and global_attempts[0] <= now - 3600:
            global_attempts.popleft()
        if len(global_attempts) >= settings.global_limit:
            retry = max(1, math.ceil(global_attempts[0] + 3600 - now))
            return response(429, 'Слишком много отправок. Попробуйте позже.', **{'Retry-After': str(retry)})
        if active >= 3 or len(results) >= 10000 or len(used_tokens) >= 10000:
            return response(503, 'Сервис занят. Попробуйте позже.')
        # No await between check and reservation: atomic in one event loop/worker.
        results[key] = (now + DEDUPE_TTL, fingerprint, 409)
        fingerprints[fingerprint] = (now + DEDUPE_TTL, 409)
        used_tokens[token_key] = (now + 7200, fingerprint)
        global_attempts.append(now)
        active += 1
        code = 502
        try:
            await asyncio.to_thread(send_mail, lead, settings)
            code = 200
        except DeliveryRejected:
            code = 503
            logger.error('smtp_rejected_before_acceptance')
        except (smtplib.SMTPException, OSError):
            logger.error('smtp_delivery_failed')
        except Exception:
            logger.error('delivery_internal_error')
        finally:
            active -= 1
            expires = time.monotonic() + (30 if code == 503 else DEDUPE_TTL)
            results[key] = (expires, fingerprint, code)
            fingerprints[fingerprint] = (expires, code)
        return cached_result(code)

    def cached_result(code):
        messages = {503: 'Письмо не принято. Повторите заявку через 30 секунд или позвоните нам.', 200: 'Заявка отправлена. Спасибо! Мы свяжемся с вами в рабочее время.',
                    409: 'Эта заявка уже отправляется. Подождите и проверьте результат.',
                    502: 'Не удалось подтвердить отправку. Пожалуйста, позвоните нам, чтобы избежать дублирования заявки.'}
        return response(code, messages[code], **({'Retry-After': '30'} if code == 503 else {}))

    return app


app = create_app()
