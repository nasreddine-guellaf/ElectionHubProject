# ElectionHub AWS-4B / AWS-5A / AWS-5B Terraform plans

Nasr Eddine owns this Terraform root for Account A in `eu-north-1`. For the
two-account target, keep `enable_pv_lambda=false`: that flag enables the
original single-account Lambda, VPC wiring, and bucket notification together.
Account B will use a separate root, provider account guard, and state. The
future Account A notification will reference the reviewed Account B Lambda ARN.
See the [two-account integration design](../../docs/infrastructure/aws-two-accounts.md)
and [Account B onboarding](../../docs/infrastructure/aws-account-b-onboarding.md).

This directory manages the Account A deployment. Its safeguards are:

- the existing S3 bucket is represented by Terraform `import` blocks and every S3 resource
  has `prevent_destroy`;
- IAM, VPC, Secrets Manager, and RDS use `enable_new_resources = false` by default;
- the temporary migration runner also requires `enable_test_runner = true`;
- Lambda PV and its S3 notification additionally require `enable_pv_lambda = true`.

An import block changes no AWS resource during `terraform plan`. Importing into state would
require a later, explicitly approved `terraform apply`. Do not apply until the plan shows
only the expected imports and approved creations, with no S3 update or destroy action.

## Prepared target

- region: `eu-north-1` only;
- existing S3 bucket: imported, never recreated;
- application role: S3 access limited to `reports/*` and `incidents/*`, with encrypted uploads required;
- network: dedicated VPC and two isolated database subnets with no Internet route;
- PostgreSQL: RDS PostgreSQL 16.15, `db.t4g.micro`, Single-AZ, 20 GiB gp3, encryption,
  forced TLS, one-day automated backups on Account A's Free plan, deletion protection,
  no Performance Insights;
- RDS master password: generated and managed by RDS in Secrets Manager, never placed in
  Terraform variables or state as plaintext;
- runtime password: generated inside the controlled runner for a non-owner
  `electionhub_app` role and stored in a separate Secrets Manager secret;
- optional runner: Amazon Linux 2023 `t4g.micro`, no inbound rules, SSM-managed, IMDSv2,
  encrypted 8 GiB root disk, and automatic termination after two hours.
- historical single-account Lambda PV: RDS IAM login without a password, column-level SQL grants, private
  networking, regional S3 Gateway endpoint, bounded concurrency, logs and encrypted DLQ.

The RDS endpoint is always private. With the runner disabled its security group has no ingress.
When the runner is explicitly enabled, PostgreSQL ingress is granted only from the runner's
security group. The runner itself has no inbound rules; its temporary public IPv4 address is
used only for outbound SSM, package, Git, and CA access. No NAT Gateway is created.

## Plan-only commands

The Account A deployment uses local state outside the checkout at
`%LOCALAPPDATA%\ElectionHub\AccountA\eu-north-1\terraform.tfstate`. For Account A,
pass this path as `-state` on subsequent local-backend plans, applies and state
commands. Keep a protected backup. The commands and figures below without that
flag describe the historical pre-adoption previews.

### Account A backup API

The deployed baseline uses `enable_new_resources=true`, `enable_backup_api=true`,
`enable_test_runner=false`, `enable_pv_lambda=false`, and
`backup_api_commit=8809703adb6aef8a41c5f5eb0fbd839682e36831`. Preserve these
settings when planning against live state. The backup flag manages a single
ARM64 `t4g.micro`, its instance profile, and the required VPC rules. The
instance has an outbound public IPv4 for HTTPS and SSM, an encrypted gp3 volume,
IMDSv2, no inbound rules, and a loopback-only FastAPI service. Its IAM role
reads only the application database secret and uses the existing private S3
prefix policy. RDS accepts port 5432 from the backup API security group.

Use SSM to check `systemctl status electionhub-api` and
`curl -fsS http://127.0.0.1:8000/health`. The pinned source above predates the
cloud health schema fix. The running instance received that fix via SSM. On
the next release, publish and pin a commit that includes the fix before
replacing the instance. `backup/smoke.py` uses a synthetic scoped fixture
and the live API. Run it from the backend working directory as the service
user, with the application secret ARN and bucket name as its two arguments.
Use the locked HTTP test dependencies on a temporary Python path. Afterward,
an operator with S3 version permissions removes
only the exact reported `TEST_KEY` versions and delete markers.

Live qualification passed: health and polling-station read returned 200,
PostgreSQL reported TLS active, and the PDF round trip returned 201/200/204
with matching SHA-256 and SSE-S3. The fixture removed its synthetic database
rows. Terraform reported no changes after deployment.

The instance can serve as a backup integration target once a supported,
authenticated GCP ingress and failover path has been designed and tested.

Terraform 1.17.2 is installed locally under the ignored `.local/tools` directory. The binary
was downloaded from HashiCorp and its SHA-256 was checked against the official checksum file.

```powershell
Set-Location infra/aws

$env:TF_VAR_aws_account_id = "749251635900"
$env:TF_VAR_existing_s3_bucket_name = "electionhub-demo-749251635900-eu-north-1"

$terraform = Resolve-Path ..\..\.local\tools\terraform-1.17.2\terraform.exe

& $terraform init -backend=false
& $terraform fmt -check -recursive
& $terraform validate

# Existing S3 adoption only. Do not apply.
& $terraform plan -out ..\..\.local\plans\aws4b-s3-only.tfplan `
  -var "enable_new_resources=false"

# Preview IAM, isolated VPC, Secrets Manager, and private RDS. Do not apply.
& $terraform plan -out ..\..\.local\plans\aws4b-private-rds.tfplan `
  -var "enable_new_resources=true" `
  -var "enable_test_runner=false"

# Preview the separate, temporary runner. Do not apply.
& $terraform plan -out ..\..\.local\plans\aws4b-private-rds-runner.tfplan `
  -var "enable_new_resources=true" `
  -var "enable_test_runner=true"

# Historical single-account AWS-5A / AWS-5B previews below.
# Keep enable_pv_lambda=false when planning the two-account Account A target.
# From the repository root, build the ignored Linux ZIP before the AWS-5A preview.
Set-Location ../..
.\scripts\build_lambda_pv.ps1
Set-Location infra/aws

# Preview RDS plus Lambda PV and the filtered S3 notification. Do not apply.
& $terraform plan -out ..\..\.local\plans\aws5a-pv-lambda.tfplan `
  -var "enable_new_resources=true" `
  -var "enable_test_runner=false" `
  -var "enable_pv_lambda=true"

# Re-run after AWS-5B to verify the application role's incidents/* prefix. Do not apply.
& $terraform plan -out ..\..\.local\plans\aws5b-incidents.tfplan `
  -var "enable_new_resources=true" `
  -var "enable_test_runner=false" `
  -var "enable_pv_lambda=true"
```

Generated `.tfplan`, state, and `.terraform` content are ignored by Git. No `apply`, state
import, bucket update, database migration, or resource provisioning belongs to AWS-3
preparation.

Validated on 24 November 2026 with Terraform 1.17.2 and AWS provider 6.73.0:

- S3 adoption plan: 6 imports, 0 add, 0 change, 0 destroy;
- private IAM/VPC/RDS preview: 6 imports, 13 add, 0 change, 0 destroy;
- private RDS plus temporary runner preview: 6 imports, 27 add, 0 change, 0 destroy;
- private RDS plus Lambda PV preview: 6 imports, 25 add, 0 change, 0 destroy;
- AWS-5B incidents preview: 6 imports, 25 add, 0 change, 0 destroy; all six existing S3
  controls remain no-op and the application role includes only `reports/*` and `incidents/*`;
- none of these saved plans was applied.

The saved plans are intentionally ignored. Never apply an old saved plan: renew the AWS login,
rerun all three plans, inspect their JSON action summary, and obtain explicit approval first.
The exact bootstrap and cleanup sequence is documented in
[`docs/infrastructure/aws-4b-rds-plan.md`](../../docs/infrastructure/aws-4b-rds-plan.md).
The idempotency, IAM database authentication, packaging and future event test sequence are in
[`docs/infrastructure/aws-5a-lambda-pv.md`](../../docs/infrastructure/aws-5a-lambda-pv.md).
