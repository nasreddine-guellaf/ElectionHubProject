# ElectionHub AWS Terraform plan

This directory prepares AWS-3 without provisioning anything. The configuration has two
safety layers:

- the existing S3 bucket is represented by Terraform `import` blocks and every S3 resource
  has `prevent_destroy`;
- IAM, VPC, and RDS resources use `enable_new_resources = false` by default.

An import block changes no AWS resource during `terraform plan`. Importing into state would
require a later, explicitly approved `terraform apply`. Do not apply until the plan shows
only the expected imports and approved creations, with no S3 update or destroy action.

## Prepared target

- region: `eu-north-1` only;
- existing S3 bucket: imported, never recreated;
- application role: S3 access limited to `reports/*`, with encrypted uploads required;
- network: dedicated VPC, two subnets in separate Availability Zones, no NAT Gateway;
- PostgreSQL: RDS PostgreSQL 16.15, `db.t4g.micro`, Single-AZ, 20 GiB gp3, encryption,
  forced TLS, one-day automated backups, deletion protection, no Performance Insights;
- RDS master password: generated and managed by RDS in Secrets Manager, never placed in
  Terraform variables or state as plaintext.

The RDS endpoint is private by default and the security group has no ingress. A public
endpoint is allowed only when at least one explicit CIDR is supplied; `0.0.0.0/0` and
`::/0` are rejected by variable validation.

## Plan-only commands

Install Terraform 1.5 or later first. Terraform is not currently installed on the
development machine.

```powershell
Set-Location infra/aws

$env:TF_VAR_aws_account_id = "749251635900"
$env:TF_VAR_existing_s3_bucket_name = "electionhub-demo-749251635900-eu-north-1"

terraform init
terraform fmt -check -recursive
terraform validate

# Existing S3 adoption only. Do not apply.
terraform plan -out aws3-s3-import.tfplan

# Preview IAM, VPC, and private RDS creation. Do not apply.
terraform plan -out aws3-private-rds.tfplan -var "enable_new_resources=true"
```

If the later GCP design uses a public RDS endpoint, first reserve a fixed GCP egress IPv4
address, then preview the restricted rule. Replace the example address; never use it as-is.

```powershell
terraform plan -out aws3-filtered-rds.tfplan `
  -var "enable_new_resources=true" `
  -var "rds_publicly_accessible=true" `
  -var 'postgres_ingress_cidrs=["203.0.113.10/32"]'
```

Generated `.tfplan`, state, and `.terraform` content are ignored by Git. No `apply`, state
import, bucket update, database migration, or resource provisioning belongs to AWS-3
preparation.

Validated on 23 November 2026 with Terraform 1.17.2 and AWS provider 6.73.0:

- S3 adoption plan: 6 imports, 0 add, 0 change, 0 destroy;
- private IAM/VPC/RDS preview: 6 imports, 14 add, 0 change, 0 destroy;
- neither saved plan was applied.
