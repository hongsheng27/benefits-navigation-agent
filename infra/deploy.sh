#!/usr/bin/env bash
#
# Build the backend image, push it to ECR, and roll the ECS service onto it.
#
#   ./infra/deploy.sh
#
# Reads configuration from the repository-root `.env` (gitignored). Requires
# Docker and the AWS CLI. Run from anywhere; paths resolve against the repo.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CLUSTER="jiezhu"
SERVICE="jiezhu-backend"
REPOSITORY="jiezhu-backend"
# The task definition pins ARM64. Building amd64 here would fail at runtime with
# a bare "exec format error" that says nothing about the cause.
PLATFORM="linux/arm64"

# --- configuration --------------------------------------------------------
set -a
# shellcheck disable=SC1091
[ -f .env ] && . ./.env
set +a
unset AWS_PROFILE  # `.env` credentials must win over any stale shared profile.

: "${AWS_REGION:?set AWS_REGION in .env}"
: "${BEDROCK_MODEL_ID:?set BEDROCK_MODEL_ID in .env}"
export AWS_REGION
export BEDROCK_MODEL_ID
export DATA_STORE_BACKEND="${DATA_STORE_BACKEND:-sqlite}"

# --- who am I -------------------------------------------------------------
# This machine has more than one set of credentials. Deploying into the wrong
# account is silent until it is expensive, so print the identity every time.
CALLER=$(aws sts get-caller-identity --query Arn --output text)
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_ACCOUNT_ID
echo "identity : $CALLER"
echo "account  : $AWS_ACCOUNT_ID"
echo "region   : $AWS_REGION"

# --- what am I shipping ---------------------------------------------------
# Tag with the commit, never `latest`: "which code is running?" has to have an
# answer during a demo.
IMAGE_TAG=$(git rev-parse --short HEAD)
if [ -n "$(git status --porcelain)" ]; then
  IMAGE_TAG="${IMAGE_TAG}-dirty"
  echo "WARNING: working tree is dirty; tagging $IMAGE_TAG"
fi
export IMAGE_TAG
REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE="${REGISTRY}/${REPOSITORY}:${IMAGE_TAG}"
echo "branch   : $(git branch --show-current)"
echo "image    : $IMAGE"
echo

# --- build and push -------------------------------------------------------
docker build --platform "$PLATFORM" -t "$IMAGE" .

# Registry traffic gets reset intermittently on some venue networks while the
# AWS API endpoints stay up. Retry rather than reconfigure anything.
for attempt in 1 2 3; do
  if aws ecr get-login-password --region "$AWS_REGION" \
      | docker login --username AWS --password-stdin "$REGISTRY"; then
    break
  fi
  echo "docker login failed (attempt $attempt), retrying"
done

for attempt in 1 2 3; do
  if docker push "$IMAGE"; then break; fi
  echo "docker push failed (attempt $attempt), retrying"
done

# --- register and roll ----------------------------------------------------
RENDERED=$(mktemp)
trap 'rm -f "$RENDERED"' EXIT
envsubst < infra/ecs/task-definition.json > "$RENDERED"

REVISION=$(aws ecs register-task-definition \
  --cli-input-json "file://$RENDERED" \
  --region "$AWS_REGION" \
  --query 'taskDefinition.revision' --output text)
echo "registered task definition revision $REVISION"

# Desired count stays at 1 on purpose. Session state, the Bedrock rate limiter,
# and the RDS connection pool are all per-process; a second task breaks them.
aws ecs update-service \
  --cluster "$CLUSTER" --service "$SERVICE" \
  --task-definition "jiezhu-backend:${REVISION}" \
  --desired-count 1 \
  --region "$AWS_REGION" >/dev/null

echo "rolling the service; in-flight sessions are lost because the store is in memory"
aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE" --region "$AWS_REGION"
echo "service stable on revision $REVISION"
