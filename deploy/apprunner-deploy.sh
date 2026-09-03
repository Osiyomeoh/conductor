#!/usr/bin/env bash
# Deploy the Conductor web UI to AWS App Runner for a permanent public URL.
# Builds the React SPA, builds a linux/amd64 image, pushes it to ECR, then
# creates/updates the App Runner service via CloudFormation.
#
# Prereqs: Docker running (with buildx), AWS creds that can push to ECR and
# create the CloudFormation stack. Run from anywhere:  deploy/apprunner-deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

REGION="${AWS_REGION:-us-west-2}"
REPO="conductor-web"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
TAG="$(date +%Y%m%d-%H%M%S)"
IMAGE="${REGISTRY}/${REPO}:${TAG}"

echo "==> building the frontend"
( cd web && npm install && npm run build )

echo "==> ensuring ECR repository ${REPO}"
aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null

echo "==> logging Docker in to ECR"
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"

echo "==> building + pushing linux/amd64 image  ${IMAGE}"
docker buildx build --platform linux/amd64 -f deploy/Dockerfile \
  -t "$IMAGE" --push .

# Live agents: if a Gemini key is present (in the env or .env), run the agents
# live on Gemini. The key flows straight from .env into the service parameter;
# it is never printed or committed.
[ -f .env ] && set -a && . ./.env && set +a
PARAMS="ImageUri=${IMAGE}"
if [ -n "${GEMINI_API_KEY:-}" ]; then
  echo "==> Gemini key found: deploying with live agents (provider=gemini, model=${CONDUCTOR_GEMINI_MODEL:-gemini-3.5-flash})"
  PARAMS="$PARAMS Provider=gemini GeminiApiKey=${GEMINI_API_KEY} GeminiModel=${CONDUCTOR_GEMINI_MODEL:-gemini-3.5-flash}"
else
  echo "==> no Gemini key: deploying with the deterministic fixture planner"
fi

echo "==> deploying App Runner service (CloudFormation)"
aws cloudformation deploy \
  --template-file deploy/apprunner.yaml \
  --stack-name conductor-web \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides $PARAMS \
  --region "$REGION"

URL="$(aws cloudformation describe-stacks --stack-name conductor-web \
  --region "$REGION" --query 'Stacks[0].Outputs[?OutputKey==`ServiceUrl`].OutputValue' \
  --output text)"
echo ""
echo "==> done. Permanent public URL:"
echo "    ${URL}"
