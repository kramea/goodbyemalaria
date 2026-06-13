"""Public landing page for MalarIA.

A self-contained marketing/education page in the spirit of goodbyemalaria.com:
bold, mission-driven, multilingual, with an African-print-inspired accent palette.

Narrative arc: the reality -> field workers are the heroes -> the toolbox ->
TIMING is decisive (the right tool at the wrong time is wasted) -> it's beatable
(eradicated elsewhere) -> act. Field-worker photos live in /assets and are shown
when present.

Live figures (WHO national baselines + current district alert counts) are injected
from the running system.
"""

from . import data, who
from .config import ROOT

_ASSETS = ROOT / "assets"


def _has(name: str) -> bool:
    return (_ASSETS / name).exists()


def _asset_url(stem: str) -> str:
    """Return the URL for an asset by stem, trying common image extensions."""
    for ext in ("png", "svg", "jpg", "jpeg", "webp"):
        if (_ASSETS / f"{stem}.{ext}").exists():
            return f"/assets/{stem}.{ext}"
    return ""


def _alert_counts() -> dict:
    counts = {"outbreak": 0, "elevated": 0, "normal": 0}
    for key in data.regions():
        a = data.region_alert(key)
        if a in counts:
            counts[a] += 1
    return counts


def render_landing(public_base_url: str = "", whatsapp_number: str = "+1 415 523 8886") -> str:
    counts = _alert_counts()
    who.country_summary("Mozambique")
    who.country_summary("Malawi")
    n_regions = len(data.regions())

    logo_url = _asset_url("goodbye_malaria_logo")
    logo_html = (f'<span class="gm-logo"><img src="{logo_url}" alt="Goodbye Malaria"/></span>'
                 if logo_url else "")

    fw1, fw2 = _asset_url("fieldworker1"), _asset_url("fieldworker2")
    hero_bg = (f",url('{fw2}') center 30%/cover" if fw2
               else (f",url('{fw1}') center/cover" if fw1 else ""))

    # Field-worker photo gallery (graceful if photos not yet added).
    if fw1 or fw2:
        cells = ""
        if fw1:
            cells += (f'<figure><img src="{fw1}" alt="Field worker spraying indoor walls (IRS)"/>'
                      '<figcaption>Indoor residual spraying — coating walls so resting mosquitoes die on contact.</figcaption></figure>')
        if fw2:
            cells += (f'<figure><img src="{fw2}" alt="Field worker treating a home for mosquitoes"/>'
                      '<figcaption>Protecting a household at dusk — the last line between a family and infection.</figcaption></figure>')
        gallery = f'<div class="gallery">{cells}</div>'
    else:
        gallery = ('<div class="gallery placeholder"><div>📷 Add <code>fieldworker1.jpg</code> &amp; '
                   '<code>fieldworker2.jpg</code> to <code>/assets</code> to feature your field-worker photos here.</div></div>')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>MalarIA — the right action, at the right time</title>
<meta name="description" content="Malaria is beatable. In Mozambique and Malawi it still kills. Field workers are the front line — and the right tool at the wrong time saves no one."/>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600;800;900&family=Inter:wght@400;500;600&display=swap" rel="stylesheet"/>
<style>
  :root{{
    --ink:#1c1410; --bg:#fbf6ee; --paper:#ffffff;
    --red:#e23b2e; --red-d:#b62a20; --amber:#f4a92e; --teal:#0f7a6c; --teal-d:#0b5a50;
    --muted:#6b5d52; --line:#e7dccd;
  }}
  *{{box-sizing:border-box}}
  html{{scroll-behavior:smooth}}
  body{{margin:0;font-family:Inter,system-ui,Arial,sans-serif;color:var(--ink);background:var(--bg);line-height:1.6}}
  h1,h2,h3,.brand{{font-family:Montserrat,system-ui,sans-serif;line-height:1.1;letter-spacing:-.02em}}
  a{{color:var(--teal-d)}}
  .wrap{{max-width:1080px;margin:0 auto;padding:0 22px}}
  .pattern{{height:14px;background:
     repeating-linear-gradient(135deg,var(--red) 0 18px,var(--amber) 18px 36px,var(--teal) 36px 54px)}}

  header.nav{{position:sticky;top:0;z-index:50;background:rgba(28,20,16,.96);backdrop-filter:blur(6px)}}
  .nav .wrap{{display:flex;align-items:center;justify-content:space-between;height:62px}}
  .brand{{color:#fff;font-weight:900;font-size:20px}}
  .brand b{{color:var(--amber)}}
  .nav nav a{{color:#f3e9dc;text-decoration:none;margin-left:22px;font-size:14px;font-weight:500;opacity:.9}}
  .nav nav a:hover{{opacity:1;color:#fff}}
  @media(max-width:760px){{.nav nav{{display:none}}}}

  .btn{{display:inline-block;border:0;cursor:pointer;font-family:Montserrat;font-weight:700;
    border-radius:999px;padding:14px 26px;font-size:15px;text-decoration:none;transition:.15s transform}}
  .btn:hover{{transform:translateY(-2px)}}
  .btn-red{{background:var(--red);color:#fff}}
  .btn-ghost{{background:transparent;color:#fff;border:2px solid rgba(255,255,255,.55)}}

  .hero{{position:relative;color:#fff;padding:96px 0 84px;background:
     linear-gradient(160deg,rgba(36,23,16,.82) 0%,rgba(20,14,10,.92) 75%){hero_bg};
     background-position:center;background-size:cover}}
  .hero .kicker{{color:var(--amber);font-weight:700;letter-spacing:.18em;text-transform:uppercase;font-size:13px}}
  .hero h1{{font-size:clamp(34px,6vw,64px);font-weight:900;margin:14px 0 16px}}
  .hero h1 em{{color:var(--red);font-style:normal}}
  .hero p.lede{{font-size:clamp(17px,2.2vw,21px);color:#efe4d6;max-width:640px;margin:0 0 28px}}
  .hero .ctas{{display:flex;gap:14px;flex-wrap:wrap}}
  .goodbye{{margin-top:34px;color:#d7c9ba;font-size:14px}}
  .goodbye b{{color:#fff}}

  section{{padding:66px 0}}
  .eyebrow{{color:var(--red-d);font-weight:700;letter-spacing:.14em;text-transform:uppercase;font-size:13px}}
  h2{{font-size:clamp(26px,4vw,40px);font-weight:800;margin:8px 0 14px}}
  .sub{{color:var(--muted);max-width:700px;font-size:17px}}

  .stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin-top:34px}}
  @media(max-width:860px){{.stats{{grid-template-columns:repeat(2,1fr)}}}}
  .stat{{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:22px}}
  .stat .n{{font-family:Montserrat;font-weight:900;font-size:38px;color:var(--red);line-height:1}}
  .stat .l{{margin-top:8px;font-size:14px;color:var(--muted)}}
  .stat.t .n{{color:var(--teal)}}

  /* field workers */
  .heroes{{background:#241712;color:#f3e9dc}}
  .gallery{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:30px}}
  @media(max-width:760px){{.gallery{{grid-template-columns:1fr}}}}
  .gallery figure{{margin:0;border-radius:16px;overflow:hidden;background:#170f0a;border:1px solid #3a2a20}}
  .gallery img{{width:100%;height:300px;object-fit:cover;display:block}}
  .gallery figcaption{{padding:13px 16px;font-size:13.5px;color:#d8c8b8}}
  .gallery.placeholder{{grid-template-columns:1fr}}
  .gallery.placeholder div{{padding:40px;border:1px dashed #5a4636;border-radius:16px;color:#cdbfb0;text-align:center}}
  .gallery.placeholder code{{color:var(--amber)}}

  .pull{{background:linear-gradient(160deg,var(--red),var(--red-d));color:#fff}}
  .pull .wrap{{text-align:center}}
  .pull .q{{font-family:Montserrat;font-weight:900;font-size:clamp(26px,4.6vw,46px);line-height:1.12;max-width:900px;margin:0 auto}}
  .pull .q small{{display:block;font-family:Inter;font-weight:500;font-size:17px;opacity:.92;margin-top:18px}}

  .split{{display:grid;grid-template-columns:1fr 1fr;gap:30px;align-items:center}}
  @media(max-width:820px){{.split{{grid-template-columns:1fr}}}}
  .card{{background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:26px}}
  .card.dark{{background:#241712;color:#f3e9dc;border:0}}
  .card.dark h3{{color:#fff}}

  .free-list{{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}}
  .chip{{background:#eaf4f1;color:var(--teal-d);border:1px solid #cfe6e0;border-radius:999px;padding:6px 13px;font-size:13px;font-weight:600}}

  .tl{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:30px}}
  @media(max-width:860px){{.tl{{grid-template-columns:1fr}}}}
  .tl .col{{background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:22px;border-top:6px solid var(--red)}}
  .tl .col.m{{border-top-color:var(--amber)}}
  .tl .col.s{{border-top-color:var(--teal)}}
  .tl h3{{font-size:19px;margin:6px 0 4px}}
  .tl .when{{font-size:13px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.08em}}
  .tl ul{{margin:14px 0 0;padding-left:18px}} .tl li{{margin:7px 0;font-size:15px}}

  .factors{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:30px}}
  @media(max-width:860px){{.factors{{grid-template-columns:repeat(2,1fr)}}}}
  .factor{{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:20px}}
  .factor .ico{{font-size:26px}} .factor h3{{font-size:17px;margin:10px 0 4px}}
  .factor p{{margin:0;font-size:14px;color:var(--muted)}}

  .langs-sec{{background:#241712;color:#f3e9dc}}
  .langs{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:30px}}
  @media(max-width:860px){{.langs{{grid-template-columns:repeat(2,1fr)}}}}
  .lang{{background:#170f0a;border:1px solid #3a2a20;border-left:5px solid var(--amber);border-radius:14px;padding:18px}}
  .lang .ln{{font-family:Montserrat;font-weight:800;font-size:17px;color:#fff}}
  .lang .ex{{margin-top:10px;font-size:14.5px;color:#d8c8b8;font-style:italic}}

  .live{{display:inline-flex;gap:10px;align-items:center;background:#241712;color:#fff;border-radius:999px;
    padding:8px 16px;font-size:13px;font-weight:600;margin-top:26px}}
  .dot{{width:9px;height:9px;border-radius:50%;background:var(--red);animation:p 1.6s infinite}}
  @keyframes p{{0%{{box-shadow:0 0 0 0 rgba(226,59,46,.55)}}70%{{box-shadow:0 0 0 10px rgba(226,59,46,0)}}100%{{box-shadow:0 0 0 0 rgba(226,59,46,0)}}}}

  .cta{{background:linear-gradient(160deg,#0f7a6c,#0b5a50);color:#fff;border-radius:22px;padding:44px;text-align:center}}
  .cta h2{{color:#fff}} .cta p{{color:#dff1ec;max-width:620px;margin:0 auto 24px}}

  .team{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:28px}}
  @media(max-width:760px){{.team{{grid-template-columns:1fr}}}}
  .member{{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:24px;text-align:center}}
  .member .mname{{font-family:Montserrat;font-weight:800;font-size:19px}}
  .member .mrole{{font-size:13px;color:var(--muted);margin-top:4px}}
  .gm-logo{{display:inline-block;background:#fff;border-radius:10px;padding:9px 14px;vertical-align:middle;margin-left:8px}}
  .gm-logo img{{height:34px;display:block}}

  footer{{background:#1c1410;color:#cdbfb0;padding:46px 0;font-size:13px}}
  footer a{{color:var(--amber)}}
  footer .src{{color:#9b8a7c;margin-top:10px;line-height:1.7}}
  .reveal{{opacity:0;transform:translateY(16px);transition:.6s ease}} .reveal.in{{opacity:1;transform:none}}
</style>
</head>
<body>
<div class="pattern"></div>
<header class="nav"><div class="wrap">
  <div class="brand">🦟 Malar<b>IA</b></div>
  <nav>
    <a href="#reality">The reality</a>
    <a href="#heroes">Field workers</a>
    <a href="#interventions">Interventions</a>
    <a href="#timing">Timing</a>
    <a href="#languages">Languages</a>
    <a href="#beatable">Beatable</a>
    <a href="/tech">How it works</a>
    <a href="/chat">💬 Chat</a>
    <a href="#try">Try it</a>
  </nav>
</div></header>

<!-- HERO -->
<section class="hero"><div class="wrap">
  <div class="kicker">A field-worker decision agent for malaria prevention</div>
  <h1>Malaria is beatable.<br/><em>Timing is everything.</em></h1>
  <p class="lede">It's curable, preventable, and already gone from dozens of countries. In Mozambique and
    Malawi it still kills every day — and on the ground the difference is doing the <b>right thing at the
    right moment</b>, before the mosquitoes win.</p>
  <div class="ctas">
    <a class="btn btn-red" href="/chat">💬 Chat with MalarIA now</a>
    <a class="btn btn-ghost" href="/coming-soon">Or use WhatsApp</a>
  </div>
  <div class="goodbye">Together we can say <b>goodbye</b> — <b>tchau tchau</b> — <b>au revoir</b> — <b>tsalani bwino</b> — to malaria.</div>
</div></section>

<!-- THE REALITY -->
<section id="reality"><div class="wrap">
  <div class="eyebrow">The reality</div>
  <h2>A preventable disease, still taking lives</h2>
  <p class="sub">Malaria is curable and preventable — yet it remains one of the deadliest diseases on Earth,
    and sub-Saharan Africa carries almost the entire burden.</p>
  <div class="stats">
    <div class="stat"><div class="n">263M</div><div class="l">malaria cases worldwide in 2023 (WHO)</div></div>
    <div class="stat"><div class="n">~597K</div><div class="l">deaths in 2023 — mostly children under 5</div></div>
    <div class="stat"><div class="n">~95%</div><div class="l">of all cases &amp; deaths are in the WHO African Region</div></div>
    <div class="stat"><div class="n">#1</div><div class="l">the mosquito is the deadliest animal on the planet</div></div>
  </div>
  <div class="stats">
    <div class="stat"><div class="n">10.2M</div><div class="l">estimated cases/yr in <b>Mozambique</b> — 295 per 1,000 at risk (WHO GHO, 2024)</div></div>
    <div class="stat"><div class="n">6.4M</div><div class="l">estimated cases/yr in <b>Malawi</b> — 295 per 1,000 at risk (WHO GHO, 2024)</div></div>
    <div class="stat t"><div class="n">4 in 5</div><div class="l">malaria deaths in Africa are children under five</div></div>
    <div class="stat t"><div class="n">{n_regions}</div><div class="l">sub-national zones MalarIA tracks live across both countries</div></div>
  </div>
</div></section>

<div class="pattern"></div>

<!-- FIELD WORKERS -->
<section id="heroes" class="heroes"><div class="wrap">
  <div class="eyebrow" style="color:var(--amber)">The front line</div>
  <h2 style="color:#fff">The most important soldier against malaria<br/>is the field worker.</h2>
  <p class="sub" style="color:#d8c8b8;max-width:780px">No lab, no policy, no app stops a single case on its own.
    Prevention happens when a field worker reaches a village, reads the ground, and acts — spraying a wall,
    treating a pool of water, hanging a net — at exactly the moment it counts. They walk the last mile, in the
    heat and the rain, carrying the entire fight on their backs.</p>
  {gallery}
  <p class="sub" style="color:#d8c8b8;max-width:780px;margin-top:26px">Every one of these actions only works in a
    narrow window. Get there in time and a village is protected. Arrive late — after the rains, after the hatch,
    after the peak — and the very same effort is wasted. <b style="color:#fff">MalarIA exists to make sure the
    field worker always knows the window.</b></p>
</div></section>

<!-- INTERVENTIONS -->
<section id="interventions"><div class="wrap">
  <div class="eyebrow">The toolbox</div>
  <h2>Many interventions — each with its moment</h2>
  <p class="sub">Vector control isn't one tool, it's a sequence matched to the horizon. MalarIA routes every
    field question to the right one.</p>
  <div class="tl">
    <div class="col">
      <div class="when">⚡ Immediate · hours–days</div>
      <h3>Stop transmission now</h3>
      <ul>
        <li><b>Larviciding (Bti)</b> — kill larvae in new standing water; resistance-proof</li>
        <li><b>Emergency IRS</b> — rapid indoor spraying (Actellic, SumiShield)</li>
        <li><b>Larval source management</b> — drain &amp; fill breeding sites</li>
        <li><b>Spatial repellents</b> — a bridge while teams mobilise</li>
      </ul>
    </div>
    <div class="col m">
      <div class="when">📅 Month ahead · weeks</div>
      <h3>Build the shield</h3>
      <ul>
        <li><b>ITN / LLIN nets</b> — dual-active (Interceptor G2) where resistance is confirmed</li>
        <li><b>Eave tubes</b> — bypass pyrethroid resistance (50–70% fewer mosquitoes indoors)</li>
        <li><b>Chemoprevention</b> — SMC for under-5s, IPTp in pregnancy</li>
        <li><b>House screening</b> — close the entry points</li>
      </ul>
    </div>
    <div class="col s">
      <div class="when">🌧️ Season ahead · months</div>
      <h3>Plan the campaign</h3>
      <ul>
        <li><b>Annual IRS</b> — finish before the wet-season peak</li>
        <li><b>Resistance monitoring</b> — sets next year's insecticide</li>
        <li><b>Vaccine (RTS,S / R21)</b> — through routine immunisation</li>
        <li><b>Housing &amp; livestock measures</b> — durable, structural gains</li>
      </ul>
    </div>
  </div>
</div></section>

<!-- PULL QUOTE: the core message -->
<section class="pull"><div class="wrap">
  <p class="q">The right tool at the wrong time saves no one.
    <small>Spray before the rains and it washes off. Hand out nets after the peak and the cases already happened.
      Timing is not a detail — it <i>is</i> the intervention.</small></p>
</div></section>

<!-- TIMING -->
<section id="timing"><div class="wrap">
  <div class="eyebrow">Why timing wins</div>
  <h2>The same tool can save a village — or be wasted</h2>
  <p class="sub">Whether an intervention works depends on conditions that change week to week. These are exactly
    what MalarIA reasons over, live, so the field worker acts inside the window — not outside it.</p>
  <div class="factors">
    <div class="factor"><div class="ico">🌧️</div><h3>Weather</h3><p>Spray on dry days — rain washes fresh insecticide off the walls. MalarIA checks the live forecast first.</p></div>
    <div class="factor"><div class="ico">🌊</div><h3>Ground &amp; flooding</h3><p>New standing water breeds mosquitoes within days — larviciding must land within ~48h of a flood.</p></div>
    <div class="factor"><div class="ico">📅</div><h3>Season</h3><p>An IRS campaign must finish before the transmission peak. A few weeks late misses the window entirely.</p></div>
    <div class="factor"><div class="ico">🧬</div><h3>Resistance</h3><p>Where pyrethroids fail, a standard net does little. The tool has to match the local vector.</p></div>
  </div>
  <div class="live"><span class="dot"></span> Live now: {counts['outbreak']} zone(s) in active outbreak · {counts['elevated']} elevated · {counts['normal']} in dry-season lull</div>
</div></section>

<!-- LANGUAGES -->
<section id="languages" class="langs-sec"><div class="wrap">
  <div class="eyebrow" style="color:var(--amber)">Speaks their language</div>
  <h2 style="color:#fff">Every field worker, in their own words</h2>
  <p class="sub" style="color:#e3d6c6;max-width:780px">Across Mozambique and Malawi, field workers speak many
    languages. MalarIA <b style="color:#fff">auto-detects the language of the very first message</b> and replies
    entirely in it — no menus, no English-only barrier — then stays in that language for the whole conversation.</p>
  <div class="langs">
    <div class="lang"><div class="ln">🇲🇿 Português</div><div class="ex">“Qual é a situação da malária em Beira?”</div></div>
    <div class="lang"><div class="ln">🇲🇼 Chichewa</div><div class="ex">“Kodi udzudzu uli bwanji ku Zomba?”</div></div>
    <div class="lang"><div class="ln">🌍 English</div><div class="ex">“How is the situation in Maputo?”</div></div>
    <div class="lang"><div class="ln">🇫🇷 Français</div><div class="ex">“Quelle est la situation du paludisme ?”</div></div>
  </div>
  <p class="sub" style="color:#e3d6c6;max-width:780px;margin-top:24px">It judges language by the words written —
    not the country — and uses correct local malaria terminology (in Chichewa: <i>malungo</i>, <i>udzudzu</i>,
    <i>tsambatsi</i>). The right advice means nothing if the worker can't read it.</p>
</div></section>

<div class="pattern"></div>

<!-- BEATABLE (moved to a hopeful close) -->
<section id="beatable"><div class="wrap">
  <div class="eyebrow">It's beatable — proven</div>
  <h2>Eradicated there. We can end it here.</h2>
  <div class="split">
    <div>
      <p class="sub">Over <b>40 countries and territories</b> have been certified malaria-free by the WHO —
        proof that with sustained, well-timed action, malaria ends. The tools work. The science is settled.
        What's left is execution on the ground, season after season — by field workers.</p>
      <div class="free-list">
        <span class="chip">China · 2021</span>
        <span class="chip">El Salvador · 2021</span>
        <span class="chip">Algeria · 2019</span>
        <span class="chip">Argentina · 2019</span>
        <span class="chip">Cabo Verde · 2024</span>
        <span class="chip">Egypt · 2024</span>
        <span class="chip">+ 35 more</span>
      </div>
    </div>
    <div class="card dark">
      <h3>So why does it still kill here?</h3>
      <p>Because in high-burden zones the fight is relentless: heavy rains create new breeding sites in days,
        mosquitoes grow resistant to insecticides, and a campaign that lands a few weeks late misses the peak.
        <b>Elimination isn't a single act — it's the right intervention, in the right place, at the right time,
        every time.</b> That's a problem of timing and reach. That's the problem MalarIA helps solve.</p>
    </div>
  </div>
</div></section>

<!-- CTA -->
<section id="try"><div class="wrap">
  <div class="cta">
    <h2>Put MalarIA in your pocket</h2>
    <p>Ask about your district in English, Portuguese, French or Chichewa — get the situation now,
      the right intervention, and whether the weather will hold, in seconds. Chat right here in your
      browser, or message it on WhatsApp.</p>
    <a class="btn btn-red" href="/chat">💬 Chat in your browser</a>
    <a class="btn btn-ghost" href="/coming-soon" style="margin-left:10px">Message on WhatsApp</a>
  </div>
</div></section>

<!-- TEAM -->
<section id="team"><div class="wrap">
  <div class="eyebrow">The team</div>
  <h2>Built by</h2>
  <div class="team">
    <div class="member"><div class="mname">Kalai Ramea</div></div>
    <div class="member"><div class="mname">Mike Mpanya</div></div>
    <div class="member"><div class="mname">Sherwin Charles</div></div>
  </div>
</div></section>

<footer><div class="wrap">
  <div class="brand" style="color:#fff;font-size:18px">🦟 Malar<b style="color:var(--amber)">IA</b></div>
  <p style="display:flex;align-items:center;flex-wrap:wrap;gap:4px">A field-worker decision agent for malaria prevention in Mozambique &amp; Malawi — built for <b>Goodbye Malaria</b>.{logo_html}</p>
  <p><a href="/tech">⚙️ How it works — the technical details →</a></p>
  <p class="src">Sources: WHO World Malaria Report 2024 (global cases, deaths, regional burden);
    WHO Global Health Observatory, 2024 (Mozambique &amp; Malawi national estimates); WHO list of
    malaria-free certified countries. Figures are approximate and for demonstration; validate against
    live national surveillance before operational use.</p>
</div></footer>

<script>
  const io=new IntersectionObserver(es=>es.forEach(e=>{{if(e.isIntersecting)e.target.classList.add('in')}}),{{threshold:.12}});
  document.querySelectorAll('section .wrap > *').forEach((el,i)=>{{el.classList.add('reveal');el.style.transitionDelay=(i%4*40)+'ms';io.observe(el)}});
</script>
</body>
</html>"""


def render_coming_soon() -> str:
    """Lightweight 'WhatsApp coming soon' page, on-theme, links back to web chat."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>MalarIA — WhatsApp coming soon</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;800;900&family=Inter:wght@400;500;600&display=swap" rel="stylesheet"/>
<style>
  :root{--ink:#1c1410;--red:#e23b2e;--amber:#f4a92e;--teal:#0f7a6c;--teal-d:#0b5a50;--muted:#e9ddcd}
  *{box-sizing:border-box}
  body{margin:0;min-height:100dvh;font-family:Inter,system-ui,Arial,sans-serif;color:#fff;
    background:linear-gradient(160deg,#241712,#140e0a);display:flex;flex-direction:column}
  .pattern{height:10px;background:repeating-linear-gradient(135deg,var(--red) 0 18px,var(--amber) 18px 36px,var(--teal) 36px 54px)}
  .wrap{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;
    text-align:center;padding:40px 22px;max-width:640px;margin:0 auto}
  .mosq{font-size:64px;margin-bottom:8px}
  .kicker{color:var(--amber);font-weight:700;letter-spacing:.18em;text-transform:uppercase;font-size:13px}
  h1{font-family:Montserrat;font-weight:900;font-size:clamp(30px,6vw,52px);line-height:1.08;margin:14px 0 16px}
  h1 em{color:var(--amber);font-style:normal}
  p{color:var(--muted);font-size:18px;line-height:1.6;max-width:520px}
  .btns{display:flex;gap:14px;flex-wrap:wrap;justify-content:center;margin-top:30px}
  .btn{display:inline-block;font-family:Montserrat;font-weight:700;border-radius:999px;
    padding:14px 26px;font-size:15px;text-decoration:none;transition:.15s transform}
  .btn:hover{transform:translateY(-2px)}
  .btn-red{background:var(--red);color:#fff}
  .btn-ghost{background:transparent;color:#fff;border:2px solid rgba(255,255,255,.5)}
  .note{margin-top:30px;font-size:13.5px;color:#bda9}
</style>
</head>
<body>
<div class="pattern"></div>
<div class="wrap">
  <div class="mosq">🦟</div>
  <div class="kicker">MalarIA on WhatsApp</div>
  <h1>Coming <em>soon!</em></h1>
  <p>We're setting up MalarIA's dedicated WhatsApp line for field workers in Mozambique
     and Malawi. In the meantime, you can talk to the very same agent right now in your browser.</p>
  <div class="btns">
    <a class="btn btn-red" href="/chat">💬 Chat with MalarIA now</a>
    <a class="btn btn-ghost" href="/">← Back home</a>
  </div>
  <div class="note">Same agent · same live data · same languages — just over the web for now.</div>
</div>
<div class="pattern"></div>
</body>
</html>"""
