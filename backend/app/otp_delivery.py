import json
from contextlib import closing
from functools import cached_property
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class OtpDeliveryError(OSError):
    """Delivery could not be confirmed."""


class LambdaSmsSender:
    def __init__(self, function_arn: str, recipient_refs: dict[str, str]):
        self.function_arn = function_arn
        self.recipient_refs = recipient_refs

    @cached_property
    def client(self):
        return boto3.session.Session().client(
            "lambda",
            region_name=self.function_arn.split(":")[3],
            config=Config(connect_timeout=2, read_timeout=10, retries={"total_max_attempts": 1}),
        )

    def send(self, recipient: str, challenge_id: UUID, code: str) -> None:
        recipient_ref = self.recipient_refs.get(recipient)
        if recipient_ref is None:
            raise OtpDeliveryError("OTP recipient is not configured")
        payload = {
            "version": 1,
            "challenge_id": str(challenge_id),
            "recipient_ref": recipient_ref,
            "code": code,
        }
        try:
            response = self.client.invoke(
                FunctionName=self.function_arn,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload).encode("utf-8"),
            )
            with closing(response["Payload"]) as body:
                if response.get("StatusCode") != 200 or response.get("FunctionError"):
                    raise OtpDeliveryError("OTP Lambda invocation failed")
                result = json.loads(body.read(1024))
        except (BotoCoreError, ClientError, KeyError, ValueError, TimeoutError):
            raise OtpDeliveryError("OTP Lambda response unavailable") from None

        if result != {"version": 1, "status": "accepted"} or type(result["version"]) is not int:
            raise OtpDeliveryError("OTP Lambda did not accept delivery")
