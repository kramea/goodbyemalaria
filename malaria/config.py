"""Central configuration. Reads from environment (and .env if python-dotenv is present)."""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv optional at runtime
    pass

ROOT = Path(__file__).resolve().parent.parent

# --- Models (adaptive: cheapest model that fits each job) ---
# Router: fast classifier (language + intent + intervention + needs_weather) -> Haiku.
ROUTER_MODEL = os.getenv("MALARIA_ROUTER_MODEL", "claude-haiku-4-5")
# Specialist: the intervention expert that writes the reply -> Sonnet.
SPECIALIST_MODEL = os.getenv("MALARIA_SPECIALIST_MODEL", "claude-sonnet-4-6")
# Advisor: legacy single-call conversational agent (fallback path).
ADVISOR_MODEL = os.getenv("MALARIA_ADVISOR_MODEL", "claude-sonnet-4-6")
# Acknowledger: instant, language-aware holding reply -> Haiku (fast/cheap).
ACK_MODEL = os.getenv("MALARIA_ACK_MODEL", "claude-haiku-4-5")
# Navigator + adversarial reasoning -> Sonnet (fast + capable) by default.
NAVIGATOR_MODEL = os.getenv("MALARIA_NAVIGATOR_MODEL", "claude-sonnet-4-6")
ADVERSARIAL_MODEL = os.getenv("MALARIA_ADVERSARIAL_MODEL", "claude-sonnet-4-6")
# Verifier: constrained rubric scoring -> Haiku (structured output, fast).
VERIFIER_MODEL = os.getenv("MALARIA_VERIFIER_MODEL", "claude-haiku-4-5")
# Escalation: used for the final navigator fix only if the rubric still fails
# after the fast model — Opus earns its cost only on genuinely hard cases.
ESCALATION_MODEL = os.getenv("MALARIA_ESCALATION_MODEL", "claude-opus-4-8")

# --- API client resilience ---
# Per-request timeout (seconds): a healthy call is ~5-15s, so 40s catches a hung
# socket without cutting off a slow-but-live response. The SDK default is 600s.
REQUEST_TIMEOUT = float(os.getenv("MALARIA_REQUEST_TIMEOUT", "40"))
# Retries on timeout/connection errors (each on a fresh connection).
MAX_RETRIES = int(os.getenv("MALARIA_MAX_RETRIES", "3"))

# --- Orchestration ---
MAX_ROUNDS = int(os.getenv("MALARIA_MAX_ROUNDS", "3"))
RUBRIC_THRESHOLD = int(os.getenv("MALARIA_RUBRIC_THRESHOLD", "7"))
# Reasoning effort for the Opus agents. Low keeps WhatsApp replies fast
# (latency-sensitive); raise to "medium"/"high" for max rigor in batch/demo use.
EFFORT = os.getenv("MALARIA_EFFORT", "low")

# --- Twilio ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
TWILIO_VALIDATE_SIGNATURE = os.getenv("TWILIO_VALIDATE_SIGNATURE", "0") == "1"

# --- Storage ---
SESSION_DIR = Path(os.getenv("MALARIA_SESSION_DIR", str(ROOT / "sessions")))
KNOWLEDGE_FILE = ROOT / "knowledge" / "regions.json"
MAPS_DIR = Path(os.getenv("MALARIA_MAPS_DIR", str(ROOT / "maps_out")))

# --- Maps on WhatsApp ---
# Public base URL used to build absolute map-image / map-page links (Twilio fetches
# these, and the web chat embeds them). e.g. https://<host>  (no trailing slash).
# Precedence: explicit MALARIA_PUBLIC_BASE_URL > Railway's injected public domain.
PUBLIC_BASE_URL = os.getenv("MALARIA_PUBLIC_BASE_URL", "").rstrip("/")
if not PUBLIC_BASE_URL and os.getenv("RAILWAY_PUBLIC_DOMAIN"):
    PUBLIC_BASE_URL = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN').rstrip('/')}"
# Toggle attaching a map image to WhatsApp replies.
SEND_MAPS = os.getenv("MALARIA_SEND_MAPS", "1") == "1"
