# Account B serverless demo and integration review

Bouzadi Badreddine owns the Account B demo. Nasr Eddine Guellaf owns Account A's S3 bucket, private RDS, networking, schema, and EC2 backup backend. The OTP schema follows the [two-account integration guide](aws-two-accounts.md) and was confirmed by Nasr for the FastAPI adapter. The [Account B onboarding guide](aws-account-b-onboarding.md) covers initial account setup.

## Run locally

From the repository root in PowerShell, with the backend's locked dependencies installed in `.venv`:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest -q tests/test_lambda_pv.py tests/test_lambda_otp.py
Pop-Location
python scripts/build_account_b_demo.py
terraform -chdir=infra/aws-account-b fmt -check -recursive
terraform -chdir=infra/aws-account-b init -backend=false
terraform -chdir=infra/aws-account-b validate
terraform -chdir=infra/aws-account-b test
```

The mock Terraform test runs a plan against a mocked AWS provider. The PV demo accepts the checked-in synthetic S3 fixture, verifies the requested version and digest, and counts one processed record and one duplicate within that invocation. Its fake SQL state resets on each invocation. The PV handler acknowledges the standalone S3 test notification without creating an S3 or SQL connection. The integrated ZIP built by `scripts/build_lambda_pv.ps1` includes only the real PV handler, pinned dependencies, and RDS CA bundle. Keep `enable_pv_lambda = false` in `infra/aws` for the two-account setup.

The baseline PV suite passed 10 tests. The updated demo suite passed 40 focused tests, with one Starlette dependency deprecation warning. Ruff, Terraform formatting and validation, and the mocked Terraform plan passed. Both demo ZIP handlers returned the expected results when invoked locally with the checked-in fixtures.

## OTP v1 contract

Use a synchronous Lambda invocation with a JSON object containing exactly these fields.

| Field | Rule |
|---|---|
| `version` | Integer `1` |
| `challenge_id` | Canonical lowercase UUID |
| `recipient_ref` | Allowlist key matching `[a-z][a-z0-9_-]{0,63}` |
| `code` | Six ASCII digits as a string, for example `012345` |

The result contains only integer `version` (`1`) and `status`. `accepted` means the mock accepted the request or SNS accepted the publish. `invalid_request` means the schema failed. `recipient_not_allowed` means the reference is absent from the allowlist. `provider_unavailable` covers configuration failures, provider failures, and timeouts with an unknown provider outcome. Treat these as application statuses in the Lambda payload alongside the AWS invocation result.

FastAPI owns generation, expiration, attempt limits, challenge state, and code verification. The sender resolves `OTP_RECIPIENTS_JSON` on the server. The demo defaults to `demo-otp` with a synthetic target and never persists the delivery payload. SNS requires an explicit `OTP_DELIVERY_MODE=sns` and a configured E.164 allowlist value. The demo Terraform hardcodes mock mode and grants no SNS permission. For later SNS work, agree on how to inject the allowlist outside Terraform state. The SNS adapter makes one publish attempt with one-second connect and two-second read timeouts. Direct SMS has no idempotency key. A timeout may follow an accepted send, so FastAPI must invalidate the challenge and avoid automatic retries. Keep invocation payload and provider request logging off.

## Account B checks and plan

Open Horizons (`865579549007`) is Account B in Stockholm. Its active Free plan showed USD 100 in credits and a plan expiration of May 24, 2027 UTC. The `electionhub-new-dev` profile is backed by the project owner's temporary session. The Lambda list check succeeded. An explicit organization policy denied the SNS sandbox status check. Omit real SMS. The earlier Open Horizons preview showed 13 additions and no changes or deletions. Rebuild and regenerate the saved preview after handler changes. Create permissions are still pending verification.

Use a named profile backed by a temporary session. Confirm the returned account ID with Bouzadi before using it as the Terraform account guard.

```powershell
$profile = 'electionhub-new-dev'
$region = 'eu-north-1'
aws sts get-caller-identity --profile $profile --region $region
aws account get-region-opt-status --profile $profile --region us-east-1 --region-name $region
aws lambda list-functions --profile $profile --region $region --max-items 1
aws lambda get-account-settings --profile $profile --region $region
aws sns get-sms-sandbox-account-status --profile $profile --region $region
```

Confirm the Account B plan type, remaining credits, and expiry with the account owner or Billing console. Read access to Lambda and the list result do not establish deployment permissions. Confirm that the deployer can manage the demo Lambda functions, log groups, metric alarms, encrypted SQS queue, execution roles and inline policies, and that it can pass only those execution roles to Lambda. Have the account owner check the active session policy, permissions boundary, and any applicable SCP. Verify enough Lambda concurrency for two reservations. Record any region or API denial with its service, region, and error code. Direct S3-to-PV requires `eu-north-1`. An alternate demo region can be evaluated independently if Stockholm is unavailable. [S3 notification destinations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-how-to-event-types-and-destinations.html) · [SNS authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_sns.html)

After rebuilding both ZIPs, the Account B plan uses isolated local state under `.local/aws-account-b/` and an AWS provider restricted to the verified account. Use the following commands from the repository root with both demo ZIPs already built.

```powershell
$accountId = '865579549007'
New-Item -ItemType Directory -Force .local/aws-account-b | Out-Null
terraform -chdir=infra/aws-account-b init
terraform -chdir=infra/aws-account-b plan -input=false `
  -var "account_b_id=$accountId" -var "aws_profile=$profile" -var "aws_region=$region" `
  -out ../../.local/aws-account-b/open-horizons-demo.tfplan
terraform -chdir=infra/aws-account-b show ../../.local/aws-account-b/open-horizons-demo.tfplan
```

After a separately approved demo deployment, the synchronous smoke check can be run with the same temporary Account B profile. It uses synthetic payloads and checks the invocation and function results.

```powershell
.\scripts\smoke_account_b_demo.ps1 -Profile $profile -AccountId $accountId -Region $region
```

## Review with Nasr before integration

| Function | Proposed Lambda ARN | Proposed execution role ARN |
|---|---|---|
| Integrated PV | `arn:aws:lambda:eu-north-1:865579549007:function:electionhub-b-pv` | `arn:aws:iam::865579549007:role/electionhub/electionhub-b-pv-role` |
| OTP | `arn:aws:lambda:eu-north-1:865579549007:function:electionhub-b-otp` | `arn:aws:iam::865579549007:role/electionhub/electionhub-b-otp-role` |

The independent demo uses the separate `electionhub-b-demo-pv` and `electionhub-b-demo-otp` names, with role names suffixed by `-role`. Its Terraform outputs both ARN maps. Use the integrated names for the following review.

1. **S3 invocation.** Nasr confirms the Account A ID, bucket ARN, region, notification configuration and a synthetic fixture owner. Account B would grant `s3.amazonaws.com` invoke access on integrated PV, scoped to the exact source bucket ARN and Account A ID. Nasr would merge the `s3:ObjectCreated:*` notification filtered to `reports/` with any existing notifications. [S3 invocation permissions](https://docs.aws.amazon.com/lambda/latest/dg/with-s3.html)
2. **Versioned reads.** Nasr confirms versioning, the immutable-key convention, and bucket encryption. Agree on a bucket policy limited to the integrated PV role and `reports/*`. Account B would grant that role `s3:GetObjectVersion` and `s3:GetObject` on the same prefix. Review any KMS key policy and scoped decrypt grant if the bucket uses SSE-KMS.
3. **Private PostgreSQL.** Agree on private Lambda subnets, routes, DNS, security groups for TCP 5432, and how Lambda reaches S3 and STS from the private network. Nasr supplies the RDS endpoint, port, database name, resource ID, and event processor login, and verifies the schema and least-privilege SQL grants on `report_documents` and `object_events`. Agree on an Account A role scoped to `rds-db:connect` for that resource ID and login, trusted by the integrated Account B PV role. The integrated handler would need to assume that role for token generation and retain TLS `verify-full`. [Cross-account RDS IAM authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.IAMPolicy.html)
4. **Temporary GCP credentials.** Review with Nasr and the GCP owner a federated role in Account B restricted to the intended GCP workload identity, exact audience and invariant subject. Limit it to `lambda:InvokeFunction` on the intended OTP function or agreed alias, with a short session duration. FastAPI would invoke it through the AWS SDK with SigV4. Agree on the OTP region and invocation timeout budget with the GCP owner.
5. **OTP integration.** Nasr confirmed the four fields and the server-side recipient allowlist. FastAPI must inspect the invocation result and returned status, invalidate the challenge on failure or timeout, avoid automatic retries, and test that delivery failure gives the same public response as an unknown citizen. Keep real SMS disabled.

## Integrated PV network review

Nasr reported that his local Account A Terraform draft includes the RDS return routes, peer security-group access on TCP 5432, and versioned S3 reads for the exact Open Horizons PV role through B's gateway endpoint. His disabled integration plan reported no live changes. His restricted PostgreSQL test verified an initial write and replay with `RETURNING provider_event_id`.

The saved Open Horizons mock plan has no VPC, peering, Lambda security group, or S3 gateway endpoint. For the joint review, share the [integrated Account B network draft](../../infra/aws-account-b-pv/README.md) or plan first. After separately approved provisioning and peering acceptance, send Nasr the VPC ID, active peering ID, Lambda security-group ID, S3 gateway endpoint ID, and actual integrated PV role ARN. Nasr can then generate the enabled Account A plan. Keep the bucket notification disabled through private runtime qualification.

Nasr reported that Account A's ElectionHub and default VPCs use `10.40.0.0/16` and `172.31.0.0/16`. Account A has no ElectionHub peering, VPN, or Transit Gateway attachment. The planned GCP subnet `10.20.0.0/24` is disjoint. The supplied Open Horizons inventory showed only the default VPC and no peering, VPN, or Transit Gateway attachments. Recheck inventory before creating the proposed `10.41.0.0/16` VPC.

Run these read-only commands in the PowerShell session with the verified Open Horizons login:

```powershell
$profile = 'electionhub-new-dev'
$region = 'eu-north-1'
aws sts get-caller-identity --profile $profile --region $region --query Account --output text --no-cli-pager
aws ec2 describe-vpcs --profile $profile --region $region --query 'Vpcs[].{Vpc:VpcId,CIDRs:CidrBlockAssociationSet[].CidrBlock}' --no-cli-pager
aws ec2 describe-route-tables --profile $profile --region $region --no-cli-pager
aws ec2 describe-vpc-peering-connections --profile $profile --region $region --no-cli-pager
aws ec2 describe-vpn-connections --profile $profile --region $region --no-cli-pager
aws ec2 describe-transit-gateway-attachments --profile $profile --region $region --no-cli-pager
aws ec2 describe-availability-zones --profile $profile --region $region --query 'AvailabilityZones[].{Name:ZoneName,Id:ZoneId}' --no-cli-pager
```

Confirm the account is `865579549007` before interpreting the inventory. Treat denied inventory calls as unverified. Compare AZ IDs with Account A.

- **Peering routes.** B's private Lambda subnets are proposed as `10.41.10.0/24` and `10.41.11.0/24`. Both B route tables need routes to `10.40.10.0/24` and `10.40.11.0/24`. A's shared RDS route table needs return routes to both B subnets. No EC2 backup subnet route is required.
- **RDS.** Enable DNS support and hostnames. After peering is active, scope TCP 5432 ingress and egress to the peer Lambda and RDS security groups. Use the original RDS hostname and AWS CA with `verify-full`.
- **S3 and STS.** Nasr confirmed versioning, SSE-S3, and no bucket notifications. Associate the B S3 gateway endpoint with both Lambda route tables, permit HTTPS to the S3 prefix list, and restrict the endpoint, role and bucket policy to the PV identity and `reports/*`. Use `sts.eu-north-1.amazonaws.com` privately, with endpoint HTTPS ingress from the Lambda group. Scope `sts:AssumeRole` to the dedicated A role for `electionhub_event_processor`.
- **Cost decision.** Nasr's Stockholm estimate was USD 7.67/month for one STS endpoint AZ or USD 15.33/month for two at 730 hours, plus endpoint data and any cross-AZ charges. Confirm the AZ count and budget before planning the integrated deployment.
- **Qualification.** Review one plan per account. With the bucket notification disabled, test role assumption, an exact synthetic S3 object version, private DNS and TLS, and a first event followed by a replay under `electionhub_event_processor`. Confirm the insert returns `provider_event_id` and a replay writes only one logical event. Enable the bucket notification only after those checks pass.
