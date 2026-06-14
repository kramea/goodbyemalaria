"""Technical 'how it works' sub-page for MalarIA — a blog-format product write-up.

Explains the data stack, the complexities of grounding a field agent in messy
real-world feeds, the self-healing data layer, the adversarial review, and the
train/inference split — built with Claude Opus 4.8. Figures are pulled live from
the running system.
"""

from . import config, data, prompts


def _specialists_by_horizon() -> dict:
    groups = {"immediate": [], "month ahead": [], "season ahead": []}
    for label in prompts.INTERVENTIONS.values():
        name, _, horizon = label.partition(" — ")
        groups.setdefault(horizon.strip().lower(), []).append(name.strip())
    return groups


def render_tech(public_base_url: str = "") -> str:
    groups = _specialists_by_horizon()
    n_spec = len(prompts.INTERVENTIONS)
    n_regions = len(data.regions())
    n_scenarios = n_regions * 5 * 4  # zones × urgency states × resistance profiles

    def li(items):
        return "".join(f"<li>{x}</li>" for x in items)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>MalarIA — how it works (technical write-up)</title>
<meta name="description" content="How MalarIA grounds a malaria field agent in live data, heals missing data, and adversarially reviews every recommendation before it reaches a worker."/>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600;800;900&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet"/>
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
  .nav nav a{{color:#f3e9dc;text-decoration:none;margin-left:20px;font-size:14px;font-weight:500}}
  @media(max-width:820px){{.nav nav a{{margin-left:12px;font-size:13px}}}}

  .hero{{background:linear-gradient(160deg,#2a1a12,#1c1410);color:#fff;padding:70px 0 58px}}
  .hero .kick{{color:var(--amber);font-weight:700;letter-spacing:.16em;text-transform:uppercase;font-size:13px}}
  .hero h1{{font-size:clamp(30px,5vw,52px);font-weight:900;margin:12px 0 14px}}
  .hero p{{color:#efe4d6;max-width:720px;font-size:19px;margin:0}}
  .badge{{display:inline-block;margin-top:22px;background:var(--red);color:#fff;font-family:Montserrat;font-weight:800;
    border-radius:999px;padding:10px 20px;font-size:15px}}

  section{{padding:50px 0}}
  .eyebrow{{color:var(--red-d);font-weight:700;letter-spacing:.13em;text-transform:uppercase;font-size:13px}}
  h2{{font-size:clamp(24px,3.6vw,34px);font-weight:800;margin:8px 0 12px}}
  .sub{{color:var(--muted);max-width:760px;font-size:16px}}

  .figs{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-top:28px}}
  @media(max-width:860px){{.figs{{grid-template-columns:repeat(3,1fr)}}}}
  @media(max-width:520px){{.figs{{grid-template-columns:repeat(2,1fr)}}}}
  .fig{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:16px;text-align:center}}
  .fig .n{{font-family:Montserrat;font-weight:900;font-size:26px;color:var(--red)}}
  .fig .l{{font-size:12px;color:var(--muted);margin-top:4px}}

  /* blog article */
  .article{{max-width:720px;margin:0 auto}}
  .article .lead{{font-size:20px;color:var(--muted);margin:0 0 26px}}
  .article h3{{font-size:23px;margin:34px 0 8px}}
  .article h3 .em{{color:var(--red)}}
  .article p{{font-size:17px;color:#2c2118;margin:0 0 16px}}
  .article ul{{font-size:17px;color:#2c2118;margin:0 0 16px;padding-left:20px}} .article li{{margin:7px 0}}
  .article code{{background:#f0e9dd;padding:1px 6px;border-radius:5px;font-size:14px}}
  .article blockquote{{border-left:4px solid var(--amber);margin:22px 0;padding:6px 0 6px 18px;
    font-style:italic;color:var(--ink);font-size:19px}}
  .article .sig{{color:var(--muted);font-size:14px;margin-top:30px;border-top:1px solid var(--line);padding-top:14px}}

  .flow{{display:flex;flex-direction:column;gap:0;margin-top:26px}}
  .node{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:15px 20px}}
  .node.r{{border-left:6px solid var(--amber)}} .node.s{{border-left:6px solid var(--red)}}
  .node.d{{border-left:6px solid var(--teal)}} .node.m{{border-left:6px solid #9b8a7c}}
  .node.h{{border-left:6px solid #7b5cff}} .node.a{{border-left:6px solid #d94d8a}}
  .node h3{{margin:0 0 4px;font-size:17px}} .node .meta{{font-size:13px;color:var(--muted)}}
  .node code{{font-size:12.5px}}
  .arrow{{align-self:center;color:var(--muted);font-size:20px;margin:5px 0}}

  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:24px}}
  @media(max-width:820px){{.grid2{{grid-template-columns:1fr}}}}
  .card{{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:22px}}
  .card h3{{margin:0 0 8px;font-size:18px}}
  .card ul{{margin:8px 0 0;padding-left:18px}} .card li{{margin:5px 0;font-size:15px}}
  .card.dark{{background:#241712;color:#f3e9dc;border:0}} .card.dark h3{{color:#fff}}
  .tag2{{display:inline-block;background:#eaf4f1;color:var(--teal-d);border:1px solid #cfe6e0;border-radius:999px;
    padding:3px 10px;font-size:12px;font-weight:600;margin:2px}}

  table.src{{width:100%;border-collapse:collapse;margin-top:22px;background:var(--paper);border-radius:14px;overflow:hidden;border:1px solid var(--line)}}
  table.src th,table.src td{{text-align:left;padding:11px 13px;border-bottom:1px solid var(--line);font-size:13.5px;vertical-align:top}}
  table.src th{{background:#241712;color:#fff;font-family:Montserrat;font-size:13px}}
  table.src td b{{color:var(--ink)}}
  .live{{color:var(--teal-d);font-weight:700}} .heal{{color:var(--red-d);font-weight:700}}

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
  <nav>
    <a href="/">← Site</a>
    <a href="#story">Write-up</a>
    <a href="#arch">Pipeline</a>
    <a href="#data">Data</a>
    <a href="#heal">Self-healing</a>
    <a href="#adv">Adversarial</a>
  </nav>
</div></header>

<section class="hero"><div class="wrap">
  <div class="kick">Under the hood · technical write-up</div>
  <h1>How MalarIA reasons<br/>under uncertainty</h1>
  <p>A field-worker malaria-prevention agent that grounds itself in eight live and curated
     data sources, heals itself when those sources go dark, and runs an adversarial review
     before any advice reaches the ground — built end-to-end with <b>Claude Opus 4.8</b>.</p>
  <div class="badge">⚙️ Built with Claude Opus 4.8</div>
</div></section>

<!-- FIGURES -->
<section><div class="wrap">
  <div class="eyebrow">At a glance</div>
  <h2>The system in figures</h2>
  <div class="figs">
    <div class="fig"><div class="n">8</div><div class="l">live + curated data sources</div></div>
    <div class="fig"><div class="n">{n_spec}</div><div class="l">intervention specialists</div></div>
    <div class="fig"><div class="n">6</div><div class="l">agent roles in the pipeline</div></div>
    <div class="fig"><div class="n">4</div><div class="l">languages, auto-detected</div></div>
    <div class="fig"><div class="n">{n_regions}</div><div class="l">sub-national zones</div></div>
    <div class="fig"><div class="n">{n_scenarios}</div><div class="l">scenarios pre-validated offline</div></div>
  </div>
</div></section>

<!-- ===================== THE BLOG WRITE-UP ===================== -->
<section id="story" style="background:#fff"><div class="wrap"><div class="article">
  <div class="eyebrow">The write-up</div>
  <h2 style="margin-bottom:18px">Building an agent that's honest about what it doesn't know</h2>

  <p class="lead">Malaria isn't only a medicine problem — it's a <b>timing</b> problem. The right
    intervention at the wrong moment saves no one. MalarIA is an attempt to put that judgement,
    grounded in live conditions, into a field worker's pocket over WhatsApp.</p>

  <h3>Malaria is a <span class="em">timing</span> problem</h3>
  <p>Spray a wall the week before heavy rain and the insecticide washes off. Hand out bed nets after
    the transmission peak and the cases have already happened. Larvicide a flood pool after the
    mosquitoes have already emerged as adults and you've missed the window entirely. The tools work —
    the science is settled — but their value collapses if they land outside a narrow window that
    shifts week to week with the weather, the season, and the state of an outbreak.</p>
  <p>So the core design question was never "which intervention is best?" It was: <b>can the agent know
    enough about right-now conditions to choose the right tool for this week, in this district?</b>
    That turns a chatbot into a data problem.</p>

  <h3>Grounding the agent: the data stack</h3>
  <p>Every reply is built on a <b>live situation brief</b> assembled per message from eight sources.
    Each one answers a specific operational question:</p>
  <ul>
    <li><b>WHO Global Health Observatory</b> — the national burden baseline (incidence per 1,000).</li>
    <li><b>Open-Meteo forecast</b> — the next 7 days of rain probability, to find <i>spray-safe days</i>.</li>
    <li><b>Open-Meteo archive (90 days)</b> — past rainfall, from which we compute a <b>mosquito breeding
      timeline</b>: when eggs were likely laid (the peak-rain day), when larvae peak (+7d), and when adults
      emerge (+12d). That timeline is what decides whether larviciding is still useful or already too late.</li>
    <li><b>GloFAS / Open-Meteo flood</b> — river discharge vs. its norm, for flood-response urgency.</li>
    <li><b>ReliefWeb</b> — live humanitarian health alerts (outbreaks, displacement) in the last 72h.</li>
    <li><b>DHIS2</b> — weekly confirmed case counts and the week-on-week trend, the earliest outbreak signal.</li>
    <li><b>PMI malaria profiles</b> — parsed from the official FY2024 PDFs: confirmed insecticide
      <b>resistance</b>, the recommended net type, IRS chemical, and <b>supply-chain / stockout</b> risk.</li>
    <li><b>A curated knowledge base</b> — per-zone vectors, season phase, elevation/flood-proneness, and the
      last campaign, hand-built for the {n_regions} zones we cover.</li>
  </ul>
  <p>The fetchers run <b>in parallel</b> (a thread pool), each with a tight timeout and its own cache, so
    assembling the brief costs a second or two, not the sum of eight network calls.</p>

  <h3>The hard part isn't the data — it's when the data <span class="em">lies or vanishes</span></h3>
  <p>In a Mozambican district on a 2G phone, the comfortable assumption that your data sources are up,
    fresh, and agree with each other is simply false. Real feeds:</p>
  <ul>
    <li><b>Go missing</b> — an API is down, rate-limited, or (as we hit in build) silently changes its access rules.</li>
    <li><b>Go stale</b> — last week's case counts, presented as this week's.</li>
    <li><b>Disagree</b> — ReliefWeb often lags district surveillance by 48–72h, so it can say "all clear"
      while DHIS2 already shows a spike.</li>
  </ul>
  <p>A naive agent does the worst possible thing here: it stays silent, or it fills the gap with a confident
    guess. Neither is acceptable when a field worker is about to deploy a spray team. So before the agent
    reasons at all, a different agent checks the data.</p>

  <h3>Self-healing: the agent that runs <span class="em">before</span> the agent</h3>
  <p>Every turn builds a <b>data-quality report</b> — each source marked OK or MISSING. If anything is wrong,
    a dedicated <b>self-healing agent</b> runs first. It doesn't invent data; it applies a documented fallback
    and, crucially, <b>records the uncertainty so the specialist can be honest about it</b>:</p>
  <ul>
    <li>DHIS2 down → fall back to the curated alert level as a case-trend proxy, flagged as a proxy.</li>
    <li>PMI profile unreachable → use the last-known resistance data from the knowledge base.</li>
    <li>ReliefWeb unreachable → assume no active alert, and say so.</li>
    <li>Sources conflict → trust district surveillance over the slower humanitarian feed, and note the lag.</li>
  </ul>
  <blockquote>The result is a reply that will say "DHIS2 is offline, so these case numbers are estimates —
    but the outbreak signal is confirmed" rather than quietly pretending everything is fine.</blockquote>

  <h3>Adversarial review: two critics before a worker acts</h3>
  <p>A plausible-sounding malaria recommendation can still be <b>dangerous</b>: recommending a pyrethroid net
    where pyrethroid resistance is confirmed, or larviciding after the adults have already emerged. So the
    specialist's first answer is treated as a <b>draft</b>, not a verdict. Two reviewers challenge it in parallel:</p>
  <ul>
    <li><b>The Devil's Advocate</b> — a senior epidemiologist persona hunting for resistance mismatches,
      timing errors, data contradictions, and operationally impossible advice.</li>
    <li><b>The Field Realism check</b> — an operations-manager persona asking: can one worker actually execute
      this, with standard supplies, given the stockout risk and their skill level?</li>
  </ul>
  <p>An <b>orchestrator</b> then merges the draft with both verdicts — rewriting on a critical challenge,
    appending a fallback when a product is at stockout risk, escalating when a step needs a trained supervisor.
    In testing, this caught a real flaw: for a flooded outbreak zone the draft led with larviciding, and the
    Devil's Advocate flagged that the breeding window had <b>already closed</b> — so the final reply pivoted to
    emergency IRS with a resistance-appropriate insecticide. That's the layer earning its keep.</p>

  <h3>Train offline, answer fast: the inference split</h3>
  <p>Running self-healing + a specialist + two reviewers + an orchestrator is powerful but slow — roughly
    45 seconds end to end. Acceptable for a demo where you <i>want</i> to see the reasoning; too slow for a
    worker waiting on a phone. So the heavy reasoning is moved <b>offline</b>.</p>
  <p>A weekly training pass runs every zone × urgency-state × resistance-profile combination
    (<b>{n_scenarios}</b> scenarios) through the full adversarial loop and distils each into a small,
    <b>pre-validated decision skeleton</b>. At runtime the specialist loads the relevant skeleton and only
    <i>adapts</i> it to today's live data — dates, locations, spray windows — instead of re-deriving it from
    scratch. That cuts a turn from ~47s to ~16s while keeping the adversarial guarantees. (In DEMO mode the
    full live loop still runs, so you can watch every agent think.)</p>

  <h3>Built with Claude Opus 4.8</h3>
  <p>The architecture, every prompt, the eight data integrations, the choropleth mapping, the WhatsApp
    delivery layer, and this page were designed and built iteratively with <b>Claude Opus 4.8</b>
    (<code>claude-opus-4-8</code>) via Claude Code. At runtime the system uses adaptive model tiering — a fast
    model for routing and structured checks, a stronger model for the field reply and the adversarial review —
    streaming throughout so a flaky field connection never leaves a worker staring at silence.</p>

  <p class="sig">A field-worker decision agent for malaria prevention in Mozambique &amp; Malawi — built for
    Goodbye Malaria.</p>
</div></div></section>

<!-- ARCHITECTURE -->
<section id="arch"><div class="wrap">
  <div class="eyebrow">The pipeline</div>
  <h2>One message, six agent roles</h2>
  <p class="sub">Cheap where possible, deep where it counts — and every reply is checked before it ships.</p>
  <div class="flow">
    <div class="node m"><h3>📩 Inbound WhatsApp / web message <span style="font-weight:500;font-size:13px">· any language</span></h3><div class="meta">Twilio / web → FastAPI → per-phone session memory loaded</div></div>
    <div class="arrow">▼</div>
    <div class="node r"><h3>🧭 Router</h3><div class="meta">Structured output: <code>language · intent · intervention · timeline · needs_weather</code></div></div>
    <div class="arrow">▼</div>
    <div class="node d"><h3>🔍 Parallel live-data fetch</h3><div class="meta">8 sources via a thread pool — forecast, archive/breeding-window, flood, ReliefWeb, DHIS2, PMI, WHO, curated KB</div></div>
    <div class="arrow">▼</div>
    <div class="node h"><h3>🛡️ Self-healing data check</h3><div class="meta">Quality report → fallbacks for missing/stale/conflicting sources → uncertainty surfaced to the specialist</div></div>
    <div class="arrow">▼</div>
    <div class="node d"><h3>📋 Enriched situation brief</h3><div class="meta">Urgency + resistance computed deterministically · pre-validated decision skeleton loaded if fresh</div></div>
    <div class="arrow">▼</div>
    <div class="node s"><h3>🩺 Intervention specialist (draft)</h3><div class="meta">1 of {n_spec} expert playbooks · replies in the worker's language</div></div>
    <div class="arrow">▼</div>
    <div class="node a"><h3>⚔️ Adversarial review → orchestrator</h3><div class="meta">Devil's advocate + field realism (parallel) → orchestrator merges into the final reply</div></div>
    <div class="arrow">▼</div>
    <div class="node m"><h3>📤 Final reply + alert choropleth</h3><div class="meta">Streamed back; turn saved to memory</div></div>
  </div>
</div></section>

<!-- LIVE DATA -->
<section id="data" style="background:#fff"><div class="wrap">
  <div class="eyebrow">Live data</div>
  <h2>Grounded in real feeds, not vibes</h2>
  <p class="sub">Eight sources, fetched in parallel. <span class="live">Green</span> = live in this build;
    <span class="heal">healed</span> = currently covered by the self-healing fallback (needs an access key /
    endpoint for full live data).</p>
  <table class="src">
    <tr><th>Source</th><th>What it provides</th><th>How it's used</th><th>Status</th></tr>
    <tr><td><b>WHO GHO</b></td><td>National incidence &amp; estimated cases (2024)</td><td>Cited baseline; disk-cached</td><td class="live">live</td></tr>
    <tr><td><b>Open-Meteo forecast</b></td><td>7-day rain probability</td><td>Spray / larvicide timing → spray-safe days</td><td class="live">live</td></tr>
    <tr><td><b>Open-Meteo archive (90d)</b></td><td>Past daily rainfall</td><td>Breeding-window timeline (eggs → larvae → adults)</td><td class="live">live</td></tr>
    <tr><td><b>GloFAS flood</b></td><td>River discharge vs norm</td><td>Flood-response urgency</td><td class="live">live</td></tr>
    <tr><td><b>PMI FY2024 profiles</b></td><td>Resistance, net/IRS choice, stockout risk</td><td>Operational feasibility + resistance constraints</td><td class="live">live (PDF parse)</td></tr>
    <tr><td><b>ReliefWeb</b></td><td>Humanitarian health alerts (72h)</td><td>Outbreak / displacement signal</td><td class="heal">healed</td></tr>
    <tr><td><b>DHIS2</b></td><td>Weekly case counts + WoW trend</td><td>Earliest outbreak signal</td><td class="heal">healed</td></tr>
    <tr><td><b>Curated KB</b></td><td>Per-zone vectors, season, elevation, alert</td><td>Core reasoning context</td><td class="live">live</td></tr>
  </table>
</div></section>

<!-- SELF-HEALING + ADVERSARIAL -->
<section id="heal"><div class="wrap">
  <div class="eyebrow">Resilience</div>
  <h2>Self-healing &amp; adversarial review</h2>
  <div class="grid2">
    <div class="card">
      <h3>🛡️ Self-healing data layer</h3>
      <p style="font-size:15px;color:var(--muted);margin:0 0 8px">Runs when any source is MISSING / STALE / CONFLICT.</p>
      <ul>
        <li>DHIS2 down → curated alert level as a case-trend proxy (flagged)</li>
        <li>PMI down → last-known resistance from the KB</li>
        <li>ReliefWeb down → assume no alert, and say so</li>
        <li>Conflict → trust district surveillance over the slower feed</li>
      </ul>
    </div>
    <div class="card dark" id="adv">
      <h3>⚔️ Adversarial review</h3>
      <p style="font-size:15px;color:#d8c8b8;margin:0 0 8px">The draft is challenged before it ships.</p>
      <ul>
        <li><b>Devil's advocate</b> — resistance mismatch, timing error, data contradiction</li>
        <li><b>Field realism</b> — specificity, stock, skill level, clarity</li>
        <li><b>Orchestrator</b> — rewrites on a critical challenge; appends fallbacks &amp; escalations</li>
      </ul>
    </div>
  </div>
</div></section>

<!-- DECISION LOGIC -->
<section id="logic" style="background:#fff"><div class="wrap">
  <div class="eyebrow">Decision logic</div>
  <h2>Same question, different ground truth → different answer</h2>
  <div class="grid2">
    <div class="scn">
      <div class="step"><span class="pill">Scenario A</span> active outbreak + flooding</div>
      <p class="q">“It flooded in Chókwè — where should I larvicide, and is it dry enough this week?”</p>
      <div class="step"><b>Brief →</b> Gaza <span class="pill">OUTBREAK</span><span class="pill">FLOOD</span> · breeding window from 90-day archive · resistance: pyrethroid-confirmed</div>
      <div class="step"><b>Devil's advocate →</b> "breeding window already closed — larviciding is too late"</div>
      <div class="step"><b>Final →</b> pivots to ⚡ emergency IRS (Actellic/SumiShield), not a pyrethroid; people-first flood steps</div>
    </div>
    <div class="scn">
      <div class="step"><span class="pill">Scenario B</span> dry-season lull</div>
      <p class="q">“How is the situation in Zomba?”</p>
      <div class="step"><b>Brief →</b> Zomba <span class="pill">NORMAL (dry)</span> + WHO baseline; sources healthy</div>
      <div class="step"><b>Specialist →</b> "planning window, not an emergency" → weights 📅 month / 🌧️ season prep</div>
      <div class="step"><b>Review →</b> approved, no false urgency</div>
    </div>
  </div>
  <p class="sub" style="margin-top:18px">Signals that flip the answer: <span class="tag2">🌧️ weather</span>
    <span class="tag2">🌊 flooding</span> <span class="tag2">📅 season</span>
    <span class="tag2">🧬 resistance</span> <span class="tag2">📈 case trend</span>
    <span class="tag2">📦 stockout risk</span></p>
</div></section>

<!-- MAPPING -->
<section id="maps"><div class="wrap">
  <div class="eyebrow">Mapping</div>
  <h2>Alert-level choropleths</h2>
  <p class="sub">Admin polygons (geoBoundaries) shaded by each zone's current alert — outbreak (red),
    elevated (orange), normal/dry (green) — rendered as a static image for WhatsApp and an interactive
    Leaflet layer. The worker's zone is outlined.</p>
  <div class="maps">
    <figure><img src="/map/gaza" alt="Mozambique alert choropleth" loading="lazy"/><figcaption>Mozambique — Gaza in active outbreak (red).</figcaption></figure>
    <figure><img src="/map/zomba" alt="Malawi alert choropleth" loading="lazy"/><figcaption>Malawi — dry-season lull (green) in the south.</figcaption></figure>
  </div>
</div></section>

<footer><div class="wrap">
  <div class="brand" style="color:#fff;font-size:18px">🦟 Malar<b style="color:var(--amber)">IA</b></div>
  <p>Built with Claude Opus 4.8 for Goodbye Malaria · <a href="/">← back to the main site</a></p>
</div></footer>
</body>
</html>"""
