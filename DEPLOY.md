# Deployment Setup — agentic-reach.com

> **Instructions for Claude:** When the user asks you to "execute what's in here" or "set up deployment", follow the steps in the **Claude Action Plan** section below. Do them in order, confirm each step with the user before proceeding to the next.

---

## Infrastructure Overview

- **Server:** `adm.agentic-reach.com` (Debian 13, Hetzner)
- **Reverse proxy:** Traefik v3 — handles TLS (Let's Encrypt) and subdomain routing automatically
- **Registry:** `ghcr.io` (GitHub Container Registry, free with GitHub)
- **SSH access:** `ssh uli@adm.agentic-reach.com` (key-based, no password)

### How deployment works

1. CI (GitHub Actions) builds a Docker image and pushes it to `ghcr.io/<org>/<app>:latest`
2. CI SSHes into the server as the `deploy` user using a **per-app private key**
3. The server's `authorized_keys` has a **forced command** for that key — it can only trigger a redeploy of this one app, nothing else
4. Server runs: `docker compose pull && docker compose up -d --remove-orphans`
5. Traefik detects the new container via Docker labels and routes `<app>.agentic-reach.com` to it with a fresh TLS cert

---

## Claude Action Plan

When asked to set up deployment for this repo, do the following steps in order:

### Step 1 — Determine app name and subdomain

Ask the user:
- What is the **service name**? (e.g. `myapp`) — this becomes the directory on the server and the subdomain
- What **subdomain** should it be served on? (default: `<name>.agentic-reach.com`)
- What **port** does the app listen on inside the container?

### Step 2 — Check for Dockerfile

Check if a `Dockerfile` exists in the repo root. If not, ask the user what runtime/framework the app uses and create an appropriate one.

### Step 3 — Create GitHub Actions workflow

Create `.github/workflows/deploy.yml` using the template below. Fill in:
- `SERVICE_NAME` — the service name from Step 1
- `IMAGE_NAME` — set to `${{ github.repository }}` (auto-resolves to `org/repo`)
- `CONTAINER_PORT` — the port from Step 1

```yaml
name: Build and Deploy

on:
  push:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}
  SERVICE_NAME: REPLACE_ME        # e.g. myapp
  CONTAINER_PORT: REPLACE_ME      # e.g. 3000

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout
        uses: actions/checkout@v6

      - name: Log in to ghcr.io
        uses: docker/login-action@v4
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push image
        uses: docker/build-push-action@v7
        with:
          context: .
          push: true
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest

  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest

    steps:
      - name: Deploy to server
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: echo "deploy triggered"
```

### Step 4 — Create service compose file

Tell the user: *"I need to create the service directory and docker-compose.yml on the server. I'll do this now via SSH."*

Then run (substituting values from Step 1):

```bash
ssh uli@adm.agentic-reach.com 'sudo bash -s' << 'EOF'
mkdir -p /opt/services/SERVICE_NAME
cat > /opt/services/SERVICE_NAME/docker-compose.yml << 'COMPOSE'
services:
  SERVICE_NAME:
    image: ghcr.io/ORG/REPO:latest
    restart: unless-stopped
    networks:
      - traefik-public
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.SERVICE_NAME.rule=Host(`SUBDOMAIN.agentic-reach.com`)"
      - "traefik.http.routers.SERVICE_NAME.entrypoints=websecure"
      - "traefik.http.routers.SERVICE_NAME.tls.certresolver=letsencrypt"
      - "traefik.http.services.SERVICE_NAME.loadbalancer.server.port=CONTAINER_PORT"

networks:
  traefik-public:
    external: true
COMPOSE
echo "Created /opt/services/SERVICE_NAME/docker-compose.yml"
EOF
```

Also save this compose file locally in the srvmgmt repo at `services/SERVICE_NAME/docker-compose.yml` — that repo lives at `/home/uli/projects/sit/agentic-reach/srvmgmt` on the dev machine.

### Step 5 — Generate deploy key

Tell the user to run this **on their local machine** (not on the server):

```bash
ssh-keygen -t ed25519 -C "deploy-SERVICE_NAME" -f deploy_SERVICE_NAME_key
```

This produces:
- `deploy_SERVICE_NAME_key` — private key → goes into GitHub Actions secret
- `deploy_SERVICE_NAME_key.pub` — public key → goes onto the server

### Step 6 — Register public key on server

```bash
cat deploy_SERVICE_NAME_key.pub | ssh uli@adm.agentic-reach.com 'sudo /opt/scripts/add-service-key.sh SERVICE_NAME'
```

This adds a **forced-command entry** to the deploy user's `authorized_keys` — the key can only trigger a redeploy of this specific service.

### Step 7 — Add GitHub Actions secrets

Tell the user to add these secrets in the GitHub repo under **Settings → Secrets → Actions**:

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | `adm.agentic-reach.com` |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_SSH_KEY` | Contents of `deploy_SERVICE_NAME_key` (the private key file) |

`GITHUB_TOKEN` is built-in — no need to add it manually.

### Step 8 — Verify

After the user pushes to `main`:
1. Watch the Actions tab — both jobs should go green
2. Visit `https://SUBDOMAIN.agentic-reach.com` — TLS cert issues automatically on first request
3. Check Traefik picked it up: `ssh uli@adm.agentic-reach.com 'sudo docker ps'`

### Step 9 — Clean up key files

Remind the user to delete the local private key file after adding it to GitHub:
```bash
rm deploy_SERVICE_NAME_key deploy_SERVICE_NAME_key.pub
```

---

## If the app needs environment variables

Secrets (API keys, DB passwords etc.) go in `/opt/services/SERVICE_NAME/.env` on the server — never in the compose file or the repo. Add to the compose file:

```yaml
    env_file: .env
```

Create the file on the server manually:
```bash
ssh uli@adm.agentic-reach.com 'sudo nano /opt/services/SERVICE_NAME/.env'
```

---

## Dos and Don'ts

- **Do** make the image name match `ghcr.io/${{ github.repository }}:latest`
- **Do** keep the service name consistent across: directory name, compose service name, Traefik router name, and deploy key label
- **Don't** add the deploy user to the docker group — the forced-command + sudo pattern is intentional
- **Don't** commit `.env` files or private keys to the repo
- **Don't** use `docker-compose down` in deploy — it causes downtime; `up -d` does a rolling update
