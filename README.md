# Retail Store Sample

This repository contains the storefront UI and its catalog, cart, checkout, and orders services.

## Run the application with Docker Desktop

From the repository root, build and start the complete application and its local dependencies:

```powershell
docker compose up -d --build
docker compose ps
```

Open the storefront at [http://localhost:8080](http://localhost:8080). The UI uses the local backend services for product browsing, cart updates, and demo checkout. This application is for demonstration only; do not enter real payment or personal information.

Stop the application with:

```powershell
docker compose down
```

The catalog and orders services use development-only credentials defined in their Compose files. Do not expose this local demo stack publicly or use real payment or personal information.

## Build and deploy to EKS

The [Build, Publish, and Update GitOps workflow](.github/workflows/build-publish-gitops.yml) builds the UI, catalog, cart, checkout, and orders images on pushes to `main` (or when manually dispatched). It pushes each image to Docker Hub with both a commit-SHA tag and `latest`, then packages the application Helm chart and opens a pull request against `Tanjimul-Adnan/eks-helm` at `apps/retail-shop`.

Configure these repository secrets and variables before running the workflow:

| Name | Type | Description |
| --- | --- | --- |
| `DOCKERHUB_TOKEN` | Secret | Docker Hub access token with permission to push the five image repositories. |
| `GH_PAT` | Secret | GitHub token with contents-write and pull-request-write access to the Helm GitOps repository. |
| `DOCKERHUB_USERNAME` | Variable (optional) | Docker Hub namespace; defaults to `tanjimuladnan`. |
| `HELM_REPO` | Variable (optional) | GitOps repository in `owner/repo` form; defaults to `Tanjimul-Adnan/eks-helm`. |

The workflow validates the packaged chart before opening the pull request. Argo CD deploys the update after that pull request is merged; the workflow does not deploy directly to the EKS cluster.

The retail-shop chart enables MySQL for catalog, PostgreSQL and RabbitMQ for orders, and Redis for checkout. MySQL, PostgreSQL, and RabbitMQ use persistent volume claims; the EKS cluster must have a default StorageClass (or the chart values must specify one) for those claims to bind. Database and RabbitMQ credentials are managed by their service charts.
