# Voice command center adaptation

Reviewed 2026-09-27. Reference: https://github.com/adewaskar/jarvis at
1c4016afdf86f7043efc6882ceffef84ad0d8783. Our base:
d448bc90b1fdf63510c96e2584daef286a0c3e83.

## Decision

Keep this project's Python/Gemini and deterministic market-analysis architecture.
The reference implements a React/Three.js voice interface backed by a Node bridge
and Claude Agent SDK, with local MCP tools. It is not an Indian-market analysis
engine. Replacing our backend with it would discard existing market and risk work.
Its bridge tool-name permission policy is not a substitute for our exact-plan
approval and financial validation boundaries.

Adopt the interaction idea with original lightweight CSS: a reactor that reflects
actual voice states, readable analysis cards, and an interface suitable for a
basic laptop and mobile-width browser. No upstream code/assets were copied, no
Claude subscription/dependency was added, and no MCP configuration was imported.

## Implemented in this change

- Cyan command-center theme and animated reactor in the existing Voice panel.
- Reactor follows actual recognition/processing/synthesis states; it is never a
  fake connection or market-data indicator. Reduced-motion preference is honored.
- Existing English/Telugu recognition, editable transcript and explicit Send remain.
- Mobile viewport metadata; responsive layout and visible keyboard focus.
- Backend price, EMA, RSI, VWAP, source and freshness fields are displayed.
- Backend strategy reasons, conflicting evidence and invalidation conditions are
  exposed in expandable sections. All warning/error strings are visible, including
  errors accompanying partial results. No price or trade levels are synthesized.

## Run

Follow docs/SETUP.md for backend environment and credentials. Start the backend
with `python -m jarvis_server`; in `frontend`, run `npm ci` and `npm run dev`.
Open Chat to see the reactor. Select Telugu or English, click Start Listening,
review the transcript and send. Enable Speak Responses for spoken replies.
Open Analysis for computed market output and expandable strategy evidence.
Use a microphone-capable browser on localhost, or configure HTTPS for remote use.
A phone must reach a configured backend URL; its localhost is the phone itself.

## Remaining production work

This is an interface/output adaptation, not completion of the Master SRD.
Always-on wake word, natural barge-in, authenticated remote mobile access,
50-stock scheduled scans, chart generation and email/WhatsApp delivery are not
implemented by this patch. Existing automation requires explicit ticks. LIVE
execution remains unsupported. Provider credentials, real market feeds and
speech accuracy on the user's device were not exercised in this environment.
The existing Analysis form uses a fixed token; production instrument resolution
needs separate work before relying on that form for arbitrary symbols.

## Validation

Frontend production build and full Vitest suite, including regression cases for
partial-result errors, stale-data warnings, source visibility and strategy reasons.
Browser speech is tested using adapters; these tests do not certify microphone
hardware or Telugu recognition quality.
