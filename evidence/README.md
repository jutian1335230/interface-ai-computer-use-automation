# Evidence

`example-artifact.json` is the capability compiled from the final genuine model run. The retained timestamped directories contain:

- `discovery-live-20260927T122210961057Z`: genuine OpenAI accessibility observations, decisions, bounded locator recovery, artifact, and final screenshot.
- `replay-20260927T122253959388Z`: redacted event log, structured success result, and Playwright trace.
- `replay-20260927T122315385719Z`: redacted event log, typed `member_not_found` result, and Playwright trace.
- `interventions/`: handoff requests and control-transfer signals when the handoff demo is run.

The discovery log demonstrates that policy blocked no unsafe fallback, UI action failures were fed back into the bounded model loop, and the final compiler removed concrete member and balance values from the artifact. Runtime records are synthetic; persisted event/result JSON is redacted.