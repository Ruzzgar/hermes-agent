import asyncio
import base64
import hashlib
import hmac
import urllib.parse
from unittest.mock import AsyncMock

import pytest
from yarl import URL

from gateway.config import PlatformConfig
from gateway.platforms.sms import SmsAdapter


class _FakeRequest:
    def __init__(self, raw: bytes, headers: dict[str, str], *, scheme: str, host: str, path_qs: str):
        self._raw = raw
        self.headers = headers
        self.scheme = scheme
        self.host = host
        self.rel_url = URL(path_qs)
        self.url = URL(f"{scheme}://{host}{path_qs}")

    async def read(self) -> bytes:
        return self._raw


def _twilio_signature(url: str, raw: bytes, auth_token: str) -> str:
    form = urllib.parse.parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    payload = url
    for key in sorted(form):
        for value in sorted(form[key]):
            payload += key + value
    digest = hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


@pytest.fixture
def sms_adapter(monkeypatch: pytest.MonkeyPatch) -> SmsAdapter:
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "twilio-secret")
    monkeypatch.setenv("TWILIO_PHONE_NUMBER", "+15557654321")
    return SmsAdapter(PlatformConfig(enabled=True))


@pytest.mark.asyncio
async def test_sms_webhook_rejects_missing_twilio_signature(sms_adapter: SmsAdapter):
    sms_adapter.handle_message = AsyncMock(return_value=None)
    raw = b"From=%2B15551234567&To=%2B15557654321&Body=ping&MessageSid=SM123"
    request = _FakeRequest(
        raw,
        headers={"Host": "127.0.0.1:8080"},
        scheme="http",
        host="127.0.0.1:8080",
        path_qs="/webhooks/twilio",
    )

    response = await sms_adapter._handle_webhook(request)
    await asyncio.sleep(0)

    assert response.status == 403
    sms_adapter.handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_sms_webhook_accepts_valid_signature_with_public_url_override(
    sms_adapter: SmsAdapter,
):
    sms_adapter.handle_message = AsyncMock(return_value=None)
    sms_adapter._webhook_url = "https://sms.example.com/webhooks/twilio"
    raw = (
        b"From=%2B15551234567&To=%2B15557654321&Body=ping&MessageSid=SM123&NumMedia="
    )
    signature = _twilio_signature(sms_adapter._webhook_url, raw, "twilio-secret")
    request = _FakeRequest(
        raw,
        headers={
            "Host": "127.0.0.1:8080",
            "X-Twilio-Signature": signature,
        },
        scheme="http",
        host="127.0.0.1:8080",
        path_qs="/webhooks/twilio",
    )

    response = await sms_adapter._handle_webhook(request)
    await asyncio.sleep(0)

    assert response.status == 200
    sms_adapter.handle_message.assert_awaited_once()
    event = sms_adapter.handle_message.await_args.args[0]
    assert event.text == "ping"
    assert event.message_id == "SM123"
    assert event.source.chat_id == "+15551234567"
