---
name: Test request (run the benchmark for me)
about: Ask a teammate with API keys to run an Asymmetry Bench config and publish it to the team site. Prefer the site's form — it prefills this for you.
title: "[Test request] <short name>"
---

<!-- Keep "[Test request]" in the title: the dashboard lists requests by that
     prefix and shows their status from this issue's state and labels.
     Easier route: https://cornelldatascience.github.io/multi-agent-coop/#request -->

**What this tests / why:**

```json
{
  "name": "<short name>",
  "test_model": "claude-sonnet-5",
  "counterparts": ["meta-llama/llama-3.1-8b-instruct", "control"],
  "tasks": ["commons", "sale", "contract", "claim"],
  "seeds": { "start": 0, "count": 10 },
  "judge_model": "claude-haiku-5-5",
  "concurrency": 4
}
```

<!-- Available tasks: commons, sale, contract, claim, knowledge, knowledge_rel.
     Keep "control" in counterparts — the matched-pair design needs it.
     Whoever runs it: run locally, then publish per runs/README.md and close
     this issue (label `running` while it runs, `declined` to decline). -->
