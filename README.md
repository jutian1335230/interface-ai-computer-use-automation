# Legacy Capability Runner

A small computer-use system that lets an LLM discover a workflow once, compiles the successful run into a typed capability artifact, and replays that artifact without an LLM. The included target is an intentionally old-style member-services UI with no test IDs and server-rendered transitions.

## Setup

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m playwright install chromium
python -m pytest
```

For genuine LLM discovery, put `OPENAI_API_KEY` in the ignored `.env` file (copy `.env.example`) or set it in the shell. `OPENAI_MODEL` is optional. Never commit `.env`.

## Demo path

The one-command smoke demo starts the local application, performs explicitly labeled offline discovery, then replays both a successful lookup and a `member_not_found` business outcome:

```powershell
interface-automation demo
```

For the required real LLM-driven run, use two terminals:

```powershell
# Terminal 1
interface-automation serve
```

```powershell
# Terminal 2, with OPENAI_API_KEY already set
interface-automation discover `
  --goal "Look up member 12345 and read the current savings balance" `
  --param member_id=12345 `
  --output evidence/example-artifact.json

interface-automation replay evidence/example-artifact.json --param member_id=12345
interface-automation replay evidence/example-artifact.json --param member_id=11111
```

To watch a replay and inspect the final page for 15 seconds:

```powershell
interface-automation replay evidence/example-artifact.json `
  --param member_id=12345 --headed --keep-open-seconds 15
```

Discovery defaults to the real OpenAI planner. `--offline` is only a deterministic development smoke test and its evidence is labeled accordingly.

## Human handoff

This command pauses before submission while preserving the headed browser session:

```powershell
interface-automation replay evidence/example-artifact.json `
  --param member_id=12345 --headed --handoff-at step-4 --wait-for-human
```

The request ID appears in `evidence/interventions/`. In the open browser, the operator clicks **Find member**, then signals completion from another terminal:

```powershell
interface-automation resume REQUEST_ID --note "Submitted lookup and verified detail page"
```

Automation resumes on the same page, captures the operator's click/change events and note, extracts the output, and verifies the checkpoint.

## Commands

- `serve`: run the local training application.
- `discover`: run the observe-decide-act loop and save an artifact.
- `replay`: execute a saved artifact with no model decisions.
- `resume`: return control from a human to paused automation.
- `demo`: create reproducible offline evidence for happy and exceptional paths.

Run `interface-automation COMMAND --help` for all options. See [REPORT.md](REPORT.md) for design decisions and [evidence/README.md](evidence/README.md) for evidence provenance.
