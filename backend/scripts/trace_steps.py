import json

with open(r"C:\Users\Sumit\.gemini\antigravity\brain\3d8ba28f-2705-4521-b85c-bf9a0f9e45bc\.system_generated\logs\transcript.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        data = json.loads(line)
        idx = data.get("step_index")
        if idx and 8770 <= idx <= 8815:
            tc = data.get("tool_calls")
            if tc:
                for c in tc:
                    tname = c.get("tool_name")
                    args = c.get("arguments", {})
                    summary = args.get("toolSummary") or str(args)[:100]
                    print(f"Step {idx}: {tname} -> {summary}")
