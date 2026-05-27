"""Playwright-style HTML trace viewer for collection run results.

Generates a self-contained HTML file with embedded CSS and JS that
displays a timeline waterfall, click-to-expand request details,
assertion pass/fail, and timing breakdown.
"""

from __future__ import annotations

import html
import json


def generate_trace_html(
    collection_name: str,
    results: list[dict],
    elapsed_ms: float,
) -> str:
    """Return a self-contained HTML string visualizing a collection run.

    Parameters
    ----------
    collection_name:
        Human-readable name shown in the header.
    results:
        List of dicts matching ``RunRequestResult`` schema — each must
        include ``request_name``, ``method``, ``url``, ``status``,
        ``elapsed_ms``, ``error``, and optionally ``assertion_results``.
    elapsed_ms:
        Total wall-clock time for the whole run.
    """
    total = len(results)
    passed = sum(
        1 for r in results
        if r.get("status") is not None and r.get("error") is None
    )
    failed = total - passed

    # Compute max elapsed for scaling waterfall bars.
    max_elapsed = max((r.get("elapsed_ms", 0) for r in results), default=1) or 1

    # Embed results data as JSON for the JS side.
    data_json = json.dumps(
        {
            "collection_name": collection_name,
            "results": results,
            "elapsed_ms": elapsed_ms,
            "total": total,
            "passed": passed,
            "failed": failed,
            "max_elapsed": max_elapsed,
        },
        ensure_ascii=False,
    )

    return _TEMPLATE.replace("/* __DATA__ */", html.escape(data_json, quote=False))


_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Theridion Trace</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
background:#0a0a0a;color:#e5e5e5;padding:1rem}
.header{padding:1rem 1.5rem;border-radius:8px;background:#171717;
margin-bottom:1rem;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem}
.header h1{font-size:1.25rem;font-weight:600}
.header .stats{display:flex;gap:1rem;font-size:.875rem}
.badge{padding:2px 8px;border-radius:4px;font-weight:600}
.badge-pass{background:#065f46;color:#6ee7b7}
.badge-fail{background:#7f1d1d;color:#fca5a5}
.badge-time{background:#1e3a5f;color:#93c5fd}
.waterfall{display:flex;flex-direction:column;gap:2px;margin-bottom:1rem}
.bar-row{display:flex;align-items:center;gap:.5rem;padding:.25rem .5rem;
border-radius:4px;background:#171717;cursor:pointer;transition:background .15s}
.bar-row:hover{background:#262626}
.bar-label{min-width:200px;max-width:300px;font-size:.8125rem;overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}
.bar-method{font-weight:700;margin-right:.25rem;font-size:.75rem}
.bar-track{flex:1;height:20px;background:#262626;border-radius:3px;position:relative}
.bar-fill{height:100%;border-radius:3px;min-width:2px;display:flex;align-items:center;
padding-left:4px;font-size:.6875rem;color:#fff;white-space:nowrap}
.bar-fill.ok{background:#059669}
.bar-fill.err{background:#dc2626}
.bar-status{min-width:40px;text-align:right;font-size:.8125rem;font-weight:600}
.bar-status.s2{color:#6ee7b7}
.bar-status.s3{color:#93c5fd}
.bar-status.s4{color:#fbbf24}
.bar-status.s5{color:#f87171}
.bar-status.se{color:#f87171}
.detail{display:none;background:#171717;border-radius:6px;padding:1rem;
margin:2px 0 6px 0;font-size:.8125rem;overflow-x:auto}
.detail.open{display:block}
.detail h3{font-size:.875rem;margin-bottom:.5rem;color:#a3a3a3;border-bottom:1px solid #262626;padding-bottom:4px}
.detail pre{background:#0a0a0a;padding:.5rem;border-radius:4px;overflow-x:auto;
font-size:.75rem;line-height:1.5;margin-bottom:.75rem;max-height:300px;overflow-y:auto}
.assertions-list{list-style:none;margin-bottom:.75rem}
.assertions-list li{padding:2px 0}
.assertions-list .pass::before{content:"✓ ";color:#6ee7b7}
.assertions-list .fail::before{content:"✗ ";color:#f87171}
@media(max-width:640px){.bar-label{min-width:100px;max-width:140px}
.header{flex-direction:column;align-items:flex-start}}
</style>
</head>
<body>
<script>
var __TRACE_DATA__ = JSON.parse("/* __DATA__ */".replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>'));
</script>
<div id="app"></div>
<script>
(function(){
var D=__TRACE_DATA__;
var $ = function(s){return document.querySelector(s)};

function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML}
function fmtMs(n){return n<1000?n.toFixed(0)+'ms':(n/1000).toFixed(2)+'s'}
function statusClass(s){if(!s)return 'se';var c=Math.floor(s/100);return 's'+c}
function tryFormatJson(s){try{return JSON.stringify(JSON.parse(s),null,2)}catch(e){return s||''}}

var h='<div class="header"><h1>'+esc(D.collection_name)+' — Trace</h1>'
+'<div class="stats">'
+'<span class="badge badge-pass">'+D.passed+' passed</span>'
+'<span class="badge badge-fail">'+D.failed+' failed</span>'
+'<span class="badge badge-time">'+fmtMs(D.elapsed_ms)+'</span>'
+'</div></div>';

h+='<div class="waterfall">';
D.results.forEach(function(r,i){
  var pct=Math.max((r.elapsed_ms||0)/D.max_elapsed*100,1);
  var cls=r.error?'err':'ok';
  var sc=r.status?statusClass(r.status):'se';
  h+='<div class="bar-row" data-idx="'+i+'">';
  h+='<div class="bar-label"><span class="bar-method">'+esc(r.method||'GET')+'</span>'+esc(r.request_name||r.url||'')+'</div>';
  h+='<div class="bar-track"><div class="bar-fill '+cls+'" style="width:'+pct+'%">'+fmtMs(r.elapsed_ms||0)+'</div></div>';
  h+='<div class="bar-status '+sc+'">'+(r.status||'ERR')+'</div>';
  h+='</div>';
  h+='<div class="detail" id="detail-'+i+'">';
  h+='<h3>Request</h3><pre>'+esc(r.method||'GET')+' '+esc(r.url||'')+'</pre>';
  if(r.error) h+='<h3>Error</h3><pre style="color:#f87171">'+esc(r.error)+'</pre>';
  if(r.assertion_results && r.assertion_results.length){
    h+='<h3>Assertions ('+r.assertions_passed+'/'+((r.assertions_passed||0)+(r.assertions_failed||0))+')</h3>';
    h+='<ul class="assertions-list">';
    r.assertion_results.forEach(function(a){
      h+='<li class="'+(a.passed?'pass':'fail')+'">'+esc(a.message)+'</li>';
    });
    h+='</ul>';
  }
  h+='<h3>Timing</h3><pre>Total: '+fmtMs(r.elapsed_ms||0)+'</pre>';
  h+='</div>';
});
h+='</div>';

$('#app').innerHTML=h;

document.querySelectorAll('.bar-row').forEach(function(row){
  row.addEventListener('click',function(){
    var idx=this.getAttribute('data-idx');
    var det=document.getElementById('detail-'+idx);
    det.classList.toggle('open');
  });
});
})();
</script>
</body>
</html>
"""
