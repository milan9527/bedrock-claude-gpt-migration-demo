"""Run sequential live comparisons across all four source/target APIs."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APIS = ("converse", "invoke", "responses", "chat")
CORE = ("summary", "agent_chain", "stream")
EXTRA = ("extract", "rag", "tools", "agent_parallel", "agent_recovery",
         "thinking", "thinking_tools", "multiturn", "injection", "truncation",
         "api_unicode", "api_system", "api_history", "api_tool_error", "api_stop")


def main():
    output = ROOT / ".deploy/expanded-api-matrix"
    output.mkdir(mode=0o700, exist_ok=True)
    cases = []
    for i, source_api in enumerate(APIS):
        for j, target_api in enumerate(APIS):
            astra = (i + j) % 2 == 1
            source = ("us.anthropic.claude-fable-5-1" if astra else
                      "us.anthropic.claude-opus-4-8") if source_api in ("converse", "invoke") else (
                      "us.openai.gpt-5.6-sol" if astra else "us.openai.gpt-6-astra")
            target = "us.openai.gpt-6-astra" if astra else "us.openai.gpt-5.6-sol"
            cases.append((f"{source_api}-{target_api}", source_api, target_api, source, target, CORE))
    for name, source, target in (
        ("opus-sol", "us.anthropic.claude-opus-4-8", "us.openai.gpt-5.6-sol"),
        ("fable-astra", "us.anthropic.claude-fable-5-1", "us.openai.gpt-6-astra"),
    ):
        cases.append((f"extended-{name}", "invoke", "responses", source, target, EXTRA))
    for name, source_api, target_api, source, target, scenarios in cases:
        path = output / f"{name}.json"
        if path.exists():
            evidence = json.loads(path.read_text())
            if (len(evidence["jobs"]) == len(scenarios) and
                    all(j["job"]["status"] != "running" for j in evidence["jobs"])):
                print(f"Already recorded: {name}", flush=True)
                continue
            raise RuntimeError(f"Partial evidence at {path}; inspect before restarting")
        print(f"Running: {name}", flush=True)
        subprocess.run([sys.executable, str(ROOT / "deploy/verify_scenarios.py"),
                        "--source-api", source_api, "--target-api", target_api,
                        "--source-model", source, "--target-model", target,
                        "--adaptive", "--scenarios", *scenarios, "--output", str(path)],
                       cwd=ROOT, check=True)
    print(f"Finished; private evidence: {output}", flush=True)


if __name__ == "__main__":
    main()
