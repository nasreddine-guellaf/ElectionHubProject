mock_provider "aws" {}

run "disabled" {
  command = plan

  assert {
    condition     = length(aws_s3_bucket.pv) == 0
    error_message = "The draft must be off by default."
  }
}

run "private_versioned_artifact_bucket" {
  command = plan

  variables {
    enable_artifact_bucket = true
  }

  assert {
    condition = (
      !aws_s3_bucket.pv[0].force_destroy &&
      aws_s3_bucket_versioning.pv[0].versioning_configuration[0].status == "Enabled" &&
      aws_s3_bucket_ownership_controls.pv[0].rule[0].object_ownership == "BucketOwnerEnforced" &&
      aws_s3_bucket_public_access_block.pv[0].block_public_acls &&
      aws_s3_bucket_public_access_block.pv[0].ignore_public_acls &&
      aws_s3_bucket_public_access_block.pv[0].block_public_policy &&
      aws_s3_bucket_public_access_block.pv[0].restrict_public_buckets
    )
    error_message = "Artifact staging must be private and versioned."
  }
}
