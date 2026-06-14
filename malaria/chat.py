"""Web chat page for MalarIA — a WhatsApp-style UI that mirrors the real
conversation.

It talks to the same `/message` JSON endpoint the WhatsApp webhook uses, so the
replies, the router→specialist routing, the language locking, the live data and
the map-on-first/closing behaviour are all identical — just over the browser
instead of Twilio (so it's free of the sandbox's daily message cap).

A per-browser id is kept in localStorage so the conversation has memory across
turns and reloads; "Start over" clears it for a fresh greeting.
"""


def render_chat(public_base_url: str = "", whatsapp_number: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>MalarIA — chat</title>
<meta name="description" content="Chat with MalarIA — the field-worker malaria-prevention decision agent. Same agent as WhatsApp, in your browser."/>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;800;900&family=Inter:wght@400;500;600&display=swap" rel="stylesheet"/>
<style>
  :root{{
    --ink:#1c1410; --bg:#fbf6ee; --red:#e23b2e; --amber:#f4a92e;
    --teal:#0f7a6c; --teal-d:#0b5a50; --muted:#6b5d52; --line:#e7dccd;
    --wa-bg:#e7ddd0; --in:#ffffff; --out:#d6f3c9;
  }}
  *{{box-sizing:border-box}}
  html,body{{height:100%}}
  body{{margin:0;font-family:Inter,system-ui,Arial,sans-serif;color:var(--ink);
    background:var(--bg);display:flex;flex-direction:column;height:100dvh}}
  a{{color:var(--teal-d)}}
  .pattern{{height:8px;flex:0 0 auto;background:
     repeating-linear-gradient(135deg,var(--red) 0 18px,var(--amber) 18px 36px,var(--teal) 36px 54px)}}

  /* header */
  header{{flex:0 0 auto;background:#241712;color:#fff;display:flex;align-items:center;
    gap:12px;padding:11px 16px}}
  header .av{{width:42px;height:42px;border-radius:50%;background:var(--teal);
    display:grid;place-items:center;font-size:22px;flex:0 0 auto}}
  header .who{{flex:1;min-width:0}}
  header .nm{{font-family:Montserrat;font-weight:800;font-size:17px;line-height:1.1}}
  header .nm b{{color:var(--amber)}}
  header .st{{font-size:12px;color:#bda;opacity:.85;display:flex;align-items:center;gap:6px}}
  header .st .g{{width:8px;height:8px;border-radius:50%;background:#46d369;display:inline-block}}
  header a.home{{color:#e9ddcd;text-decoration:none;font-size:13px;font-weight:600;
    border:1px solid rgba(255,255,255,.3);border-radius:999px;padding:6px 12px;white-space:nowrap}}
  header a.home:hover{{background:rgba(255,255,255,.1)}}

  /* conversation */
  .feed{{flex:1 1 auto;overflow-y:auto;padding:18px 14px 8px;background:var(--wa-bg);
    background-image:radial-gradient(rgba(0,0,0,.025) 1px,transparent 1px);background-size:22px 22px}}
  .feed .inner{{max-width:680px;margin:0 auto;display:flex;flex-direction:column;gap:8px}}
  .row{{display:flex}}
  .row.me{{justify-content:flex-end}}
  .bub{{max-width:82%;padding:9px 12px;border-radius:12px;font-size:15px;line-height:1.5;
    box-shadow:0 1px 1px rgba(0,0,0,.08);white-space:pre-wrap;word-wrap:break-word;position:relative}}
  .row.them .bub{{background:var(--in);border-top-left-radius:3px}}
  .row.me .bub{{background:var(--out);border-top-right-radius:3px}}
  .bub strong{{font-weight:700}}
  .bub a{{color:var(--teal-d);word-break:break-all}}
  .bub img{{display:block;margin-top:8px;border-radius:10px;max-width:100%;border:1px solid var(--line)}}
  .bub .t{{display:block;text-align:right;font-size:10.5px;color:var(--muted);margin-top:4px}}
  .sys{{align-self:center;background:rgba(0,0,0,.06);color:#5a4a3c;font-size:12px;
    border-radius:8px;padding:5px 12px;margin:4px 0}}

  /* typing */
  .typing{{display:inline-flex;gap:4px;align-items:center;padding:4px 2px}}
  .typing i{{width:8px;height:8px;border-radius:50%;background:#9a8b7d;display:inline-block;
    animation:bl 1.2s infinite}}
  .typing i:nth-child(2){{animation-delay:.2s}} .typing i:nth-child(3){{animation-delay:.4s}}
  @keyframes bl{{0%,60%,100%{{opacity:.3;transform:translateY(0)}}30%{{opacity:1;transform:translateY(-3px)}}}}

  /* suggestion chips */
  .chips{{max-width:680px;margin:0 auto;padding:8px 14px 0;display:flex;gap:8px;flex-wrap:wrap;flex:0 0 auto;background:var(--wa-bg)}}
  .chip{{background:#fff;border:1px solid var(--line);color:var(--teal-d);border-radius:999px;
    padding:7px 13px;font-size:13px;font-weight:600;cursor:pointer;transition:.12s}}
  .chip:hover{{background:#eaf4f1;transform:translateY(-1px)}}

  /* composer */
  .composer{{flex:0 0 auto;background:#f3ece1;border-top:1px solid var(--line);
    padding:10px 14px;display:flex;gap:10px;align-items:flex-end}}
  .composer .box{{max-width:680px;margin:0 auto;width:100%;display:flex;gap:10px;align-items:flex-end}}
  .composer textarea{{flex:1;resize:none;border:1px solid var(--line);border-radius:22px;
    padding:11px 16px;font-family:inherit;font-size:15px;max-height:120px;outline:none;background:#fff}}
  .composer textarea:focus{{border-color:var(--teal)}}
  .send{{flex:0 0 auto;width:46px;height:46px;border-radius:50%;border:0;background:var(--teal);
    color:#fff;font-size:20px;cursor:pointer;display:grid;place-items:center;transition:.12s}}
  .send:hover{{background:var(--teal-d)}}
  .send:disabled{{opacity:.5;cursor:default}}
  .reset{{background:none;border:0;color:var(--muted);font-size:12px;cursor:pointer;text-decoration:underline}}
  .footnote{{flex:0 0 auto;text-align:center;font-size:11.5px;color:var(--muted);padding:6px 10px;background:#f3ece1}}
</style>
</head>
<body>
<div class="pattern"></div>
<header>
  <div class="av">🦟</div>
  <div class="who">
    <div class="nm">Malar<b>IA</b></div>
    <div class="st"><span class="g"></span> online · field-worker decision agent</div>
  </div>
  <a class="home" href="/">← Home</a>
</header>

<div class="feed" id="feed"><div class="inner" id="inner"></div></div>

<div class="chips" id="chips">
  <button class="chip" data-q="How is the malaria situation in Maputo?">How is it in Maputo?</button>
  <button class="chip" data-q="I want to spray tomorrow in Gaza — will it rain there?">Spray tomorrow — will it rain?</button>
  <button class="chip" data-q="Qual é a situação da malária na Beira?">🇲🇿 Situação na Beira?</button>
  <button class="chip" data-q="Kodi udzudzu uli bwanji ku Zomba?">🇲🇼 Udzudzu ku Zomba?</button>
</div>

<div class="composer"><div class="box">
  <textarea id="inp" rows="1" placeholder="Message MalarIA…" autocomplete="off"></textarea>
  <button class="send" id="send" title="Send">➤</button>
</div></div>
<div class="footnote">Field-worker malaria decision agent · <button class="reset" id="reset">Start over</button> · WhatsApp coming soon</div>

<script>
(function(){{
  const feed=document.getElementById('feed'), inner=document.getElementById('inner');
  const inp=document.getElementById('inp'), send=document.getElementById('send');
  const chips=document.getElementById('chips');

  // Stable per-browser id so the agent keeps conversation memory across turns/reloads.
  function newId(){{ return 'web:'+Math.random().toString(36).slice(2)+Date.now().toString(36); }}
  let phone=localStorage.getItem('malaria_chat_id');
  if(!phone){{ phone=newId(); localStorage.setItem('malaria_chat_id',phone); }}

  function scroll(){{ feed.scrollTop=feed.scrollHeight; }}
  function now(){{ const d=new Date(); return d.getHours().toString().padStart(2,'0')+':'+d.getMinutes().toString().padStart(2,'0'); }}

  function esc(s){{ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
  // WhatsApp-ish formatting: *bold*, linkify URLs, newlines preserved by CSS.
  function fmt(s){{
    let h=esc(s);
    h=h.replace(/(https?:\\/\\/[^\\s]+)/g,'<a href="$1" target="_blank" rel="noopener">$1</a>');
    h=h.replace(/\\*([^*\\n]+)\\*/g,'<strong>$1</strong>');
    return h;
  }}

  function bubble(who,html,withTime){{
    const row=document.createElement('div'); row.className='row '+who;
    const b=document.createElement('div'); b.className='bub'; b.innerHTML=html;
    if(withTime){{ const t=document.createElement('span'); t.className='t'; t.textContent=now(); b.appendChild(t); }}
    row.appendChild(b); inner.appendChild(row); scroll(); return b;
  }}
  function sys(txt){{ const d=document.createElement('div'); d.className='sys'; d.textContent=txt; inner.appendChild(d); scroll(); }}

  function greet(){{
    bubble('them',
      '🦟 <strong>MalarIA</strong><br>Hello! I help field workers pick the right malaria intervention at the right time. '
      +'Ask me about any district in Mozambique or Malawi — in English, Português, Français or Chichewa.'
      +'<br><br>Olá! · Bonjour! · Moni!', true);
  }}

  let busy=false, hintEl=null, inflight=null, turnSeq=0;
  function setBusy(b){{ busy=b; send.disabled=b; inp.disabled=b; }}
  function flashHint(){{
    if(hintEl) return;
    hintEl=document.createElement('div'); hintEl.className='sys';
    hintEl.textContent='⏳ Still answering your last message — one sec…';
    inner.appendChild(hintEl); scroll();
    setTimeout(()=>{{ if(hintEl){{ hintEl.remove(); hintEl=null; }} }}, 1800);
  }}
  // Cancel any in-flight turn and clear all transient state (used by "Start over").
  function resetState(){{
    turnSeq++;                                  // invalidate the running turn's result
    if(inflight){{ try{{ inflight.abort(); }}catch(_){{}} inflight=null; }}
    if(hintEl){{ hintEl.remove(); hintEl=null; }}
    setBusy(false);
  }}

  async function ask(text){{
    text=(text||'').trim();
    if(!text) return;
    if(busy){{ flashHint(); return; }}   // block + visibly tell the user we're still working
    const myTurn=++turnSeq;              // tag this turn so a later "start over" can discard it
    const myPhone=phone;                 // pin the conversation this turn belongs to
    setBusy(true); chips.style.display='none';
    bubble('me', fmt(text), true);
    inp.value=''; inp.style.height='auto';
    const typingRow=document.createElement('div'); typingRow.className='row them';
    typingRow.innerHTML='<div class="bub"><span class="typing"><i></i><i></i><i></i></span></div>';
    inner.appendChild(typingRow); scroll();
    const ctrl=new AbortController(); inflight=ctrl;
    const timer=setTimeout(()=>ctrl.abort(), 75000);   // never spin forever
    try{{
      const r=await fetch('/message',{{method:'POST',headers:{{'content-type':'application/json'}},
        body:JSON.stringify({{phone:myPhone,message:text}}), signal:ctrl.signal}});
      let j=null, raw='';
      try{{ j=await r.json(); }}catch(_){{ try{{ raw=await r.text(); }}catch(_2){{}} }}
      if(myTurn!==turnSeq) return;       // user started over while we waited → drop this result
      if(j && j.reply!=null){{
        let html=fmt(j.reply);
        if(j.map_url){{ html+='<img src="'+j.map_url+'" alt="alert map" loading="lazy"/>'; }}
        const b=bubble('them', html, true);
        const img=b.querySelector('img'); if(img){{ img.onload=scroll; img.onerror=scroll; }}
      }}else if(j && j.error){{
        sys('⚠️ '+j.error);
      }}else{{
        sys('⚠️ Unexpected response ('+r.status+'). '+(raw?raw.slice(0,140):''));
      }}
    }}catch(e){{
      if(myTurn===turnSeq){{           // ignore aborts caused by "start over"
        sys(e.name==='AbortError' ? '⏱️ That took too long — please send it again.'
                                  : '⚠️ Network error — please try again. '+e);
      }}
    }}finally{{
      clearTimeout(timer);
      if(inflight===ctrl) inflight=null;
      typingRow.remove();              // ALWAYS clear this turn's dots
      if(myTurn===turnSeq){{ setBusy(false); inp.focus(); scroll(); }}  // only if still the active turn
    }}
  }}

  send.addEventListener('click',()=>ask(inp.value));
  inp.addEventListener('keydown',e=>{{ if(e.key==='Enter' && !e.shiftKey){{ e.preventDefault(); ask(inp.value); }} }});
  inp.addEventListener('input',()=>{{ inp.style.height='auto'; inp.style.height=Math.min(inp.scrollHeight,120)+'px'; }});
  chips.querySelectorAll('.chip').forEach(c=>c.addEventListener('click',()=>ask(c.dataset.q)));
  document.getElementById('reset').addEventListener('click',()=>{{
    resetState();                       // abort in-flight + unlock + clear dots BEFORE wiping the UI
    phone=newId(); localStorage.setItem('malaria_chat_id',phone);
    inner.innerHTML=''; chips.style.display='flex'; greet();
  }});

  greet(); inp.focus();
}})();
</script>
</body>
</html>"""
