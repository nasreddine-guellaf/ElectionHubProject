"""End-to-end S3 smoke test through the ElectionHub API.

The script creates one uniquely keyed synthetic PDF, verifies it in S3, deletes it
through ElectionHub, and finally removes only the versions belonging to that test key.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import boto3
import httpx
from botocore.exceptions import ClientError
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--profile", default=os.getenv("AWS_PROFILE", "electionhub-demo")
    )
    return parser.parse_args()


def purge_test_versions(s3, bucket: str, key: str) -> int:
    response = s3.list_object_versions(Bucket=bucket, Prefix=key)
    targets = [
        {"Key": item["Key"], "VersionId": item["VersionId"]}
        for group in ("Versions", "DeleteMarkers")
        for item in response.get(group, [])
        if item["Key"] == key
    ]
    if targets:
        s3.delete_objects(Bucket=bucket, Delete={"Objects": targets, "Quiet": True})
    return len(targets)


def main() -> None:
    args = arguments()
    config = dotenv_values(ROOT / ".env")
    bucket = config.get("S3_BUCKET")
    region = config.get("AWS_REGION")
    if config.get("OBJECT_STORAGE_BACKEND") != "s3" or not bucket or not region:
        raise RuntimeError(".env must select S3 and provide AWS_REGION and S3_BUCKET")

    credentials = json.loads((ROOT / ".local" / "demo-credentials.json").read_text())
    session = boto3.Session(profile_name=args.profile, region_name=region)
    identity = session.client("sts").get_caller_identity()
    s3 = session.client("s3")
    content = (
        b"%PDF-1.4\n"
        b"% ElectionHub temporary S3 integration qualification\n"
        b"1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"
    )
    digest = hashlib.sha256(content).hexdigest()
    document = None
    object_key = None
    deleted_through_api = False

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "demo-agent", "password": credentials["demo-agent"]},
        )
        login.raise_for_status()
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        reports = client.get("/api/v1/reports", params={"limit": 20, "offset": 0})
        reports.raise_for_status()
        draft = None
        for report in reports.json()["items"]:
            revisions = client.get(
                f"/api/v1/reports/{report['id']}/revisions",
                params={"limit": 20, "offset": 0},
            )
            revisions.raise_for_status()
            draft = next(
                (
                    (report, revision)
                    for revision in revisions.json()["items"]
                    if revision["status"] == "DRAFT"
                    and revision["revision_number"] == report["current_revision"]
                ),
                None,
            )
            if draft:
                break
        if draft is None:
            raise RuntimeError("No current draft belonging to demo-agent was found")

        report, revision = draft
        base = f"/api/v1/reports/{report['id']}/revisions/{revision['revision_number']}"
        try:
            upload = client.post(
                f"{base}/documents",
                data={"expected_version": str(revision["edit_version"])},
                files={
                    "file": ("electionhub-s3-smoke.pdf", content, "application/pdf")
                },
            )
            upload.raise_for_status()
            document = upload.json()
            object_key = (
                f"reports/{report['id']}/revisions/{revision['revision_number']}/"
                f"{document['id']}.pdf"
            )

            head = s3.head_object(Bucket=bucket, Key=object_key)
            download = client.get(f"{base}/documents/{document['id']}/content")
            download.raise_for_status()
            if hashlib.sha256(download.content).hexdigest() != digest:
                raise RuntimeError(
                    "Downloaded document checksum does not match the upload"
                )
            if document["sha256"] != digest or document["storage_provider"] != "S3":
                raise RuntimeError(
                    "ElectionHub document metadata does not match the upload"
                )
            if head.get("ServerSideEncryption") != "AES256":
                raise RuntimeError("The uploaded object is not encrypted with SSE-S3")
            expected_metadata = {
                "document-id": document["id"],
                "revision-id": document["revision_id"],
            }
            if head.get("Metadata") != expected_metadata:
                raise RuntimeError(
                    "S3 object metadata does not match ElectionHub metadata"
                )

            deletion = client.delete(f"{base}/documents/{document['id']}")
            deletion.raise_for_status()
            deleted_through_api = deletion.status_code == 204
            listing = client.get(f"{base}/documents")
            listing.raise_for_status()
            if any(item["id"] == document["id"] for item in listing.json()):
                raise RuntimeError("Deleted document is still returned by ElectionHub")
            try:
                s3.head_object(Bucket=bucket, Key=object_key)
            except ClientError as exc:
                if exc.response["Error"]["Code"] not in {"404", "NoSuchKey"}:
                    raise
            else:
                raise RuntimeError(
                    "S3 object still resolves after ElectionHub deletion"
                )
        finally:
            if document is not None and not deleted_through_api:
                client.delete(f"{base}/documents/{document['id']}")
            purged_versions = (
                purge_test_versions(s3, bucket, object_key) if object_key else 0
            )

    print(
        json.dumps(
            {
                "account": identity["Account"],
                "region": region,
                "bucket": bucket,
                "upload_status": 201,
                "download_status": 200,
                "checksum_match": True,
                "storage_provider": document["storage_provider"],
                "server_side_encryption": "AES256",
                "delete_status": 204,
                "temporary_versions_purged": purged_versions,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
