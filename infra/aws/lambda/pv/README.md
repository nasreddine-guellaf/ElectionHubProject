# Lambda PV package

The source of the idempotent handler is `backend/app/lambda_pv.py`. Build its ignored,
Linux-compatible deployment ZIP from the repository root:

```powershell
.\scripts\build_lambda_pv.ps1
```

The script installs pinned manylinux x86-64 dependencies, validates the official regional RDS
CA bundle and writes `.local/build/lambda_pv.zip`. Terraform only reads that artifact when
`enable_pv_lambda=true`. Never commit the ZIP or replace its CA with an unverified download.
