# Open Horizons integrated PV network draft

This Terraform root is for peer review. It targets only Open Horizons account `865579549007` in `eu-north-1`, with its own local state. The standalone mock demo remains under `infra/aws-account-b`.

The supplied Stockholm inventory showed only the default VPC `172.31.0.0/16`, its local and internet gateway routes, and no peering, VPN, or Transit Gateway attachments. The ElectionHub VPC proposal `10.41.0.0/16` is disjoint from the observed ranges in both accounts. Recheck the live inventory before provisioning. The private subnets use physical AZ IDs `eun1-az1` and `eun1-az2`. Confirm placement against Nasr's AZ IDs before approval.

## Review the draft

Run from the repository root:

```powershell
$terraform = '.\.local\tools\terraform.exe'
& $terraform -chdir=infra/aws-account-b-pv fmt -check
& $terraform -chdir=infra/aws-account-b-pv init -backend=false
& $terraform -chdir=infra/aws-account-b-pv validate
& $terraform -chdir=infra/aws-account-b-pv test
```

The tests use a mocked AWS provider and placeholder Account A IDs.

For a live preview, obtain Account A's ElectionHub VPC ID, RDS security-group ID, and dedicated RDS IAM role ARN from Nasr. Agree on one or two STS endpoint AZs before planning. Create the local directory `.local/aws-account-b`, initialize normally, and supply the following inputs with `terraform plan -input=false`. Use a separate saved filename such as `../../.local/aws-account-b/integrated-pv.tfplan`.

| Input | Value |
|---|---|
| `aws_profile` | `electionhub-new-dev` |
| `account_a_vpc_id` | Nasr's ElectionHub VPC ID |
| `account_a_rds_security_group_id` | Nasr's RDS security-group ID |
| `account_a_db_role_arn` | Nasr's dedicated Account A database role ARN |
| `sts_second_az` | `false` for a one-AZ qualification or `true` for two AZs |
| `peering_active` | `false` for the initial plan |

## Sequence after separate approval

1. The initial B plan creates the private network, endpoints, security groups, role, and peering request. Nasr reviews and accepts the request separately in Account A.
2. Verify that peering is active. Plan again in B with `peering_active=true` to add requester DNS options, the four RDS routes and PostgreSQL egress. A manages the accepter DNS options, RDS return routes, RDS ingress and the bucket policy.
3. After review and approved provisioning, send Nasr the five Terraform outputs. Verify the peering status with EC2 before describing that ID as active.
4. The integrated Lambda, cross-account STS token signing, and S3 invoke permission need a follow-up runtime plan. Keep the bucket notification disabled until the private runtime proves exact-version S3 reads, IAM-authenticated PostgreSQL with `verify-full`, and safe replay.

The network draft includes no Lambda deployment or S3 notification. The interface endpoint starts incurring its own usage charges once provisioned, including while the runtime is pending.

## Integrated Lambda runtime preview

After Account A confirms the reviewed bucket policy and applies its side, use the
original Stockholm RDS hostname and database name supplied by Nasr. The runtime
flag defaults to false. The runtime plan uses the existing integrated PV state.
It adds the function, its VPC and logging permissions, log group, and dead-letter
queue. There is no S3 invoke permission or notification in this stage.

Rebuild `.local/build/lambda_pv.zip` with `scripts/build_lambda_pv.ps1` before
planning. Use the same Account A inputs, keep `peering_active=true` and
`sts_second_az=false`, and pass these additional inputs:

```powershell
$tf = '.\.local\tools\terraform.exe'
& $tf -chdir=infra/aws-account-b-pv plan -input=false `
  -var 'account_a_vpc_id=vpc-043cc55a4ffb65db5' `
  -var 'account_a_rds_security_group_id=sg-06fb233923ca3ff10' `
  -var 'account_a_db_role_arn=arn:aws:iam::749251635900:role/electionhub/ElectionHubAccountBPvDatabase' `
  -var 'peering_active=true' -var 'sts_second_az=false' `
  -var 'enable_pv_runtime=true' `
  -var 'account_a_rds_hostname=<original RDS hostname>' `
  -var 'account_a_rds_database=<database name>' `
  -out ../../.local/aws-account-b/integrated-pv-runtime.tfplan
```

Before applying, review the saved plan separately. After an approved runtime
deployment, coordinate with Nasr to prepare a synthetic report document and its
matching AWS-5A database metadata. Put a versioned S3 event for that object in
`.local/aws-account-b/pv-qualification.json` using the [demo event shape](../aws-account-b/events/pv.json),
with a single record containing the real synthetic object key, version ID,
sequencer and Account A bucket. Invoke synchronously using an authorized Account
B caller:

```powershell
aws lambda invoke --profile electionhub-new-dev --region eu-north-1 `
  --function-name electionhub-b-pv --invocation-type RequestResponse `
  --payload fileb://.local/aws-account-b/pv-qualification.json `
  .local/aws-account-b/pv-qualification-response.json --no-cli-pager
Get-Content .local/aws-account-b/pv-qualification-response.json
```

Confirm HTTP status 200 with no `FunctionError`. The first invocation should
return one processed event. Invoke again with the same event and verify that
it returns one duplicate. Nasr should confirm one logical `object_events` row
and the expected report state. The first invocation exercises the regional STS
role assumption, exact S3 version read, and PostgreSQL using `verify-full`.
Keep the S3 notification off until the team has reviewed this evidence.

### Retry through a versioned Account B artifact

If a direct ZIP upload repeatedly expires, review using a private, versioned
artifact bucket in Stockholm in Open Horizons. With approval, reuse an existing
artifact bucket or create one through a separately reviewed plan. Keep the
Account A reports bucket out of this staging flow.

The Open Horizons inventory contained no general-purpose bucket in Stockholm.
Review the [dedicated artifact-bucket Terraform root](../aws-account-b-pv-artifacts/main.tf)
using the PowerShell session with the Open Horizons login:

```powershell
$tf = '.\.local\tools\terraform.exe'
New-Item -ItemType Directory -Force .local/aws-account-b | Out-Null
& $tf -chdir=infra/aws-account-b-pv-artifacts init -input=false
& $tf -chdir=infra/aws-account-b-pv-artifacts plan -input=false `
  -var 'enable_artifact_bucket=true' `
  -out ../../.local/aws-account-b/pv-artifacts.tfplan
```

Review the plan for six additions and no changes or destructions on an empty
artifact state. Confirm the bucket name and Stockholm region. After approval
and apply, keep `enable_artifact_bucket=true` in any subsequent plans that
should retain the bucket. This root has its own state, separate from the
partially applied PV runtime. S3 storage and requests can consume credits.


Upload the reviewed ZIP and record the returned object version. This command
supplies the ZIP checksum and verifies the bucket owner:

```powershell
$bucket = '<approved Account B artifact bucket>'
$key = 'pv/lambda_pv.zip'
$zip = (Resolve-Path .local/build/lambda_pv.zip).Path
$sha = [System.Security.Cryptography.SHA256]::Create()
try {
    $checksum = [Convert]::ToBase64String($sha.ComputeHash([IO.File]::ReadAllBytes($zip)))
} finally {
    $sha.Dispose()
}
aws s3api put-object --profile electionhub-new-dev --region eu-north-1 `
  --expected-bucket-owner 865579549007 --bucket $bucket --key $key `
  --body $zip --checksum-sha256 $checksum --no-cli-pager
```

Stop if the upload fails or the response has no version ID. Save the confirmed
bucket, key, and exact version to an ignored local JSON variable file named
`.local/aws-account-b/pv-artifact.tfvars.json`:

```json
{
  "pv_runtime_s3": {
    "bucket": "<approved Account B artifact bucket>",
    "key": "pv/lambda_pv.zip",
    "version_id": "<version returned by S3>"
  }
}
```

Generate a fresh preview using the runtime inputs above, plus
`-var-file=../../.local/aws-account-b/pv-artifact.tfvars.json`. Save it under
a new name for review. If the function is still absent, expect only the
Lambda and its retry configuration. Keep the staged version available through
plan review and deployment. The S3 report notification remains off.
