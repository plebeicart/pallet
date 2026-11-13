import asyncio
import smtplib
import ssl
import threading
from dataclasses import replace
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import Lead, RECIPIENT, SENDER, Settings, create_app, make_message

ORIGIN = 'https://example.test'


@pytest.fixture(autouse=True)
def smtp(monkeypatch):
    """No test can contact a real SMTP server."""
    instance = MagicMock()
    instance.send_message.return_value = {}
    factory = MagicMock(return_value=instance)
    monkeypatch.setattr('backend.app.smtplib.SMTP_SSL', factory)
    monkeypatch.setattr('socket.create_connection', lambda *a, **kw: pytest.fail('Real network forbidden in SMTP tests'))
    return factory, instance


@pytest.fixture
def settings():
    return Settings(enabled=True, origins=(ORIGIN,), password='test-only-secret', min_age=0)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), headers={'Origin': ORIGIN}) as client:
        yield client


def payload(client, **changes):
    data = dict(name='Иван', phone='+7 (999) 117-88-28', subject='Поддон 1200×800',
                message='100 штук\nДоставка', form='main', consent='on', website='',
                token=client.get('/api/requests/config').json()['token'], request_id=str(uuid4()))
    data.update(changes)
    return data


def test_valid_request_and_tls_envelope(client, smtp):
    data = payload(client)
    result = client.post('/api/requests', json=data)
    assert result.status_code == 200 and result.json()['ok'] is True
    args, kwargs = smtp[0].call_args
    assert args == ('smtp.yandex.ru', 465)
    assert kwargs['timeout'] == 10
    assert kwargs['context'].verify_mode == ssl.CERT_REQUIRED
    assert kwargs['context'].check_hostname
    smtp[1].login.assert_called_once_with(SENDER, 'test-only-secret')
    assert smtp[1].send_message.call_args.kwargs == {'from_addr': SENDER, 'to_addrs': [RECIPIENT]}
    smtp[1].close.assert_called_once()
    assert 'access-control-allow-origin' not in result.headers
    assert result.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('field', ['name', 'phone', 'consent', 'form', 'request_id', 'token'])
def test_required(client, smtp, field):
    data = payload(client)
    del data[field]
    assert client.post('/api/requests', json=data).status_code == 422
    smtp[0].assert_not_called()


@pytest.mark.parametrize('phone', ['123', 'call me', '+7 abc 9991178828', '１２３４５６７８９０', '++79991178828', '1' * 16])
def test_invalid_phone(client, smtp, phone):
    assert client.post('/api/requests', json=payload(client, phone=phone)).status_code == 422
    smtp[0].assert_not_called()


@pytest.mark.parametrize(('field', 'value'), [('name', 'А' * 81), ('phone', '1' * 25),
    ('subject', 'А' * 201), ('message', 'А' * 2001), ('name', ' '), ('name', 123),
    ('consent', False), ('consent', 'off'), ('form', 'arbitrary'), ('request_id', 'bad'),
    ('name', 'Иван\r\nBcc: test@example.com'), ('subject', '\r\nInjected'), ('message', '\x00')])
def test_invalid_fields(client, smtp, field, value):
    result = client.post('/api/requests', json=payload(client, **{field: value}))
    assert result.status_code == 422
    assert 'input' not in result.text
    smtp[0].assert_not_called()


@pytest.mark.parametrize('error', [smtplib.SMTPAuthenticationError(535, b'test-only-secret'),
    smtplib.SMTPServerDisconnected('private data'), smtplib.SMTPDataError(554, b'private data'),
    TimeoutError('private data'), OSError('private data'), RuntimeError('private data')])
def test_smtp_errors_private_and_no_retry(client, smtp, caplog, error):
    smtp[1].send_message.side_effect = error
    data = payload(client)
    for _ in range(2):
        result = client.post('/api/requests', json=data)
        expected = 503 if isinstance(error, smtplib.SMTPResponseException) else 502
        assert result.status_code == expected and result.json()['ok'] is False
        assert 'private data' not in result.text and 'test-only-secret' not in result.text
    smtp[1].send_message.assert_called_once()
    assert all(s not in caplog.text for s in ['private data', 'test-only-secret', data['name'], data['phone']])


def test_authentication_failure(client, smtp):
    smtp[1].login.side_effect = smtplib.SMTPAuthenticationError(535, b'secret')
    assert client.post('/api/requests', json=payload(client)).status_code == 503
    smtp[1].send_message.assert_not_called()
    smtp[1].close.assert_called_once()


def test_connection_failure(client, smtp):
    smtp[0].side_effect = OSError('private')
    assert client.post('/api/requests', json=payload(client)).status_code == 503


def test_refused_recipient(client, smtp):
    smtp[1].send_message.return_value = {RECIPIENT: (550, b'rejected')}
    assert client.post('/api/requests', json=payload(client)).status_code == 503


def test_ip_rate_limit_ignores_forged_headers(settings, smtp):
    with TestClient(create_app(replace(settings, ip_limit=2)), headers={'Origin': ORIGIN}) as client:
        for i in range(2):
            assert client.post('/api/requests', json=payload(client), headers={'X-Forwarded-For': f'192.0.2.{i}'}).status_code == 200
        result = client.post('/api/requests', json=payload(client), headers={'X-Forwarded-For': '203.0.113.1'})
        assert result.status_code == 429 and int(result.headers['retry-after']) > 0
    smtp[1].send_message.assert_called_once()  # Identical content deduplicated as well.


def test_global_rate_limit(settings):
    with TestClient(create_app(replace(settings, global_limit=1)), headers={'Origin': ORIGIN}) as client:
        assert client.post('/api/requests', json=payload(client)).status_code == 200
        assert client.post('/api/requests', json=payload(client, subject='Другая заявка')).status_code == 429


def test_disabled_default(smtp, monkeypatch):
    monkeypatch.delenv('REQUESTS_ENABLED', raising=False)
    with TestClient(create_app()) as client:
        assert client.get('/api/requests/config').json() == {'enabled': False}
        # Gate runs before reading/parsing even a malformed body.
        assert client.post('/api/requests', content=b'private malformed').status_code == 503
        assert client.get('/api/health').json() == {'ok': True}
    smtp[0].assert_not_called()


def test_message_content(client):
    lead = Lead(**payload(client))
    msg = make_message(lead)
    assert msg['From'] == SENDER and msg['To'] == RECIPIENT
    assert msg['Bcc'] is None and msg['Cc'] is None and msg['Reply-To'] is None
    for text in ['Иван', '+7 (999) 117-88-28', 'Поддон 1200×800', '100 штук\nДоставка', 'Основная форма']:
        assert text in msg.get_content()
    assert 'SMTPUTF8' not in msg.as_string()
    assert 'token' not in msg.get_content() and lead.request_id not in msg.get_content()
    modal = make_message(Lead(**payload(client, form='modal', message='', subject='')))
    assert 'Модальная форма' in modal.get_content() and 'Не указаны' in modal.get_content()


@pytest.mark.parametrize('origin', [None, 'null', 'https://evil.test', ORIGIN + '.evil.test'])
def test_origin_restriction(settings, smtp, origin):
    with TestClient(create_app(settings)) as client:
        headers = {'Origin': origin} if origin else {}
        assert client.post('/api/requests', json=payload(client), headers=headers).status_code == 403
    smtp[0].assert_not_called()


def test_cross_site_and_cors(client, smtp):
    assert client.post('/api/requests', json=payload(client), headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert client.options('/api/requests', headers={'Origin': 'https://evil.test', 'Access-Control-Request-Method': 'POST'}).status_code == 405
    smtp[0].assert_not_called()


@pytest.mark.parametrize('changes', [{'website': 'https://spam.test'}, {'token': 'forged'}, {'token': '1.a.й'}])
def test_spam_checks(client, smtp, changes):
    assert client.post('/api/requests', json=payload(client, **changes)).status_code == 422
    smtp[0].assert_not_called()


def test_token_too_fast_and_expired(settings, smtp, monkeypatch):
    with TestClient(create_app(replace(settings, min_age=2)), headers={'Origin': ORIGIN}) as client:
        data = payload(client)
        assert client.post('/api/requests', json=data).status_code == 422
        import time
        now = time.time()
        monkeypatch.setattr('backend.app.time.time', lambda: now + 7201)
        assert client.post('/api/requests', json=data).status_code == 422
    smtp[0].assert_not_called()


def test_duplicate_and_conflicting_id(client, smtp):
    data = payload(client)
    assert client.post('/api/requests', json=data).status_code == 200
    assert client.post('/api/requests', json=data).status_code == 200
    assert client.post('/api/requests', json={**data, 'request_id': str(uuid4())}).status_code == 200
    assert client.post('/api/requests', json={**data, 'name': 'Пётр'}).status_code == 409
    smtp[1].send_message.assert_called_once()


def test_concurrent_duplicate(settings, smtp):
    started = threading.Event()
    release = threading.Event()

    def blocked_send(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return {}

    smtp[1].send_message.side_effect = blocked_send

    async def run():
        transport = httpx.ASGITransport(app=create_app(settings))
        async with httpx.AsyncClient(transport=transport, base_url=ORIGIN, headers={'Origin': ORIGIN}) as client:
            data = dict(name='Иван', phone='79991178828', form='modal', consent='on', request_id=str(uuid4()),
                        token=(await client.get('/api/requests/config')).json()['token'])
            first = asyncio.create_task(client.post('/api/requests', json=data))
            try:
                assert await asyncio.to_thread(started.wait, 3)
                assert (await client.post('/api/requests', json=data)).status_code == 409
            finally:
                release.set()
            assert (await first).status_code == 200

    asyncio.run(run())
    smtp[1].send_message.assert_called_once()


def test_body_limits_and_unknown_fields(client, smtp):
    assert client.post('/api/requests', content='x' * 16385, headers={'Content-Type': 'application/json'}).status_code == 413
    assert client.post('/api/requests', content='bad', headers={'Content-Type': 'application/json'}).status_code == 422
    assert client.post('/api/requests', data={'name': 'test'}).status_code == 415
    assert client.post('/api/requests', json=payload(client, to='evil@example.com')).status_code == 422
    smtp[0].assert_not_called()


def test_environment_fail_closed(monkeypatch):
    monkeypatch.setenv('REQUESTS_ENABLED', 'yes')
    with pytest.raises(RuntimeError):
        Settings.from_env()
    monkeypatch.setenv('REQUESTS_ENABLED', 'true')
    monkeypatch.delenv('SMTP_PASSWORD', raising=False)
    monkeypatch.delenv('ALLOWED_ORIGINS', raising=False)
    with pytest.raises(RuntimeError):
        Settings.from_env()
    monkeypatch.setenv('SMTP_PASSWORD', 'test-only-secret')
    monkeypatch.setenv('ALLOWED_ORIGINS', '*')
    with pytest.raises(RuntimeError):
        Settings.from_env()
    monkeypatch.setenv('ALLOWED_ORIGINS', ORIGIN)
    assert Settings.from_env().enabled
    assert 'test-only-secret' not in repr(Settings.from_env())


@pytest.mark.parametrize('failure', ['connect', 'login', 'data_rejection'])
def test_definite_failure_recovers_after_cooldown(client, smtp, monkeypatch, failure):
    import time
    before = time.monotonic()
    if failure == 'connect':
        smtp[0].side_effect = TimeoutError()
    elif failure == 'login':
        smtp[1].login.side_effect = smtplib.SMTPServerDisconnected()
    else:
        smtp[1].send_message.side_effect = smtplib.SMTPDataError(451, b'temporary')
    data = payload(client)
    assert client.post('/api/requests', json=data).status_code == 503
    smtp[0].side_effect = smtp[1].login.side_effect = smtp[1].send_message.side_effect = None
    assert client.post('/api/requests', json=data).status_code == 503
    monkeypatch.setattr('backend.app.time.monotonic', lambda: before + 31)
    assert client.post('/api/requests', json=data).status_code == 200
    assert client.post('/api/requests', json=data).status_code == 200


def test_invalid_requests_do_not_spend_mail_budget(settings, smtp):
    app = create_app(replace(settings, global_limit=1))
    for n in range(100):
        with TestClient(app, client=(f'192.0.2.{n+1}', 1234), headers={'Origin': ORIGIN}) as c:
            assert c.post('/api/requests', content='{', headers={'Content-Type':'application/json'}).status_code == 422
    with TestClient(app, client=('198.51.100.1', 1234), headers={'Origin': ORIGIN}) as c:
        assert c.post('/api/requests', json=payload(c, token='invalid')).status_code == 422
        assert c.post('/api/requests', json=payload(c)).status_code == 200
        r = c.post('/api/requests', json=payload(c, subject='Другая заявка'))
        assert r.status_code == 429 and 3500 < int(r.headers['retry-after']) <= 3600
    smtp[1].send_message.assert_called_once()


def test_ipv6_prefix_limit_and_token_binding(settings, smtp):
    app = create_app(settings)
    for n in range(6):
        with TestClient(app, client=(f'2001:db8:1::{n+1}', 1234), headers={'Origin': ORIGIN}) as c:
            r = c.post('/api/requests', content='{', headers={'Content-Type':'application/json'})
            assert r.status_code == (422 if n < 5 else 429)
    with TestClient(app, client=('192.0.2.1',1234), headers={'Origin': ORIGIN}) as c:
        data = payload(c)
    with TestClient(app, client=('192.0.2.2',1234), headers={'Origin': ORIGIN}) as c:
        assert c.post('/api/requests', json=data).status_code == 422
        assert c.post('/api/requests', json=payload(c)).status_code == 200


def test_token_cannot_send_different_leads(client, smtp):
    data = payload(client)
    assert client.post('/api/requests', json=data).status_code == 200
    assert client.post('/api/requests', json={**data,'name':'Пётр','request_id':str(uuid4())}).status_code == 429
    smtp[1].send_message.assert_called_once()


def test_config_issuance_limited(client):
    for _ in range(30):
        assert client.get('/api/requests/config').status_code == 200
    assert client.get('/api/requests/config').status_code == 429


def test_restart_invalidates_old_token(settings, smtp):
    with TestClient(create_app(settings), headers={'Origin': ORIGIN}) as c:
        data = payload(c)
    with TestClient(create_app(settings), headers={'Origin': ORIGIN}) as c:
        assert c.post('/api/requests', json=data).status_code == 422
        assert c.post('/api/requests', json=payload(c)).status_code == 200
