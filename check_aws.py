"""Preflight: can Conductor actually reach Bedrock, as the right identity?"""
import sys

from conductor.agents.base import DEFAULT_MODEL, DEFAULT_REGION, PROFILE, session

print(f"profile : {PROFILE or '(ambient)'}")
print(f"region  : {DEFAULT_REGION}")
print(f"model   : {DEFAULT_MODEL}")
try:
    s = session()
    who = s.client("sts").get_caller_identity()
    print(f"identity: {who['Arn']}")
    if "heavy-jobs" in who["Arn"]:
        print("\nREFUSING: that is the RolePilot production job user.")
        sys.exit(2)
    r = s.client("bedrock-runtime").converse(
        modelId=DEFAULT_MODEL,
        messages=[{"role": "user", "content": [{"text": "reply with the word ready"}]}])
    print(f"bedrock : {r['output']['message']['content'][0]['text'].strip()}")
    u = r.get("usage", {})
    print(f"usage   : {u.get('inputTokens')}in / {u.get('outputTokens')}out")
    print("\nready to run for real.")
except Exception as e:
    print(f"\nFAILED: {type(e).__name__}: {e}")
    sys.exit(1)
