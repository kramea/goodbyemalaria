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
# Per-request timeout (seconds). With streaming this is the gap BETWEEN chunks,
# so a healthy call never approaches it; we keep it low so a STALE/half-open
# connection (silently dropped after an idle gap) is caught fast and retried on a
# fresh connection — instead of hanging ~40s. The SDK default is 600s.
REQUEST_TIMEOUT = float(os.getenv("MALARIA_REQUEST_TIMEOUT", "20"))
# Time to establish a new TCP/TLS connection before giving up (seconds).
CONNECT_TIMEOUT = float(os.getenv("MALARIA_CONNECT_TIMEOUT", "8"))
# Close idle pooled connections after this many seconds so we never REUSE one the
# network has silently dropped (the root cause of the ~50s stalls). A fresh
# connect costs ~0.2s, so recycling aggressively is cheap insurance.
KEEPALIVE_EXPIRY = float(os.getenv("MALARIA_KEEPALIVE_EXPIRY", "15"))
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

# --- Enriched-data / adversarial architecture ---
# DEMO_MODE: stream every agent's reasoning step to the chat and run the full
# adversarial loop even when a pre-reasoned decision exists (for presentation).
# Off => production behaviour: skip adversarial when pre-reasoned, self-heal only
# on fetch failure, stream only the final reply.
DEMO_MODE = os.getenv("MALARIA_DEMO_MODE", "0") == "1"

# Model for the auxiliary reasoning agents (self-healing, devil's advocate,
# field realism, orchestrator). Sonnet by default — capable but fast.
REVIEW_MODEL = os.getenv("MALARIA_REVIEW_MODEL", "claude-sonnet-4-6")

# Live-data fetch budget (seconds) for the parallel fetcher pool. Anything slower
# is treated as MISSING and handed to the self-healing layer (keeps turns fast).
FETCH_TIMEOUT = float(os.getenv("MALARIA_FETCH_TIMEOUT", "6"))

# Cache TTLs (seconds).
RELIEFWEB_TTL = int(os.getenv("MALARIA_RELIEFWEB_TTL", str(6 * 3600)))      # 6h
HISTORICAL_TTL = int(os.getenv("MALARIA_HISTORICAL_TTL", str(6 * 3600)))    # 6h
DHIS2_TTL = int(os.getenv("MALARIA_DHIS2_TTL", str(6 * 3600)))             # 6h
PMI_TTL = int(os.getenv("MALARIA_PMI_TTL", str(7 * 24 * 3600)))           # 7d

# DHIS2 demo instance (replace play.dhis2.org with the national HMIS for prod).
DHIS2_BASE = os.getenv("MALARIA_DHIS2_BASE", "https://play.dhis2.org/api")
DHIS2_USER = os.getenv("MALARIA_DHIS2_USER", "admin")
DHIS2_PASS = os.getenv("MALARIA_DHIS2_PASS", "district")

# Pre-reasoned (offline-trained) decisions: validity window before re-training.
PRE_REASONED_MAX_AGE_DAYS = int(os.getenv("MALARIA_PRE_REASONED_MAX_AGE_DAYS", "7"))
PRE_REASONED_FILE = ROOT / "knowledge" / "regions_pretrained.json"

# --- Maps on WhatsApp ---
# Public base URL used to build absolute map-image / map-page links (Twilio fetches
# these, and the web chat embeds them). e.g. https://<host>  (no trailing slash).
# Precedence: explicit MALARIA_PUBLIC_BASE_URL > Railway's injected public domain.
PUBLIC_BASE_URL = os.getenv("MALARIA_PUBLIC_BASE_URL", "").rstrip("/")
if not PUBLIC_BASE_URL and os.getenv("RAILWAY_PUBLIC_DOMAIN"):
    PUBLIC_BASE_URL = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN').rstrip('/')}"
# Toggle attaching a map image to WhatsApp replies.
SEND_MAPS = os.getenv("MALARIA_SEND_MAPS", "1") == "1"
