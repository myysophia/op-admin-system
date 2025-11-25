#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="toci-dev-01.aurora"
SSH_USER="ninesun"
IMAGE="ninesun0318/op-backend:main"

SSH_CMD="ssh ${SSH_USER}@${REMOTE_HOST}"
DEPLOY_CMD="cd op-admin-system && docker compose -f docker-compose.backend.yml pull && docker compose -f docker-compose.backend.yml up -d"
CHECK_CMD="docker ps | grep op-admin-backend"

echo "[1/5] Connecting to ${SSH_USER}@${REMOTE_HOST}"
$SSH_CMD "echo 'Connection established.'"

echo "[2/5] Reading current image digest"
OLD_DIGEST=$($SSH_CMD "docker image inspect --format='{{index .RepoDigests 0}}' ${IMAGE} 2>/dev/null || echo 'none'")
echo "当前镜像: ${OLD_DIGEST}"

echo "[3/5] Deploying backend via docker compose"
$SSH_CMD "$DEPLOY_CMD"

echo "[4/5] Reading new image digest"
NEW_DIGEST=$($SSH_CMD "docker image inspect --format='{{index .RepoDigests 0}}' ${IMAGE} 2>/dev/null || echo 'none'")
echo "更新后镜像: ${NEW_DIGEST}"

if [[ "${NEW_DIGEST}" != "${OLD_DIGEST}" ]]; then
  echo "✅ 镜像已更新"
else
  echo "⚠️ 镜像 digest 未变化，请确认是否发布了新版本"
fi

echo "[5/5] Checking running container"
$SSH_CMD "$CHECK_CMD"

echo "验证健康状况"
curl -s 'http://toci-dev-01.aurora:8001/health' -H 'accept: application/json'
echo

echo "Deployment to test environment completed."
