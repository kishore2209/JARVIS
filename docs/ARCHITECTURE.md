# J.A.R.V.I.S Architecture

USER / VOICE / UI
        |
AI ORCHESTRATOR
        |
+-------+------------------+
|                          |
QUANT / STRATEGY        MEMORY
|                          |
MARKET DATA             CONTEXT
|
TRADE PROPOSAL
|
RISK FIREWALL
|
APPROVAL GATE
|
EXECUTION GATEWAY
|
BROKER ADAPTER

## Separation of responsibilities
- LLM: reasoning, planning, orchestration, explanation and synthesis.
- Quant Engine: deterministic calculations.
- Data Layer: timestamps, source, normalization and freshness.
- Risk Firewall: hard safety rules.
- Broker Adapter: vendor-specific connectivity.
- Audit: decisions, inputs, outputs and approvals.

## Trading scope
The core objective is systematic analysis of the active NSE F&O universe.
A scanner/ranking layer is supporting functionality, not the core product.
