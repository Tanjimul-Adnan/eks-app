# eks-app

Sample application repository. Pushes to `main` run tests, build a container, push it to ECR using GitHub OIDC, then create a PR in `eks-helm` to update the image tag.

## Required GitHub configuration

Repository **Variables**:
- `AWS_REGION` — e.g. `ap-southeast-1`
- `AWS_ROLE_ARN` — IAM role trusted for this repository's GitHub OIDC subject
- `ECR_REPOSITORY` — full ECR repository name, e.g. `workshop-dev/workshop-app`
- `HELM_REPO` — `ORG/eks-helm`
- `HELM_VALUES_FILE` — `apps/workshop-app/values-dev.yaml`

Repository **Secrets**:
- `GH_PAT` — fine-grained token with Contents: read/write and Pull requests: read/write on `eks-helm` only. Prefer a GitHub App token in production.

The IAM role needs only the required ECR push permissions and a trust policy restricted to this repository and branch. ECR repository is created by Terraform; make sure the name matches `ECR_REPOSITORY`.

## Run locally

```bash
docker build -t workshop-app:local .
docker run --rm -p 8080:8080 workshop-app:local
```
