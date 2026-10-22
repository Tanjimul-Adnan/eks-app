# retail-shop-app

Four demo services: `storefront`, `catalog`, `cart`, and `checkout`. Cart/checkout are stateless demo endpoints and do not process payments or persist orders.

Configure GitHub Actions repository variables:
- `HELM_REPO` — `ORG/retail-shop-helm`
- `HELM_VALUES_FILE` — `apps/retail-shop/values-dev.yaml` (optional; defaults to this path if unset)

Configure these GitHub Actions secrets:
- `DOCKERHUB_TOKEN` — Docker Hub access token with permission to push images to `tanjimuladnan`
- `GH_PAT` — fine-grained token scoped to Contents and Pull Requests on the Helm repository only. Prefer a GitHub App token for production.

The workflow builds and pushes `tanjimuladnan/storefront`, `tanjimuladnan/catalog`, `tanjimuladnan/cart`, and `tanjimuladnan/checkout` to Docker Hub. The Helm values file must contain an `image.repository` and `image.tag` for each service; the workflow updates those values and opens a pull request in the GitOps repository.
