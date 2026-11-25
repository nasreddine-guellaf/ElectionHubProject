import json

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError

from app import lambda_otp

REQUEST = {
    "version": 1,
    "challenge_id": "12345678-1234-4234-8234-123456789abc",
    "recipient_ref": "demo-otp",
    "code": "012345",
}
PHONE = "+12025550101"


def test_default_mock_preserves_leading_zero(monkeypatch, caplog):
    deliveries = []
    monkeypatch.delenv("OTP_DELIVERY_MODE", raising=False)
    monkeypatch.setenv("OTP_RECIPIENTS_JSON", json.dumps({"demo-otp": PHONE}))
    monkeypatch.setattr(lambda_otp.MockSender, "send", lambda _, *args: deliveries.append(args))
    response = lambda_otp.lambda_handler(REQUEST, None)
    assert response == {"version": 1, "status": "accepted"}
    assert deliveries == [(PHONE, "012345")]
    assert PHONE not in caplog.text and "012345" not in caplog.text


@pytest.mark.parametrize(
    ("changes", "status"),
    [
        ({"code": 12345}, "invalid_request"),
        ({"code": "٠١٢٣٤٥"}, "invalid_request"),
        ({"version": "v1"}, "invalid_request"),
        ({"version": True}, "invalid_request"),
        ({"challenge_id": "bad"}, "invalid_request"),
        ({"phone": PHONE}, "invalid_request"),
        ({"recipient_ref": PHONE}, "invalid_request"),
        ({"recipient_ref": "unknown"}, "recipient_not_allowed"),
    ],
)
def test_rejects_invalid_requests_without_delivery(monkeypatch, changes, status):
    monkeypatch.delenv("OTP_RECIPIENTS_JSON", raising=False)
    monkeypatch.setattr(lambda_otp, "MockSender", lambda: pytest.fail("unexpected delivery"))
    assert lambda_otp.lambda_handler(REQUEST | changes, None) == {"version": 1, "status": status}


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (None, "accepted"),
        (ClientError({"Error": {"Message": f"{PHONE} 012345"}}, "Publish"), "provider_unavailable"),
        (
            ReadTimeoutError(endpoint_url=f"https://example.test/{PHONE}/012345"),
            "provider_unavailable",
        ),
    ],
)
def test_sns_redacts_provider_details(monkeypatch, caplog, failure, status):
    class FakeSNS:
        def publish(self, **kwargs):
            assert kwargs["PhoneNumber"] == PHONE
            assert kwargs["Message"].endswith("012345")
            if failure:
                raise failure

    def client(service, *, config):
        assert service == "sns"
        assert config.retries["total_max_attempts"] == 1
        return FakeSNS()

    monkeypatch.setenv("OTP_DELIVERY_MODE", "sns")
    monkeypatch.setenv("OTP_RECIPIENTS_JSON", json.dumps({"demo-otp": PHONE}))
    monkeypatch.setattr(lambda_otp.boto3, "client", client)
    response = lambda_otp.lambda_handler(REQUEST, None)
    assert response == {"version": 1, "status": status}
    assert PHONE not in caplog.text and "012345" not in caplog.text


def test_sns_requires_a_configured_phone(monkeypatch):
    monkeypatch.setenv("OTP_DELIVERY_MODE", "sns")
    monkeypatch.delenv("OTP_RECIPIENTS_JSON", raising=False)
    monkeypatch.setattr(lambda_otp, "SnsSender", lambda: pytest.fail("unexpected SNS client"))
    assert lambda_otp.lambda_handler(REQUEST, None) == {
        "version": 1,
        "status": "provider_unavailable",
    }
