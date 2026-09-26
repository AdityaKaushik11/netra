#!/bin/sh
# Generates .env with strong random secrets for local use.
set -e
cd "$(dirname "$0")/.."
if [ -f .env ]; then echo ".env already exists; delete it first to regenerate"; exit 0; fi
rnd() { openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c "${1:-24}"; }
FERNET=$(openssl rand -base64 32 | tr '+/' '-_')
sed \
  -e "s|^MYSQL_PASSWORD=.*|MYSQL_PASSWORD=$(rnd)|" \
  -e "s|^MYSQL_ROOT_PASSWORD=.*|MYSQL_ROOT_PASSWORD=$(rnd)|" \
  -e "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=$(rnd)|" \
  -e "s|^JWT_SECRET=.*|JWT_SECRET=$(rnd 48)|" \
  -e "s|^CREDENTIALS_KEY=.*|CREDENTIALS_KEY=$FERNET|" \
  -e "s|^GATEWAY_API_SECRET=.*|GATEWAY_API_SECRET=$(rnd 32)|" \
  -e "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=Admin@$(rnd 8)|" \
  -e "s|^OPERATOR_PASSWORD=.*|OPERATOR_PASSWORD=Operator@$(rnd 8)|" \
  -e "s|^VIEWER_PASSWORD=.*|VIEWER_PASSWORD=Viewer@$(rnd 8)|" \
  -e "s|^SEED_API_KEY=.*|SEED_API_KEY=ntr_$(rnd 40)|" \
  -e "s|^CAMSIM_PASSWORD=.*|CAMSIM_PASSWORD=$(rnd 16)|" \
  -e "s|^ONVIF_PASSWORD=.*|ONVIF_PASSWORD=$(rnd 16)|" \
  -e "s|^VENDOR_API_KEY=.*|VENDOR_API_KEY=$(rnd 32)|" \
  .env.example > .env
chmod 600 .env
echo "Generated .env. Demo logins:"
grep -E '^(ADMIN|OPERATOR|VIEWER)_PASSWORD' .env
