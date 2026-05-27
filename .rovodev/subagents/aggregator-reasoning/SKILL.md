---
key: aggregator-reasoning
name: Aggregator Reasoning Polish (OPTIONAL)
version: 0.1.0
status: PLACEHOLDER — disabled by default
---

# Aggregator Reasoning Polish (OPTIONAL)

The aggregator score is **always deterministic Python** (`w_ta * TA + w_fa * FA`).
This skill is invoked **only** when `AGGREGATOR_USE_LLM_REASONING=true` — purely to rewrite the templated reasoning into something more human-readable.

## Inputs

```json
{
  "symbol": "RELIANCE",
  "combined_score": 72.0,
  "combined_signal": "BUY",
  "ta": { "score": 64.0, "signal": "HOLD", "reasoning": "..." },
  "fa": { "score": 78.0, "signal": "BUY",  "reasoning": "..." },
  "weights":    { "technical": 0.4, "fundamental": 0.6 },
  "thresholds": { "buy": 70, "sell": 40 }
}
```

## Output contract

You only return the polished reasoning string. The orchestrator does NOT change the score.

```json
{
  "stock": "RELIANCE",
  "agent": "aggregator",
  "score": 72.0,
  "signal": "BUY",
  "confidence": 0.7,
  "reasoning": "Above BUY threshold (70). Strong fundamentals (FA=78) outweigh neutral technicals.",
  "signals_used": [],
  "data_freshness": null
}
```
