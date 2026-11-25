"""Provisional synchronous v1 OTP delivery contract."""

import json
import logging
import os
import re
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import ConnectTimeoutError, ReadTimeoutError

LOGGER = logging.getLogger(__name__)
REFERENCE = re.compile(r"[a-z][a-z0-9_-]{0,63}")
CODE = re.compile(r"[0-9]{6}")
PHONE = re.compile(r"\+[1-9][0-9]{7,14}")
FIELDS = {"version", "challenge_id", "recipient_ref", "code"}


class MockSender:
    def send(self, recipient: str, code: str) -> None:
        """Acknowledge a synthetic delivery without persisting its payload."""


class SnsSender:
    def __init__(self):
        # Direct SMS has no idempotency key. A provider timeout is ambiguous.
        for namespace in ("boto3", "botocore"):
            logging.getLogger(namespace).setLevel(logging.WARNING)
        self.client = boto3.client(
            "sns",
            config=Config(connect_timeout=1, read_timeout=2, retries={"total_max_attempts": 1}),
        )

    def send(self, recipient: str, code: str) -> None:
        self.client.publish(
            PhoneNumber=recipient,
            Message=f"ElectionHub verification code: {code}",
            MessageAttributes={
                "AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"}
            },
        )


def valid_request(event) -> bool:
    if not isinstance(event, dict) or event.keys() != FIELDS:
        return False
    if type(event["version"]) is not int or event["version"] != 1:
        return False
    if any(not isinstance(event[field], str) for field in FIELDS - {"version"}):
        return False
    challenge_id = event["challenge_id"]
    try:
        return (
            len(challenge_id) == 36
            and str(UUID(challenge_id)) == challenge_id
            and REFERENCE.fullmatch(event["recipient_ref"]) is not None
            and CODE.fullmatch(event["code"]) is not None
        )
    except ValueError:
        return False


def lambda_handler(event, context) -> dict[str, int | str]:
    if not valid_request(event):
        return {"version": 1, "status": "invalid_request"}

    mode = os.getenv("OTP_DELIVERY_MODE", "mock")
    try:
        allowlist = json.loads(os.getenv("OTP_RECIPIENTS_JSON", '{"demo-otp":"synthetic"}'))
    except ValueError:
        allowlist = None
    if mode not in {"mock", "sns"} or not isinstance(allowlist, dict):
        LOGGER.warning("OTP delivery configuration unavailable")
        return {"version": 1, "status": "provider_unavailable"}

    recipient = allowlist.get(event["recipient_ref"])
    if not isinstance(recipient, str) or not recipient:
        return {"version": 1, "status": "recipient_not_allowed"}
    if mode == "sns" and not PHONE.fullmatch(recipient):
        LOGGER.warning("OTP delivery configuration unavailable")
        return {"version": 1, "status": "provider_unavailable"}

    try:
        sender = SnsSender() if mode == "sns" else MockSender()
        sender.send(recipient, event["code"])
    except (ConnectTimeoutError, ReadTimeoutError, TimeoutError):
        LOGGER.warning("OTP delivery timed out")
        return {"version": 1, "status": "provider_unavailable"}
    except Exception:
        # Provider exceptions may contain the message body or destination.
        LOGGER.warning("OTP delivery failed")
        return {"version": 1, "status": "provider_unavailable"}
    return {"version": 1, "status": "accepted"}
