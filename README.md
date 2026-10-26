# retail-shop-app

Four demo services: `storefront`, `catalog`, `cart`, and `checkout`. Cart/checkout are stateless demo endpoints and do not process payments or persist orders.

## Run locally with Docker Desktop

The Compose setup pulls the service images published by the GitHub Actions workflow and starts the local database, cache, and queue dependencies. It builds catalog locally with a connection cleanup fix because the currently published catalog image cannot pass its MySQL readiness check:

```powershell
docker compose up -d
docker compose ps
```

Open the storefront at http://localhost:8080. The service endpoints are available at catalog `:8081`, cart `:8082`, checkout `:8083`, orders `:8084`, and api-service `:8085`. Stop the stack with `docker compose down`; the MySQL and PostgreSQL data volumes are retained.

Configure GitHub Actions repository variables:
- `HELM_REPO` — `ORG/retail-shop-helm`
- `HELM_VALUES_FILE` — `apps/retail-shop/values-dev.yaml` (optional; defaults to this path if unset)

Configure these GitHub Actions secrets:
- `DOCKERHUB_TOKEN` — Docker Hub access token with permission to push images to `tanjimuladnan`
- `GH_PAT` — fine-grained token scoped to Contents and Pull Requests on the Helm repository only. Prefer a GitHub App token for production.
