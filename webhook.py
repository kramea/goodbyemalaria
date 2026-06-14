"""FastAPI webhook for Twilio WhatsApp.

Run locally:
    uvicorn webhook:app --reload --port 8000
Expose for Twilio (sandbox):
    cloudflared tunnel --url http://localhost:8000      # or: ngrok http 8000
Set MALARIA_PUBLIC_BASE_URL in .env to that public https URL (needed so Twilio
can fetch generated map images), then point the Twilio sandbox
"WHEN A MESSAGE COMES IN" webhook at:
    https://<public-host>/whatsapp   (HTTP POST)

Endpoints:
    GET  /              -> health/info
    GET  /healthz       -> liveness probe
    POST /whatsapp      -> Twilio inbound (text OR shared location); returns TwiML
    POST /message       -> JSON test endpoint: {"phone","message"} (+optional lat/lon)
    GET  /map/{region}  -> preview a region's thematic risk map in the browser
    /maps/<file>.png    -> static map images (served for Twilio media)
"""

import base64
import json
import logging
import queue
import threading
import urllib.parse
import urllib.request
from typing import Optional, Tuple
from xml.sax.saxutils import escape

from fastapi import FastAPI, Form, Query, Request, Response
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse, StreamingResponse)
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from malaria import agents, chat, choropleth, config, data, landing, maps, memory, tech, webmap
from malaria.service import handle_message

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("malaria.webhook")

app = FastAPI(title="MalarIA", description="Malaria prevention decision agent (WhatsApp)")

# Serve generated map images so Twilio (and browsers) can fetch them.
config.MAPS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/maps", StaticFiles(directory=str(config.MAPS_DIR)), name="maps")

# Serve static assets (landing-page photos, etc.).
_ASSETS_DIR = config.ROOT / "assets"
_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")


def _prewarm() -> None:
    """Warm matplotlib's font cache with ONE render at boot.

    The expensive one-time cost on a fresh container (e.g. Railway) is matplotlib
    building its font cache — that's what makes the first map render eat 5-10s.
    A single render pays it off-band. We deliberately render only ONE region (not
    all of them): on a small shared-CPU container, rendering every map at boot
    would steal CPU from the user's first request. Remaining regions render
    lazily on demand and are cached after first use. Best-effort.
    """
    try:
        for key in data.regions():
            rec = data.region_record(key)
            country = (rec or {}).get("country")
            if country:
                choropleth.render_choropleth(country, key)
                log.info("Map pre-warm done (font cache warm via %s).", key)
                return
    except Exception:
        log.warning("Map pre-warm skipped", exc_info=True)


def _warm() -> None:
    agents.warm_connection()   # open an API socket so the first message is fast
    _prewarm()                 # warm matplotlib's font cache


@app.on_event("startup")
def _on_startup() -> None:
    # Run in the background so the server starts accepting traffic immediately.
    threading.Thread(target=_warm, daemon=True).start()

# Instant holding reply, sent the moment a message arrives (in the worker's
# detected language) while the specialist answer is prepared on a background
# thread. Keeps the worker engaged and sidesteps Twilio's ~15s webhook timeout.
# First contact = a brief greeting; follow-ups = a minimal "one moment" with NO
# greeting (so we never re-introduce mid-conversation).
_ACK_GREETING = {
    "English":    "🦟 *MalarIA*\nGot your message{area} — pulling the latest data. One moment…",
    "Portuguese": "🦟 *MalarIA*\nRecebi a sua mensagem{area} — a reunir os dados mais recentes. Um momento…",
    "French":     "🦟 *MalarIA*\nMessage bien reçu{area} — je rassemble les dernières données. Un instant…",
    "Chichewa":   "🦟 *MalarIA*\nNdalandira uthenga wanu{area} — ndikusonkhanitsa deta yaposachedwa. Dikirani pang'ono…",
}
_ACK_FOLLOWUP = {
    "English":    "⏳ One moment — checking that for you…",
    "Portuguese": "⏳ Um momento — a verificar isso para si…",
    "French":     "⏳ Un instant — je vérifie cela pour vous…",
    "Chichewa":   "⏳ Dikirani pang'ono — ndikuyang'ana…",
}
_ACK_AREA_PREP = {"English": " about ", "Portuguese": " sobre ", "French": " concernant ", "Chichewa": " za "}

# Static multilingual fallback if we can't detect the language fast enough.
_ACK_FALLBACK = (
    "🦟 *MalarIA*\n"
    "Got it — gathering the latest data for your area. One moment…\n"
    "Recebido — a reunir os dados mais recentes. Um momento…\n"
    "Ndalandira — ndikusonkhanitsa deta. Dikirani pang'ono…"
)


def _instant_ack(language: str, area: Optional[str], first_contact: bool) -> str:
    if not first_contact:
        return _ACK_FOLLOWUP.get(language, "⏳ One moment…")
    tpl = _ACK_GREETING.get(language)
    if not tpl:
        return _ACK_FALLBACK
    area_str = (_ACK_AREA_PREP.get(language, " ") + area.replace("_", " ").title()) if area else ""
    return tpl.format(area=area_str)


# Default location-only prompt per region language (used when a worker shares a
# GPS pin with no accompanying text).
_LOCATION_PROMPT = {
    "Portuguese": "Partilhei a minha localização atual. Qual é a recomendação de prevenção da malária para esta zona agora?",
    "English": "I've shared my current location. What's the malaria prevention recommendation for this area now?",
    "Chichewa": "Ndatumiza malo amene ndili. Kodi malangizo opewa malungo pa dera lino ndi otani panopa?",
    "French": "J'ai partagé ma position actuelle. Quelle est la recommandation de prévention du paludisme pour cette zone maintenant?",
}


def _twiml(message: str, media_url: Optional[str] = None) -> str:
    media = f"<Media>{escape(media_url)}</Media>" if media_url else ""
    return ("<?xml version='1.0' encoding='UTF-8'?>"
            f"<Response><Message><Body>{escape(message)}</Body>{media}</Message></Response>")


def _twiml_empty() -> str:
    """No immediate reply bubble — we show a typing indicator and push the answer."""
    return "<?xml version='1.0' encoding='UTF-8'?><Response></Response>"


def send_typing(message_sid: str) -> bool:
    """Show a WhatsApp 'typing…' indicator for the inbound message (Twilio beta).

    Twilio marks the message read and animates typing until we send the real reply
    (or 25s elapses). Best-effort: returns False (and is harmless) if unsupported,
    e.g. on some sandbox numbers.
    """
    if not (message_sid and _outbound_configured()):
        return False
    try:
        form = urllib.parse.urlencode({"messageId": message_sid, "channel": "whatsapp"}).encode()
        auth = base64.b64encode(
            f"{config.TWILIO_ACCOUNT_SID}:{config.TWILIO_AUTH_TOKEN}".encode()).decode()
        req = urllib.request.Request(
            "https://messaging.twilio.com/v2/Indicators/Typing.json",
            data=form, headers={"Authorization": f"Basic {auth}"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status < 300
    except Exception as e:
        log.info("Typing indicator unavailable (%s)", e)
        return False


@app.get("/", response_class=HTMLResponse)
def root():
    """Public landing page."""
    return HTMLResponse(landing.render_landing(
        public_base_url=config.PUBLIC_BASE_URL,
        whatsapp_number=config.TWILIO_WHATSAPP_FROM.replace("whatsapp:", "") or "+1 415 523 8886",
    ))


@app.get("/tech", response_class=HTMLResponse)
def tech_page():
    """Technical 'how it works' sub-page."""
    return HTMLResponse(tech.render_tech(public_base_url=config.PUBLIC_BASE_URL))


@app.get("/chat", response_class=HTMLResponse)
def chat_page():
    """WhatsApp-style web chat — same agent as WhatsApp, via the /message endpoint."""
    return HTMLResponse(chat.render_chat(public_base_url=config.PUBLIC_BASE_URL,
                                         demo_mode=config.DEMO_MODE))


@app.get("/coming-soon", response_class=HTMLResponse)
def coming_soon_page():
    """Placeholder for the WhatsApp line (not yet live); points to the web chat."""
    return HTMLResponse(landing.render_coming_soon())


@app.get("/info")
def info():
    return {
        "service": "MalarIA",
        "purpose": "Malaria prevention conversational agent for Goodbye Malaria field workers",
        "advisor_model": config.ADVISOR_MODEL,
        "maps_enabled": config.SEND_MAPS,
        "public_base_url": config.PUBLIC_BASE_URL or "(unset — maps won't attach to WhatsApp)",
        "endpoints": {
            "whatsapp_webhook": "POST /whatsapp",
            "json_test": "POST /message",
            "map_preview": "GET /map/{region}",
        },
        "regions": list(data.regions().keys()),
    }


@app.get("/healthz")
def healthz():
    return {"ok": True}


def _validate_twilio(request: Request, params: dict) -> bool:
    if not config.TWILIO_VALIDATE_SIGNATURE:
        return True
    try:
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
        signature = request.headers.get("X-Twilio-Signature", "")
        return validator.validate(str(request.url), params, signature)
    except Exception as e:  # pragma: no cover
        log.warning("Twilio signature validation error: %s", e)
        return False


def _outbound_configured() -> bool:
    return bool(config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN)


def _app_link_for(region_key: str, pin: Optional[Tuple[float, float]]) -> Optional[str]:
    """Public URL of the interactive Leaflet map page for this region."""
    if not (config.PUBLIC_BASE_URL and region_key):
        return None
    url = f"{config.PUBLIC_BASE_URL}/app/{region_key}"
    if pin:
        url += f"?lat={pin[0]}&lon={pin[1]}"
    return url


def _media_url_for(region_key: str, pin: Optional[Tuple[float, float]]) -> Optional[str]:
    """Render the alert-level choropleth for the region's country and return its URL."""
    if not (config.SEND_MAPS and config.PUBLIC_BASE_URL and region_key):
        return None
    try:
        rec = data.region_record(region_key)
        country = rec["country"] if rec else None
        if not country:
            return None
        path = choropleth.render_choropleth(country, region_key)
        if path:
            return f"{config.PUBLIC_BASE_URL}/maps/{path.name}"
    except Exception:  # pragma: no cover
        log.exception("Choropleth render failed for %s", region_key)
    return None


def build_reply(phone: str, message: str, pin: Optional[Tuple[float, float]] = None,
                pin_region: Optional[str] = None,
                precomputed_route: "Optional[agents.Route]" = None,
                on_notice: "Optional[callable]" = None,
                ) -> Tuple[str, Optional[str], Optional[str]]:
    """One specialist turn for this worker + attach the area's map.

    on_notice (optional) is called with a short "pulling live data…" line when the
    turn goes to fetch a live signal — used to push a holding WhatsApp message.

    Returns (reply_text, media_url_or_None, region_key_or_None).
    """
    result = handle_message(phone, message, pin=pin, pin_region=pin_region,
                            precomputed_route=precomputed_route, on_notice=on_notice)
    reply = result.text
    region_key = result.region_key

    # Map only on the first message and a closing message (service sets show_map),
    # and only when SEND_MAPS is on. Disabled => text-only replies everywhere
    # (web chat and WhatsApp) with no PNG attachment and no interactive-map link.
    media_url = None
    if config.SEND_MAPS and region_key and result.show_map:
        media_url = _media_url_for(region_key, pin)
        app_url = _app_link_for(region_key, pin)
        if app_url:
            label = webmap.link_label(region_key, result.language or "")
            reply = f"{reply}\n\n🗺️ {label}: {app_url}"

    log.info("Reply to %s (region=%s, interv=%s, map=%s, show_map=%s)",
             phone, region_key, result.intervention, bool(media_url), result.show_map)
    return reply, media_url, region_key


def _process_and_push(phone: str, message: str, pin: Optional[Tuple[float, float]],
                      pin_region: Optional[str], route: "Optional[agents.Route]") -> None:
    """Background: specialist answer (+ map) pushed back via Twilio REST.

    If the turn needs a live data pull, a holding "pulling live data…" message is
    sent to the worker first (separate WhatsApp message), then the answer follows.
    """
    def _push_notice(text: str) -> None:
        try:
            send_whatsapp(to=phone, body=text)
        except Exception:  # pragma: no cover — holding message is best-effort
            log.info("Holding notice send failed for %s", phone)

    try:
        reply, media_url, _ = build_reply(phone, message, pin=pin, pin_region=pin_region,
                                          precomputed_route=route, on_notice=_push_notice)
    except Exception:  # pragma: no cover
        log.exception("Specialist error")
        reply, media_url = (
            "System error processing your request. Please try again. / "
            "Erro do sistema. Tente novamente. / Vuto la dongosolo. Yesaninso.", None)
    try:
        send_whatsapp(to=phone, body=reply, media_url=media_url)
    except Exception:
        log.exception("Send failed (media=%s); retrying text-only", bool(media_url))
        if media_url:
            try:
                send_whatsapp(to=phone, body=reply, media_url=None)
            except Exception:  # pragma: no cover
                log.exception("Text-only retry also failed for %s", phone)


def _location_message(lat: float, lon: float, body: str) -> Tuple[str, Optional[str]]:
    """Build the pipeline message + resolve the pin's region from a shared GPS point."""
    near = data.nearest_region(lat, lon)
    region_key = near[0] if near else None
    rec = data.region_record(region_key) if region_key else None
    region_name = region_key.replace("_", " ").title() if region_key else "unknown area"
    country = rec["country"] if rec else ""
    lang = rec["language_default"] if rec else "English"

    base = body.strip() or _LOCATION_PROMPT.get(lang, _LOCATION_PROMPT["English"])
    note = (f"\n\n(Field worker shared GPS location: {lat:.4f}, {lon:.4f}; nearest "
            f"sub-region: {region_name}, {country}. Scope the recommendation to that "
            f"locality and its low-lying / flood-prone zones.)")
    return base + note, region_key


@app.post("/whatsapp")
async def whatsapp(
    request: Request,
    From: str = Form(default=""),
    Body: str = Form(default=""),
    MessageSid: str = Form(default=""),
    Latitude: str = Form(default=""),
    Longitude: str = Form(default=""),
    Label: str = Form(default=""),
    Address: str = Form(default=""),
):
    form = await request.form()
    if not _validate_twilio(request, dict(form)):
        return PlainTextResponse("Invalid signature", status_code=403)

    phone = From or "unknown"
    body = (Body or "").strip()
    pin: Optional[Tuple[float, float]] = None
    pin_region: Optional[str] = None

    if Latitude and Longitude:
        try:
            lat, lon = float(Latitude), float(Longitude)
            pin = (lat, lon)
            message, pin_region = _location_message(lat, lon, body)
            log.info("Inbound location from %s: (%s,%s) %s -> region=%s",
                     phone, lat, lon, Label or Address, pin_region)
        except ValueError:
            message = body
    else:
        message = body
        log.info("Inbound WhatsApp from %s: %s", phone, message)

    if not message:
        return Response(content=_twiml(
            "Send a message describing your area and situation — or share your "
            "location pin and I'll map the malaria risk around you."),
            media_type="application/xml")

    if _outbound_configured():
        # Show a WhatsApp typing indicator (best-effort) instead of a holding
        # message; it clears when we push the real answer (~10s) or after 25s.
        await run_in_threadpool(send_typing, MessageSid)
        threading.Thread(
            target=_process_and_push, args=(phone, message, pin, pin_region, None),
            daemon=True,
        ).start()
        log.info("Sent typing indicator + queued reply for %s.", phone)
        return Response(content=_twiml_empty(), media_type="application/xml")

    # Synchronous fallback (no outbound creds) — fine for local testing.
    try:
        reply, media_url, _ = await run_in_threadpool(
            build_reply, phone, message, pin, pin_region)
    except Exception:  # pragma: no cover
        log.exception("Specialist error")
        reply, media_url = (
            "System error processing your request. Please try again. / "
            "Erro do sistema. Tente novamente. / Vuto la dongosolo. Yesaninso.", None)
    return Response(content=_twiml(reply, media_url), media_type="application/xml")


@app.post("/message")
def message_json(payload: dict):
    """JSON endpoint for testing without Twilio.

    Declared sync (def, not async) so Starlette runs the blocking pipeline in a
    threadpool instead of freezing the event loop for other requests.

    Body: {"phone","message"} and optionally {"lat","lon"} to simulate a pin.
    """
    phone = payload.get("phone", "test:+10000000000")
    message = (payload.get("message") or "").strip()
    pin = None
    pin_region = None
    if payload.get("lat") is not None and payload.get("lon") is not None:
        lat, lon = float(payload["lat"]), float(payload["lon"])
        pin = (lat, lon)
        message, pin_region = _location_message(lat, lon, message)
    if not message:
        return JSONResponse({"error": "missing 'message' (or lat/lon)"}, status_code=400)

    try:
        reply, media_url, region_key = build_reply(phone, message, pin=pin, pin_region=pin_region)
    except Exception as e:  # surface a useful JSON error instead of a raw 500
        log.exception("Chat /message failed")
        detail = f"{type(e).__name__}: {e}"
        return JSONResponse(
            {"error": f"The agent hit an error. {detail}"}, status_code=500)
    return {
        "phone": phone,
        "region": region_key,
        "reply": reply,
        "map_url": media_url,
    }


@app.post("/message/stream")
def message_stream(payload: dict):
    """Server-Sent Events: stream each pipeline stage (route → fetch → self-heal →
    brief → specialist → adversarial → final) to the browser as it happens. Used by
    the chat in DEMO_MODE to visibly narrate the multi-agent reasoning."""
    phone = payload.get("phone", "web:stream")
    message = (payload.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "missing 'message'"}, status_code=400)

    q: "queue.Queue" = queue.Queue()

    def on_step(stage: str, data: dict) -> None:
        q.put({"type": "step", "stage": stage, "data": data})

    def on_token(text: str) -> None:
        q.put({"type": "token", "text": text})

    def on_notice(text: str) -> None:
        q.put({"type": "notice", "text": text})

    def run() -> None:
        try:
            # Stream the specialist's words to the browser as they generate (first
            # token in ~0.6s). DEMO_MODE narrates pipeline stages instead, so we
            # pass no token callback there (service also guards this).
            token_cb = None if config.DEMO_MODE else on_token
            notice_cb = None if config.DEMO_MODE else on_notice
            result = handle_message(phone, message, on_step=on_step, on_token=token_cb,
                                    on_notice=notice_cb)
            media = None
            if result.show_map and result.region_key:
                media = _media_url_for(result.region_key, None)
            q.put({"type": "final", "reply": result.text, "map_url": media,
                   "region": result.region_key, "urgency": result.urgency,
                   "used_pre_reasoned": result.used_pre_reasoned})
        except Exception as e:  # pragma: no cover
            log.exception("stream pipeline failed")
            q.put({"type": "error", "error": f"{type(e).__name__}: {e}"})
        finally:
            q.put({"type": "done"})

    threading.Thread(target=run, daemon=True).start()

    def gen():
        while True:
            ev = q.get()
            yield f"data: {json.dumps(ev)}\n\n"
            if ev.get("type") == "done":
                break

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/app", response_class=HTMLResponse)
def app_index():
    """Simple local landing page linking to every region's interactive map."""
    items = "".join(
        f'<li><a href="/app/{k}">{k.replace("_", " ").title()}</a> '
        f'(<a href="/map/{k}">static map</a>)</li>'
        for k in data.regions()
    )
    return HTMLResponse(
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        "<title>MalarIA — risk maps</title>"
        "<style>body{font-family:system-ui,Arial,sans-serif;max-width:640px;margin:40px auto;padding:0 16px}"
        "h1{font-size:20px}li{margin:8px 0;font-size:16px}a{color:#1565c0}</style></head>"
        "<body><h1>🦟 MalarIA — interactive malaria risk maps</h1>"
        "<p>Tap a region for the interactive map (pan/zoom, tap markers).</p>"
        f"<ul>{items}</ul></body></html>"
    )


@app.get("/app/{region}", response_class=HTMLResponse)
def interactive_map(region: str, lat: Optional[float] = Query(default=None),
                    lon: Optional[float] = Query(default=None)):
    """Interactive Leaflet map page for a region (real OSM tiles, pan/zoom)."""
    region = region.lower()
    if region not in data.regions():
        return JSONResponse(
            {"error": f"unknown region '{region}'", "regions": list(data.regions().keys())},
            status_code=404)
    pin = (lat, lon) if (lat is not None and lon is not None) else None
    rec = data.region_record(region)
    country = rec["country"] if rec else None
    og_image = ""
    if config.PUBLIC_BASE_URL and country:
        path = choropleth.render_choropleth(country, region)
        if path:
            og_image = f"{config.PUBLIC_BASE_URL}/maps/{path.name}"
    html = webmap.render_choropleth_html(country, region, pin=pin, og_image=og_image)
    if not html:
        return JSONResponse({"error": "no geo data for region"}, status_code=404)
    return HTMLResponse(html)


@app.get("/map/{region}")
def map_preview(region: str):
    """Preview a region's alert-level choropleth in a browser (renders on demand)."""
    region = region.lower()
    if region not in data.regions():
        return JSONResponse(
            {"error": f"unknown region '{region}'", "regions": list(data.regions().keys())},
            status_code=404)
    rec = data.region_record(region)
    path = choropleth.render_choropleth(rec["country"], region, force=True) if rec else None
    if not path:
        return JSONResponse({"error": "no boundary data for region"}, status_code=404)
    return FileResponse(str(path), media_type="image/png")


def send_whatsapp(to: str, body: str, media_url: Optional[str] = None) -> str:
    """Send a WhatsApp message (optionally with a map image) via Twilio REST."""
    from twilio.rest import Client

    client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    kwargs = {"from_": config.TWILIO_WHATSAPP_FROM, "to": to, "body": body}
    if media_url:
        kwargs["media_url"] = [media_url]
    return client.messages.create(**kwargs).sid
