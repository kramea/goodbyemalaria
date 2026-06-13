# 🦟 MalarIA

### A field-worker decision agent for malaria prevention

**Malaria is beatable. Timing is everything.**

It's curable, preventable, and already gone from dozens of countries. In **Mozambique** and **Malawi** it still kills every day — and on the ground the difference is doing the **right thing at the right moment**, before the mosquitoes win.

MalarIA is a WhatsApp agent that puts that judgement in a field worker's pocket: ask about your district in your own language, and get the situation *now*, the right intervention, and whether the weather will hold — in seconds.

🌍 **Website:** [dimension-privileges-loving-wallet.trycloudflare.com](https://dimension-privileges-loving-wallet.trycloudflare.com/)

> **The right tool at the wrong time saves no one.**
> Spray before the rains and it washes off. Hand out nets after the peak and the cases already happened. Timing is not a detail — it *is* the intervention.

---

## The reality

Malaria is curable and preventable — yet it remains one of the deadliest diseases on Earth, and sub-Saharan Africa carries almost the entire burden.

| | |
|---|---|
| **263M** | malaria cases worldwide in 2023 (WHO) |
| **~597K** | deaths in 2023 — mostly children under 5 |
| **~95%** | of all cases & deaths are in the WHO African Region |
| **10.2M** | estimated cases/yr in **Mozambique** — 295 per 1,000 at risk (WHO GHO, 2024) |
| **6.4M** | estimated cases/yr in **Malawi** — 295 per 1,000 at risk (WHO GHO, 2024) |
| **4 in 5** | malaria deaths in Africa are children under five |

## The front line

**The most important soldier against malaria is the field worker.** No lab, no policy, no app stops a single case on its own. Prevention happens when a field worker reaches a village, reads the ground, and acts — spraying a wall, treating a pool of water, hanging a net — at exactly the moment it counts.

Every one of those actions only works in a narrow window. Get there in time and a village is protected. Arrive late — after the rains, after the hatch, after the peak — and the very same effort is wasted. **MalarIA exists to make sure the field worker always knows the window.**

---

## What it does — three simple jobs

1. **Speaks their language.** Auto-detects the language of the very first message and replies entirely in it — then stays in that language for the whole conversation. No menus, no English-only barrier.
2. **Answers fast, by horizon.** Assesses the question and comes back with options grouped by timeline — ⚡ *immediate* (hours–days), 📅 *month ahead* (weeks), 🌧️ *season ahead* (months).
3. **Reasons over live, local conditions.** "I want to spray tomorrow — will it rain there?" "How's the situation in Maputo?" It pulls the live weather, flood signal, and outbreak status for that exact area before it advises.

### Languages

| | Example |
|---|---|
| 🇲🇿 **Português** | *"Qual é a situação da malária em Beira?"* |
| 🇲🇼 **Chichewa** | *"Kodi udzudzu uli bwanji ku Zomba?"* (uses local terms — *malungo*, *udzudzu*) |
| 🌍 **English** | *"How is the situation in Maputo?"* |
| 🇫🇷 **Français** | *"Quelle est la situation du paludisme ?"* |

It judges language by the words written — not the country. The right advice means nothing if the worker can't read it.

### The toolbox — many interventions, each with its moment

| ⚡ Immediate · hours–days | 📅 Month ahead · weeks | 🌧️ Season ahead · months |
|---|---|---|
| Larviciding (Bti) | ITN / LLIN nets (dual-active) | Annual IRS campaign |
| Emergency IRS | Eave tubes | Resistance monitoring |
| Larval source management | Chemoprevention (SMC, IPTp) | Vaccine (RTS,S / R21) |
| Spatial repellents | House screening | Housing & livestock measures |

### Urgency cascade

The agent prioritises by what's happening *right now* in the area:

- **Active outbreak** → focus on stopping transmission immediately.
- **Active flooding** → people first, then de-flood / larvicide new standing water, watch for a case surge.
- **A season ahead** → preventative campaign planning.

---

## How it works

```
WhatsApp ──Twilio webhook──▶ FastAPI (/whatsapp)
                                  │  instant "typing…" indicator,
                                  │  reply pushed async so nobody waits
                                  ▼
                       service.handle_message(phone, msg)
                                  │  load per-phone session memory
                                  │  (language + area locked for continuity)
                                  ▼
        ┌──────────────── ROUTER (Claude, structured output) ───────────┐
        │  → language · intent · intervention · timeline · needs_weather │
        └────────────────────────────┬──────────────────────────────────┘
                                      ▼
        ┌──────── INTERVENTION SPECIALIST (1 of 15 playbooks) ───────────┐
        │  given: curated district data + live signals + urgency directive
        └────────────────────────────┬──────────────────────────────────┘
                                      ▼
            reply in the worker's language  (+ choropleth map on first / closing turn)
```

**Live data, fetched per question:**

| Source | What it gives |
|---|---|
| **Open-Meteo** forecast API | will it rain where they want to spray |
| **GloFAS / Open-Meteo** flood API | river discharge — is the area flooding now |
| **WHO Global Health Observatory** | national malaria burden (cached) |
| **Curated `regions.json`** | per-district status, season, resistance, last intervention |
| **geoBoundaries** admin polygons | choropleth maps shaded by alert level |

Built with **Claude** — a fast router model for classification and structured output, and a specialist model for the field-grade reasoning in each reply.

➡️ **Live site & full technical write-up:** [the landing page](https://dimension-privileges-loving-wallet.trycloudflare.com/) and the ["How it works" page](https://dimension-privileges-loving-wallet.trycloudflare.com/tech).

---

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # then edit .env and add ANTHROPIC_API_KEY
```

Only `ANTHROPIC_API_KEY` is required to run the agent. Twilio vars are needed only for live WhatsApp delivery.

### Run locally (no WhatsApp needed)

```bash
# one-shot
python3 cli.py "As chuvas começaram cedo em Gaza. Temos muita água parada. O que fazemos agora?"

# interactive REPL (keeps session memory for the phone id)
python3 cli.py --phone +258840000000

# JSON endpoint
uvicorn webhook:app --port 8000
curl -s localhost:8000/message -H 'content-type: application/json' \
  -d '{"phone":"test:+1","message":"How is the situation in Maputo?"}' | python3 -m json.tool
```

### Connect WhatsApp (Twilio sandbox — free, instant)

1. `.env`: set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` (console.twilio.com → Account Info) and `TWILIO_WHATSAPP_FROM` (the sandbox number, prefixed `whatsapp:`).
2. Console → **Messaging → Try it out → Send a WhatsApp message**. Send the shown `join <code>` from your phone to opt in.
3. Expose the server (`uvicorn webhook:app --port 8000`, then a tunnel such as `cloudflared tunnel --url http://localhost:8000`).
4. In **Sandbox settings → When a message comes in**, set `https://<your-host>/whatsapp` (HTTP POST).
5. Message the sandbox number — MalarIA replies in the sender's language.

> The free sandbox caps outbound at **50 messages/day** (resets at 00:00 UTC). A production WhatsApp Business sender removes the cap. Set `TWILIO_VALIDATE_SIGNATURE=1` in production.

### Deploy

Any container/PaaS works: `uvicorn webhook:app --host 0.0.0.0 --port $PORT`. Set the env vars and point the Twilio webhook at `https://<your-app>/whatsapp`. Mount a volume or set `MALARIA_SESSION_DIR` to persist session memory across restarts.

---

## Project layout

| Path | Purpose |
|---|---|
| `malaria/agents.py` | Router + intervention specialist (streaming; structured router output) |
| `malaria/service.py` | Orchestrates a turn: route → resolve area → live data → specialist → memory |
| `malaria/prompts.py` | Router prompt, 15 intervention playbooks, urgency directives |
| `malaria/data.py` | Loads `knowledge/regions.json`; region/country resolution & status |
| `malaria/weather.py` · `flood.py` · `who.py` | Live data adapters |
| `malaria/choropleth.py` · `webmap.py` | Alert-shaded maps (PNG + Leaflet) |
| `malaria/memory.py` | Per-phone JSON session memory (language + area locked) |
| `malaria/landing.py` · `tech.py` | Public landing page and technical write-up |
| `webhook.py` | FastAPI app — WhatsApp webhook, pages, map endpoints |
| `knowledge/regions.json` | Sub-national malaria decision dataset |
| `cli.py` / `run_demo.py` | Local REPL and demo harness |

To add a region, add an entry to `knowledge/regions.json` — no code change needed.

---

## It's beatable — proven

Over **40 countries and territories** have been certified malaria-free by the WHO — China, El Salvador, Algeria, Argentina, Cabo Verde, Egypt, and more. The tools work. The science is settled. What's left is execution on the ground, season after season — by field workers.

**Elimination isn't a single act — it's the right intervention, in the right place, at the right time, every time.** That's the problem MalarIA helps solve.

---

## Team

Built for **Goodbye Malaria**.

- **Kalai Ramea**
- **Mike Mpanya**
- **Sherwin Charles**

---

*Sources: WHO World Malaria Report 2024; WHO Global Health Observatory, 2024 (Mozambique & Malawi national estimates); WHO list of malaria-free certified countries. Figures are approximate and for demonstration; validate against live national surveillance before operational use.*
