# retail-shop-app

Four demo services: `storefront`, `catalog`, `cart`, and `checkout`. Cart/checkout are stateless demo endpoints and do not process payments or persist orders.

Configure GitHub Actions repository variables:
- `AWS_REGION` — e.g. `ap-southeast-1`
- `AWS_ROLE_ARN` — OIDC role ARN trusted for this repository's `main` branch
- `HELM_REPO` — `ORG/retail-shop-helm`
- `HELM_VALUES_FILE` — `apps/retail-shop/values-dev.yaml`

Secret:
- `GH_PAT` — fine-grained token scoped to Contents and Pull Requests on the Helm repository only. Prefer a GitHub App token for production.

Terraform creates ECR repos named `retail-shop-dev/storefront`, `retail-shop-dev/catalog`, `retail-shop-dev/cart`, and `retail-shop-dev/checkout`. Restrict the AWS role's ECR permissions and OIDC trust.
