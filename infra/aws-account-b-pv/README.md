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
