# Conductor on Amazon Bedrock AgentCore — deployment proof

**Runtime ARN:** `arn:aws:bedrock-agentcore:us-west-2:287977321648:runtime/conductor-Vcnj7IB5nX`
**Region:** us-west-2  **Status:** READY  **Build:** CodeBuild ARM64 → ECR `bedrock-agentcore-conductor`

## How it was deployed
- IaC: `deploy/cloudformation.yaml` (DynamoDB event log `conductor-events` + task role).
- Runtime: `conductor/agentcore_entry.py` (`BedrockAgentCoreApp`, `@app.entrypoint`),
  built and deployed with the AgentCore starter toolkit (`agentcore configure` / `agentcore deploy`).
- Container built in the cloud by CodeBuild; no local Docker.

## Invoke it
```
agentcore invoke '{"action":"state"}'
agentcore invoke '{"action":"tick","ticks":8}'
agentcore invoke '{"action":"answer","decision_id":"...","choice":"..."}'
```

## Verified result (live, in the cloud runtime)
A single `tick` of 8 against the deployed runtime:

| metric | value | meaning |
|---|---|---|
| dispatched | 8 | work sent to the team |
| verified | 5 | passed a real check, merged to base |
| claims_rejected | 3 | confident-but-wrong "done" caught before any human saw it |
| held | 22 | beyond the reviewer's attention budget, deliberately not dispatched |
| escalations -> questions | 1 -> 1 | compressed for the human |

Event log from the same invocation:
```
REJECT  Rewrite onboarding empty states: exit 1
REJECT  Migrate the onboarding events table: exit 1
MERGE   conductor/cm_... <- verified: Competitive research on three tools
MERGE   conductor/cm_... <- verified: Fix the payment webhook retry
SPEC    dec_... forked into 3 branches while waiting
```

The rejections come from deterministic verification, not from a model, so the
catch reproduces every time and does not depend on any model quota.

## Notes
- The runtime answers over IAM (SDK `InvokeAgentRuntime`), not a browsable URL.
  The clickable web UI is the always-on ASGI form (`conductor.asgi`).
- Observability (X-Ray Transaction Search) is not enabled; it needs
  `xray:UpdateTraceSegmentDestination`, which was left off the deploy user on
  purpose. CloudWatch logs for the runtime are on.
