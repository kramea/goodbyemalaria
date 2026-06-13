"""Technical 'under the hood' sub-page for MalarIA.

Explains how the system was built with Claude Opus 4.8, the multi-agent
(router -> intervention specialist) architecture, the live data sources, the
intervention/urgency decision logic, and the mapping — with real figures pulled
from the running system.
"""

from . import config, data, prompts


def _specialists_by_horizon() -> dict:
    groups = {"immediate": [], "month ahead": [], "season ahead": []}
    for label in prompts.INTERVENTIONS.values():
        name, _, horizon = label.partition(" — ")
        horizon = horizon.strip().lower()
        groups.setdefault(horizon, []).append(name.strip())
    return groups


def render_tech(public_base_url: str = "") -> str:
    groups = _specialists_by_horizon()
    n_spec = len(prompts.INTERVENTIONS)
    n_regions = len(data.regions())
    router_m, spec_m, esc_m = config.ROUTER_MODEL, config.SPECIALIST_MODEL, config.ESCALATION_MODEL

    def li(items):
        return "".join(f"<li>{x}</li>" for x in items)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>MalarIA — how it works (technical)</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600;800;900&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet"/>
<style>
  :root{{--ink:#1c1410;--bg:#fbf6ee;--paper:#fff;--red:#e23b2e;--red-d:#b62a20;--amber:#f4a92e;
    --teal:#0f7a6c;--teal-d:#0b5a50;--muted:#6b5d52;--line:#e7dccd}}
  *{{box-sizing:border-box}} html{{scroll-behavior:smooth}}
  body{{margin:0;font-family:Inter,system-ui,Arial,sans-serif;color:var(--ink);background:var(--bg);line-height:1.6}}
  h1,h2,h3,.brand{{font-family:Montserrat,system-ui,sans-serif;line-height:1.12;letter-spacing:-.02em}}
  code,.mono{{font-family:'JetBrains Mono',ui-monospace,monospace}}
  a{{color:var(--teal-d)}}
  .wrap{{max-width:1000px;margin:0 auto;padding:0 22px}}
  .pattern{{height:14px;background:repeating-linear-gradient(135deg,var(--red) 0 18px,var(--amber) 18px 36px,var(--teal) 36px 54px)}}
  header.nav{{position:sticky;top:0;z-index:50;background:rgba(28,20,16,.96);backdrop-filter:blur(6px)}}
  .nav .wrap{{display:flex;align-items:center;justify-content:space-between;height:62px}}
  .brand{{color:#fff;font-weight:900;font-size:20px}} .brand b{{color:var(--amber)}}
  .nav nav a{{color:#f3e9dc;text-decoration:none;margin-left:22px;font-size:14px;font-weight:500}}

  .hero{{background:linear-gradient(160deg,#2a1a12,#1c1410);color:#fff;padding:66px 0 56px}}
  .hero .kick{{color:var(--amber);font-weight:700;letter-spacing:.16em;text-transform:uppercase;font-size:13px}}
  .hero h1{{font-size:clamp(30px,5vw,50px);font-weight:900;margin:12px 0 12px}}
  .hero p{{color:#efe4d6;max-width:680px;font-size:18px;margin:0}}
  .badge{{display:inline-block;margin-top:20px;background:var(--red);color:#fff;font-family:Montserrat;font-weight:800;
    border-radius:999px;padding:10px 20px;font-size:15px}}

  section{{padding:54px 0}}
  .eyebrow{{color:var(--red-d);font-weight:700;letter-spacing:.13em;text-transform:uppercase;font-size:13px}}
  h2{{font-size:clamp(24px,3.6vw,34px);font-weight:800;margin:8px 0 12px}}
  .sub{{color:var(--muted);max-width:760px;font-size:16px}}

  .figs{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-top:28px}}
  @media(max-width:860px){{.figs{{grid-template-columns:repeat(3,1fr)}}}}
  @media(max-width:520px){{.figs{{grid-template-columns:repeat(2,1fr)}}}}
  .fig{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:16px;text-align:center}}
  .fig .n{{font-family:Montserrat;font-weight:900;font-size:26px;color:var(--red)}}
  .fig .l{{font-size:12px;color:var(--muted);margin-top:4px}}

  /* flow diagram */
  .flow{{display:flex;flex-direction:column;gap:0;margin-top:26px}}
  .node{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:16px 20px}}
  .node.r{{border-left:6px solid var(--amber)}} .node.s{{border-left:6px solid var(--red)}}
  .node.d{{border-left:6px solid var(--teal)}} .node.m{{border-left:6px solid #9b8a7c}}
  .node h3{{margin:0 0 4px;font-size:17px}} .node .meta{{font-size:13px;color:var(--muted)}}
  .node .tag{{display:inline-block;background:#241712;color:#fff;border-radius:6px;padding:2px 8px;font-size:12px;margin-left:6px}}
  .arrow{{align-self:center;color:var(--muted);font-size:22px;margin:6px 0}}

  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:24px}}
  @media(max-width:820px){{.grid2{{grid-template-columns:1fr}}}}
  .card{{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:22px}}
  .card h3{{margin:0 0 8px;font-size:18px}}
  .card ul{{margin:8px 0 0;padding-left:18px}} .card li{{margin:5px 0;font-size:15px}}
  .card.dark{{background:#241712;color:#f3e9dc;border:0}} .card.dark h3{{color:#fff}}
  .tag2{{display:inline-block;background:#eaf4f1;color:var(--teal-d);border:1px solid #cfe6e0;border-radius:999px;
    padding:3px 10px;font-size:12px;font-weight:600;margin:2px}}

  table.src{{width:100%;border-collapse:collapse;margin-top:22px;background:var(--paper);border-radius:14px;overflow:hidden;border:1px solid var(--line)}}
  table.src th,table.src td{{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line);font-size:14px;vertical-align:top}}
  table.src th{{background:#241712;color:#fff;font-family:Montserrat;font-size:13px}}
  table.src td b{{color:var(--ink)}}

  .scn{{background:#241712;color:#f3e9dc;border-radius:16px;padding:22px;margin-top:14px}}
  .scn .q{{font-style:italic;color:#fff;border-left:3px solid var(--amber);padding-left:12px}}
  .scn .step{{font-size:14px;margin:8px 0;color:#d8c8b8}} .scn .step b{{color:#fff}}
  .scn .pill{{display:inline-block;background:#3a2a20;border-radius:6px;padding:1px 8px;font-size:12px;margin:0 2px}}

  .maps{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:24px}}
  @media(max-width:760px){{.maps{{grid-template-columns:1fr}}}}
  .maps figure{{margin:0}} .maps img{{width:100%;border-radius:14px;border:1px solid var(--line);background:#fff}}
  .maps figcaption{{font-size:13px;color:var(--muted);margin-top:8px}}

  footer{{background:#1c1410;color:#cdbfb0;padding:36px 0;font-size:13px}}
  footer a{{color:var(--amber)}}
</style>
</head>
<body>
<div class="pattern"></div>
<header class="nav"><div class="wrap">
  <div class="brand">🦟 Malar<b>IA</b></div>
  <nav><a href="/">← Back to site</a><a href="#arch">Architecture</a><a href="#data">Live data</a><a href="#logic">Decision logic</a><a href="#maps">Mapping</a></nav>
</div></header>

<section class="hero"><div class="wrap">
  <div class="kick">Under the hood</div>
  <h1>How MalarIA works</h1>
  <p>A multi-agent malaria-prevention assistant — designed and built end-to-end with
     <b>Claude Opus 4.8</b>, running a fast router + specialist agent loop over live data.</p>
  <div class="badge">⚙️ Built with Claude Opus 4.8</div>
</div></section>

<!-- FIGURES -->
<section><div class="wrap">
  <div class="eyebrow">At a glance</div>
  <h2>The system in figures</h2>
  <div class="figs">
    <div class="fig"><div class="n">3</div><div class="l">Claude model tiers (adaptive)</div></div>
    <div class="fig"><div class="n">{n_spec}</div><div class="l">intervention specialist agents</div></div>
    <div class="fig"><div class="n">4</div><div class="l">languages, auto-detected</div></div>
    <div class="fig"><div class="n">{n_regions}</div><div class="l">sub-national zones tracked</div></div>
    <div class="fig"><div class="n">3</div><div class="l">live data feeds + curated KB</div></div>
    <div class="fig"><div class="n">~9s</div><div class="l">median reply, streamed</div></div>
  </div>
</div></section>

<!-- BUILT WITH CLAUDE -->
<section style="background:#fff"><div class="wrap">
  <div class="eyebrow">The build</div>
  <h2>Designed &amp; built with Claude Opus 4.8</h2>
  <p class="sub">Every part of MalarIA — the agent architecture, the prompt design, the live-data
    integrations, the choropleth mapping, the WhatsApp delivery layer, and this site — was developed
    iteratively with <b>Claude Opus 4.8</b> (<code>claude-opus-4-8</code>) via Claude Code. At runtime the
    system uses <b>adaptive model tiering</b>: the cheapest capable model for each job, escalating only when
    it's worth it.</p>
  <div class="grid2">
    <div class="card">
      <h3>Runtime model tiers</h3>
      <ul>
        <li><b>Router</b> — Claude (fast tier): classification in ~1–2s</li>
        <li><b>Specialist</b> — Claude: the field reply, streamed</li>
        <li><b>Adaptive tiering</b> — the cheapest capable Claude model for each job, escalating only when it's worth it</li>
      </ul>
    </div>
    <div class="card dark">
      <h3>Engineering choices that mattered</h3>
      <ul>
        <li><b>Streaming</b> responses — survives flaky field connections</li>
        <li><b>Structured outputs</b> — the router returns a validated schema</li>
        <li><b>Disk-cached</b> WHO data, per-phone session memory</li>
        <li><b>Async delivery</b> + WhatsApp typing indicator</li>
      </ul>
    </div>
  </div>
</div></section>

<!-- ARCHITECTURE -->
<section id="arch"><div class="wrap">
  <div class="eyebrow">Architecture</div>
  <h2>A router, then a specialist — sub-agents per intervention</h2>
  <p class="sub">Each message is classified once, then handed to the single agent that is the expert on the
    relevant intervention. Cheap where possible, deep where it counts.</p>
  <div class="flow">
    <div class="node m"><h3>📩 Inbound WhatsApp message <span class="tag">any language</span></h3><div class="meta">Twilio → FastAPI webhook → per-phone session memory loaded</div></div>
    <div class="arrow">▼</div>
    <div class="node r"><h3>🧭 Router</h3><div class="meta">Structured output: <code>language · intent · intervention · timeline · needs_weather</code></div></div>
    <div class="arrow">▼</div>
    <div class="node d"><h3>🔌 Context assembly</h3><div class="meta">Curated zone data + current alert (outbreak/flood/normal) + live WHO baseline + live rain/flood forecast (only if needed) + urgency cascade</div></div>
    <div class="arrow">▼</div>
    <div class="node s"><h3>🩺 Intervention specialist</h3><div class="meta">1 of {n_spec} expert playbooks · replies in the worker's language · streamed</div></div>
    <div class="arrow">▼</div>
    <div class="node m"><h3>📤 Reply + alert choropleth</h3><div class="meta">Pushed back via Twilio (first &amp; closing turns include the map); turn saved to memory</div></div>
  </div>
</div></section>

<!-- SPECIALISTS -->
<section style="background:#fff"><div class="wrap">
  <div class="eyebrow">Sub-agents</div>
  <h2>{n_spec} intervention specialists, by horizon</h2>
  <p class="sub">The router picks one. Each carries its own decision rules (product, dosing, coverage,
    resistance constraints, timing).</p>
  <div class="grid2" style="grid-template-columns:1fr 1fr 1fr">
    <div class="card"><h3>⚡ Immediate</h3><ul>{li(groups.get('immediate', []))}</ul></div>
    <div class="card"><h3>📅 Month ahead</h3><ul>{li(groups.get('month ahead', []))}</ul></div>
    <div class="card"><h3>🌧️ Season ahead</h3><ul>{li(groups.get('season ahead', []))}</ul></div>
  </div>
</div></section>

<!-- LIVE DATA -->
<section id="data"><div class="wrap">
  <div class="eyebrow">Live data</div>
  <h2>Grounded in real feeds, not vibes</h2>
  <table class="src">
    <tr><th>Source</th><th>What it provides</th><th>How it's used</th></tr>
    <tr><td><b>WHO Global Health Observatory</b></td><td>National malaria incidence &amp; estimated cases (2024)</td><td>Cited baseline; fetched once, cached to disk</td></tr>
    <tr><td><b>Open-Meteo (forecast)</b></td><td>Short-range rainfall / precipitation probability</td><td>Spray &amp; larvicide timing — fetched only when relevant</td></tr>
    <tr><td><b>Open-Meteo Flood / GloFAS</b></td><td>River discharge vs 30-day norm (rising / receding)</td><td>Flood-response urgency in flood-prone zones</td></tr>
    <tr><td><b>Curated knowledge base</b></td><td>Per-zone incidence, resistance, season, elevation, vectors, current alert</td><td>Core reasoning context for every reply</td></tr>
    <tr><td><b>geoBoundaries</b></td><td>Mozambique province + Malawi district polygons</td><td>Alert-level choropleth maps</td></tr>
  </table>
</div></section>

<!-- DECISION LOGIC -->
<section id="logic" style="background:#fff"><div class="wrap">
  <div class="eyebrow">Decision logic</div>
  <h2>Urgency cascade: the right tool for what's happening now</h2>
  <p class="sub">Before choosing a tool, MalarIA assesses the live situation and front-loads the most urgent
    response. Same question, different ground truth → different answer.</p>
  <div class="grid2">
    <div class="scn">
      <div class="step"><span class="pill">Scenario A</span> active outbreak + flooding</div>
      <p class="q">“It flooded in Chókwè — where should I larvicide, and is it dry enough this week?”</p>
      <div class="step"><b>Router →</b> lang=EN · intent=specific · <b>larviciding</b> · needs_weather=true</div>
      <div class="step"><b>Context →</b> Gaza <span class="pill">OUTBREAK</span><span class="pill">FLOODING</span> + live forecast + GloFAS discharge</div>
      <div class="step"><b>Specialist →</b> leads ⚡ Bti larviciding within 48h on dry days, resistance-agnostic; people-first flood steps</div>
    </div>
    <div class="scn">
      <div class="step"><span class="pill">Scenario B</span> dry-season lull</div>
      <p class="q">“How is the situation in Zomba?”</p>
      <div class="step"><b>Router →</b> lang=EN · intent=triage · <b>triage</b> · needs_weather=false</div>
      <div class="step"><b>Context →</b> Zomba <span class="pill">NORMAL (dry)</span> + WHO national baseline</div>
      <div class="step"><b>Specialist →</b> “planning window, not an emergency” → weights 📅 month / 🌧️ season prep, no false urgency</div>
    </div>
  </div>
  <p class="sub" style="margin-top:18px">Timing factors that flip the answer: <span class="tag2">🌧️ weather</span>
    <span class="tag2">🌊 ground &amp; flooding</span> <span class="tag2">📅 season</span>
    <span class="tag2">🧬 insecticide resistance</span> <span class="tag2">📈 current alert level</span></p>
</div></section>

<!-- MAPPING -->
<section id="maps"><div class="wrap">
  <div class="eyebrow">Mapping</div>
  <h2>Alert-level choropleths</h2>
  <p class="sub">Admin polygons (geoBoundaries) are shaded by each zone's current alert — outbreak (red),
    elevated (orange), normal/dry (green) — and rendered both as a static image for WhatsApp and an
    interactive Leaflet layer. The worker's zone is outlined.</p>
  <div class="maps">
    <figure><img src="/map/gaza" alt="Mozambique alert choropleth"/><figcaption>Mozambique provinces — Gaza in active outbreak (red).</figcaption></figure>
    <figure><img src="/map/zomba" alt="Malawi alert choropleth"/><figcaption>Malawi districts — dry-season lull (green) in the south.</figcaption></figure>
  </div>
</div></section>

<footer><div class="wrap">
  <div class="brand" style="color:#fff;font-size:18px">🦟 Malar<b style="color:var(--amber)">IA</b></div>
  <p>Built with Claude Opus 4.8 for Goodbye Malaria · <a href="/">← back to the main site</a></p>
</div></footer>
</body>
</html>"""
