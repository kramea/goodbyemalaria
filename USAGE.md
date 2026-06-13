# MalarIA — Run & Deploy Guide

A WhatsApp-based agentic malaria-prevention decision agent for Goodbye Malaria
field workers in Mozambique and Malawi. See `README.md` for the full build brief.

## Architecture

```
WhatsApp ──Twilio webhook──▶ FastAPI (/whatsapp)
                                  │
                                  ▼
                         service.handle_message(phone, msg)
                                  │  load per-phone JSON memory
                                  ▼
        ┌─────────────── orchestrator.run_pipeline ───────────────┐
        │  NAVIGATOR (Opus 4.8, adaptive thinking)                │
        │     ↓ generates recommendation                          │
        │  ADVERSARIAL (Opus 4.8, fresh context) → APPROVED/CHALLENGE
        │     ↓ if CHALLENGE: navigator revises                   │
        │  VERIFIER (Sonnet 4.6, structured 8-pt rubric score)    │
        │     ↓ if score < 7: navigator fixes; repeat ≤ 3 rounds  │
        └──────────────────────────────────────────────────────────┘
                                  │  save memory
                                  ▼
                         reply in worker's language
```

Data layer: `knowledge/regions.json` — sub-national incidence / rainfall / season
/ last-intervention / resistance signals for the named regions (synthesized from
WHO WMR 2025, MAP, CHIRPS, PMI/Goodbye Malaria records). The full block is given to
the navigator so it extracts the region and reasons across signals itself.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env          # then edit .env and add ANTHROPIC_API_KEY
```

Only `ANTHROPIC_API_KEY` is required to run the agent. Twilio vars are needed
only for live WhatsApp delivery.

## Run locally (no WhatsApp needed)

```bash
# one-shot, with the agent trace
python3 cli.py --trace "As chuvas começaram cedo em Gaza. Temos muita água parada. O que fazemos agora?"

# interactive REPL (keeps session memory for the phone id)
python3 cli.py --phone +258840000000

# all four demo scenarios + session-memory follow-up
python3 run_demo.py
```

JSON test endpoint (no Twilio):

```bash
uvicorn webhook:app --port 8000
curl -s localhost:8000/message -H 'content-type: application/json' \
  -d '{"phone":"test:+1","message":"We are in Zomba Malawi. Season starts in 6 weeks. What should we prepare?"}' | python3 -m json.tool
```

## Connect WhatsApp (Twilio sandbox — free, instant)

1. `.env`: set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` (from console.twilio.com
   dashboard → Account Info), and `TWILIO_WHATSAPP_FROM` (the sandbox number,
   prefixed `whatsapp:`).
2. Console → Messaging → Try it out → Send a WhatsApp message. Send the shown
   `join <code>` from your phone to opt in.
3. Run the server and expose it:
   ```bash
   uvicorn webhook:app --port 8000      # terminal 1
   ngrok http 8000                       # terminal 2
   ```
4. In the sandbox settings, set **When a message comes in** to
   `https://<ngrok-host>/whatsapp` (HTTP POST).
5. Message the sandbox number — MalarIA replies in the sender's language.
6. (Prod) set `TWILIO_VALIDATE_SIGNATURE=1` to verify inbound signatures.

## Deploy to a live URL

Any container/PaaS works. The process is:
`uvicorn webhook:app --host 0.0.0.0 --port $PORT`.

- **Render / Railway / Fly.io**: push the repo, set the start command above, set
  env vars (`ANTHROPIC_API_KEY`, Twilio vars), and point the Twilio webhook at
  `https://<your-app>/whatsapp`.
- Mount a persistent volume (or set `MALARIA_SESSION_DIR`) if you want session
  memory to survive restarts. For the hackathon the local `./sessions` dir is fine.

## Files

| Path | Purpose |
|---|---|
| `malaria/prompts.py` | Three agent system prompts + taxonomy + rubric + language rules |
| `malaria/data.py` | Loads `knowledge/regions.json`, formats the data-signal block |
| `malaria/agents.py` | Navigator / Adversarial / Verifier (Verifier uses structured output) |
| `malaria/orchestrator.py` | The generate→challenge→revise→score→fix loop |
| `malaria/memory.py` | Per-phone JSON session memory |
| `malaria/service.py` | load memory → run pipeline → save memory |
| `webhook.py` | FastAPI + Twilio WhatsApp webhook |
| `cli.py` / `run_demo.py` | Local REPL and four-scenario harness |
| `knowledge/regions.json` | Sub-national malaria decision dataset |

## Tuning

All via `.env`: model choices, `MALARIA_MAX_ROUNDS`, `MALARIA_RUBRIC_THRESHOLD`.
To add a region, add an entry to `knowledge/regions.json` — no code change needed.
