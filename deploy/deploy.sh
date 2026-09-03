#!/usr/bin/env bash
# One-command AgentCore + DynamoDB deploy. Run with AWS credentials that can
# create the stack and deploy to AgentCore. Bedrock must have model access;
# or set CONDUCTOR_PROVIDER=gemini + GEMINI_API_KEY in the runtime env.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> building the frontend"
( cd web && npm install && npm run build )

echo "==> provisioning DynamoDB event table + task role"
aws cloudformation deploy \
  --template-file deploy/cloudformation.yaml \
  --stack-name conductor \
  --capabilities CAPABILITY_NAMED_IAM

echo "==> deploying to AgentCore Runtime"
npm install -g @aws/agentcore
agentcore create --name Conductor --framework Strands --model-provider Bedrock \
  --dockerfile deploy/Dockerfile
agentcore deploy
agentcore status

echo "==> done. Invoke:  agentcore invoke '{\"action\":\"state\"}'"
