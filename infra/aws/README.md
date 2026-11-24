# ElectionHub AWS-4B / AWS-5A Terraform plans

This directory prepares AWS-4B without provisioning anything. It has three safety layers:

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
- application role: S3 access limited to `reports/*`, with encrypted uploads required;
- network: dedicated VPC and two isolated database subnets with no Internet route;
- PostgreSQL: RDS PostgreSQL 16.15, `db.t4g.micro`, Single-AZ, 20 GiB gp3, encryption,
  forced TLS, seven-day automated backups, deletion protection, no Performance Insights;
- RDS master password: generated and managed by RDS in Secrets Manager, never placed in
  Terraform variables or state as plaintext;
- runtime password: generated inside the controlled runner for a non-owner
  `electionhub_app` role and stored in a separate Secrets Manager secret;
- optional runner: Amazon Linux 2023 `t4g.micro`, no inbound rules, SSM-managed, IMDSv2,
  encrypted 8 GiB root disk, and automatic termination after two hours.
- optional Lambda PV: RDS IAM login without a password, column-level SQL grants, private
  networking, regional S3 Gateway endpoint, bounded concurrency, logs and encrypted DLQ.

The RDS endpoint is always private. With the runner disabled its security group has no ingress.
When the runner is explicitly enabled, PostgreSQL ingress is granted only from the runner's
security group. The runner itself has no inbound rules; its temporary public IPv4 address is
used only for outbound SSM, package, Git, and CA access. No NAT Gateway is created.

## Plan-only commands

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

# From the repository root, build the ignored Linux ZIP before the AWS-5A preview.
Set-Location ../..
.\scripts\build_lambda_pv.ps1
Set-Location infra/aws

# Preview RDS plus Lambda PV and the filtered S3 notification. Do not apply.
& $terraform plan -out ..\..\.local\plans\aws5a-pv-lambda.tfplan `
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
- neither saved plan was applied.

The saved plans are intentionally ignored. Never apply an old saved plan: renew the AWS login,
rerun all three plans, inspect their JSON action summary, and obtain explicit approval first.
The exact bootstrap and cleanup sequence is documented in
[`docs/infrastructure/aws-4b-rds-plan.md`](../../docs/infrastructure/aws-4b-rds-plan.md).
The idempotency, IAM database authentication, packaging and future event test sequence are in
[`docs/infrastructure/aws-5a-lambda-pv.md`](../../docs/infrastructure/aws-5a-lambda-pv.md).
