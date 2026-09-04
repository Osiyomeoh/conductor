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

# Secrets flow straight from .env into service parameters (an array, so values
# with special characters survive); they are never printed or committed.
[ -f .env ] && set -a && . ./.env && set +a
PARAMS=( "ImageUri=${IMAGE}" )
if [ -n "${GEMINI_API_KEY:-}" ]; then
  echo "==> Gemini key found: live agents on ${CONDUCTOR_GEMINI_MODEL:-gemini-3.5-flash}"
  PARAMS+=( "Provider=gemini" "GeminiApiKey=${GEMINI_API_KEY}" "GeminiModel=${CONDUCTOR_GEMINI_MODEL:-gemini-3.5-flash}" )
fi
if [ -n "${CONDUCTOR_SLACK_BOT_TOKEN:-}" ]; then
  echo "==> Slack configured: decisions will post to ${CONDUCTOR_SLACK_CHANNEL:-a channel}"
  PARAMS+=( "SlackBotToken=${CONDUCTOR_SLACK_BOT_TOKEN}" "SlackSigningSecret=${CONDUCTOR_SLACK_SIGNING_SECRET:-}" "SlackChannel=${CONDUCTOR_SLACK_CHANNEL:-}" )
fi
if [ -n "${CONDUCTOR_SMTP_HOST:-}" ]; then
  echo "==> Email (SMTP) configured: ${CONDUCTOR_SMTP_FROM:-}"
  PARAMS+=( "SmtpHost=${CONDUCTOR_SMTP_HOST}" "SmtpPort=${CONDUCTOR_SMTP_PORT:-465}" "SmtpUser=${CONDUCTOR_SMTP_USER:-}" "SmtpFrom=${CONDUCTOR_SMTP_FROM:-}" "SmtpPassword=${CONDUCTOR_SMTP_PASSWORD:-}" "EmailTo=${CONDUCTOR_EMAIL_TO:-}" )
fi
if [ -n "${CONDUCTOR_IMAP_HOST:-}" ]; then
  PARAMS+=( "ImapHost=${CONDUCTOR_IMAP_HOST}" "ImapUser=${CONDUCTOR_IMAP_USER:-}" "ImapPassword=${CONDUCTOR_IMAP_PASSWORD:-}" )
fi

echo "==> deploying App Runner service (CloudFormation)"
aws cloudformation deploy \
  --template-file deploy/apprunner.yaml \
  --stack-name conductor-web \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides "${PARAMS[@]}" \
  --region "$REGION"

URL="$(aws cloudformation describe-stacks --stack-name conductor-web \
  --region "$REGION" --query 'Stacks[0].Outputs[?OutputKey==`ServiceUrl`].OutputValue' \
  --output text)"
echo ""
echo "==> done. Permanent public URL:"
echo "    ${URL}"
