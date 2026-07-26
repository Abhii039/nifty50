#!/usr/bin/env python3
"""
Nifty 50 F&O Analyzer - build/update script.

Single source of truth for the app:
  - Reads/writes nifty50_state.json  (price history + prediction log)
  - Regenerates nifty50-fno-analyzer.html from that state

Usage:
  python nifty_build.py                      # rebuild HTML from current state
  python nifty_build.py --add 2026-07-27 23810.5   # add a new daily close, score
                                                    # the pending prediction, make a
                                                    # fresh one, then rebuild

On first run (no state.json) it seeds history from the existing HTML file.
"""
import json, math, os, re, sys
from datetime import datetime, timedelta

DIR   = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(DIR, 'nifty50_state.json')
HTML  = os.path.join(DIR, 'index.html')

# ---------------------------------------------------------------- state ----
def seed_from_html():
    """Pull the embedded price series out of the hand-built HTML (first run only)."""
    txt = open(HTML, encoding='utf-8').read()
    chunks = re.findall(r'"((?:\d{4}-\d{2}-\d{2},[\d.]+;?){10,})"', txt)
    raw = ''.join(chunks)
    hist = []
    for r in raw.split(';'):
        if not r:
            continue
        d, c = r.split(',')
        hist.append([d, float(c)])
    if not hist:
        raise SystemExit('Could not seed history from HTML.')
    return hist

def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding='utf-8'))
    return {'history': seed_from_html(), 'predictions': []}

# ---------------------------------------------------------------- math -----
def log_ret_stats(closes, n=120):
    seg = closes[-(n + 1):]
    rets = [math.log(seg[i] / seg[i - 1]) for i in range(1, len(seg))]
    mu = sum(rets) / len(rets)
    var = sum((x - mu) ** 2 for x in rets) / (len(rets) - 1)
    return mu, math.sqrt(var), len(rets)

def next_trading_day(dstr):
    d = datetime.strptime(dstr, '%Y-%m-%d')
    while True:
        d += timedelta(days=1)
        if d.weekday() < 5:
            return d.strftime('%Y-%m-%d')

# ------------------------------------------------------------- rebuild -----
def rebuild(add=None):
    st = load_state()
    hist = st['history']
    st.setdefault('predictions', [])
    dates = [h[0] for h in hist]
    closes = [h[1] for h in hist]

    if add:
        nd, nc = add[0], float(add[1])
        if nd in dates:
            print(f'{nd} already present - skipping add, just rebuilding.')
        else:
            prev_close = closes[-1]
            # Score any pending prediction whose target date has now arrived.
            for p in st['predictions']:
                if p['actual'] is None and p['for_date'] <= nd:
                    ref = p.get('ref_close', prev_close)
                    p['actual'] = nc
                    pred_up = p['pred_next'] > ref
                    act_up = nc > ref
                    p['dir_hit'] = bool(pred_up == act_up)
                    p['abs_err'] = round(abs(p['pred_next'] - nc), 2)
                    p['pct_err'] = round(abs(p['pred_next'] - nc) / nc * 100, 3)
            hist.append([nd, nc])
            dates.append(nd)
            closes.append(nc)

    # Fresh next-trading-day prediction (drift of mean log return).
    mu, sd, _ = log_ret_stats(closes)
    last_date, last_close = dates[-1], closes[-1]
    fdate = next_trading_day(last_date)
    if not any(p['for_date'] == fdate for p in st['predictions']):
        st['predictions'].append({
            'made_on':   last_date,
            'for_date':  fdate,
            'ref_close': last_close,
            'pred_next': round(last_close * math.exp(mu), 2),
            'actual':    None,
            'dir_hit':   None,
        })

    st['history'] = hist
    with open(STATE, 'w', encoding='utf-8') as f:
        json.dump(st, f, indent=0)

    write_html(st)
    scored = [p for p in st['predictions'] if p['actual'] is not None]
    hits = sum(1 for p in scored if p['dir_hit'])
    print(f'Rebuilt. {len(hist)} sessions through {last_date}. '
          f'Predictions scored: {len(scored)}, directional hits: {hits}'
          + (f' ({hits/len(scored)*100:.0f}%).' if scored else '.'))

# ---------------------------------------------------------------- html -----
def write_html(st):
    raw = ';'.join(f'{d},{c}' for d, c in st['history'])
    preds = json.dumps(st['predictions'])
    updated = st['history'][-1][0]
    html = (TEMPLATE
            .replace('__RAW__', raw)
            .replace('__PREDS__', preds)
            .replace('__UPDATED__', updated))
    with open(HTML, 'w', encoding='utf-8') as f:
        f.write(html)

# ======================================================== HTML TEMPLATE ====
TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nifty 50 F&amp;O Analyzer</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<style>
:root{--bg:#0d1117;--panel:#161b22;--border:#30363d;--text:#e6edf3;--muted:#8b949e;--green:#3fb950;--red:#f85149;--blue:#58a6ff;--amber:#d29922;--purple:#bc8cff}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;padding:20px;max-width:1200px;margin:0 auto}
h1{font-size:22px;display:flex;align-items:center;gap:10px}
h1 .badge{font-size:11px;background:var(--blue);color:#fff;padding:2px 8px;border-radius:10px;font-weight:600}
.sub{color:var(--muted);font-size:12px;margin:4px 0 14px}
.warn{background:#3d2c00;border:1px solid var(--amber);color:#e3b341;font-size:12px;padding:10px 14px;border-radius:8px;margin-bottom:16px;line-height:1.5}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:16px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.card .lbl{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.card .val{font-size:20px;font-weight:700;margin-top:4px}
.card .sm{font-size:12px;color:var(--muted);margin-top:2px}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:16px}
.panel h2{font-size:14px;margin-bottom:10px;color:var(--text)}
.panel .note{font-size:11px;color:var(--muted);margin-bottom:10px;line-height:1.5}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;align-items:center}
.toolbar button{background:#21262d;border:1px solid var(--border);color:var(--text);padding:5px 12px;border-radius:6px;cursor:pointer;font-size:12px}
.toolbar button.on{background:var(--blue);border-color:var(--blue);color:#fff}
.chartbox{position:relative;height:380px}
.chartbox.small{height:180px}
.up{color:var(--green)}.down{color:var(--red)}.neu{color:var(--amber)}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:8px 10px;border-bottom:1px solid var(--border);text-align:left}
th{color:var(--muted);font-size:11px;text-transform:uppercase}
.chain td,.chain th{text-align:right;padding:6px 10px;font-variant-numeric:tabular-nums}
.chain th{text-align:right}
.chain .strike{text-align:center;font-weight:700;background:#11151c}
.fno-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.inputs{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:14px}
.inputs label{font-size:12px;color:var(--muted);display:flex;flex-direction:column;gap:4px}
.inputs input{background:#0d1117;border:1px solid var(--border);color:var(--text);padding:6px 10px;border-radius:6px;width:110px;font-size:13px}
.score{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:12px}
.card{transition:transform .15s ease,border-color .15s ease}
.card:hover{transform:translateY(-2px);border-color:#3d4657}
.card .val .arrow{font-size:15px;margin-left:2px}
.verdict-wrap{display:flex;gap:26px;align-items:center;flex-wrap:wrap}
.verdict-text{flex:1;min-width:230px}
#verdictWord{font-size:28px;font-weight:800;letter-spacing:.5px}
.verdict-text p{color:var(--muted);font-size:13px;margin-top:8px;line-height:1.6}
.gauge-hint{color:var(--muted);font-size:11px;text-align:center;margin-top:2px}
#three3d{height:440px;position:relative;cursor:grab;border-radius:8px;background:radial-gradient(ellipse at 50% 30%,#12202e 0%,#0d1117 70%)}
#three3d canvas{display:block;border-radius:8px}
.legend3d{display:flex;gap:16px;font-size:12px;color:var(--muted);margin-top:8px;align-items:center}
.legend3d span{display:inline-flex;align-items:center;gap:6px}
.legend3d i{width:11px;height:11px;border-radius:3px;display:inline-block}
h1 .badge{background:linear-gradient(90deg,#58a6ff,#bc8cff,#58a6ff);background-size:200% 100%;animation:shine 4s linear infinite}
@keyframes shine{0%{background-position:0 0}100%{background-position:200% 0}}
footer{color:var(--muted);font-size:11px;text-align:center;margin:20px 0;line-height:1.6}
</style>
</head>
<body>
<h1>NIFTY 50 <span class="badge">F&amp;O ANALYZER</span></h1>
<div class="sub" id="updated"></div>
<div class="warn"><b>Not investment advice.</b> Projections and option prices below are model outputs, not live market quotes. No model reliably forecasts index prices, and the option chain is <b>theoretical (Black-Scholes)</b> &mdash; real bid/ask will differ, often materially, because of volatility skew and supply/demand. F&amp;O trading can lose your entire capital. Data: Yahoo Finance (^NSEI), daily closes.</div>

<div class="cards" id="cards"></div>

<div class="panel">
  <h2>At a Glance &mdash; What the Data Says</h2>
  <div class="verdict-wrap">
    <div><div id="gauge"></div><div class="gauge-hint">Composite of trend, momentum &amp; RSI</div></div>
    <div class="verdict-text"><div id="verdictWord"></div><p id="verdictExplain"></p></div>
  </div>
</div>

<div class="panel">
  <h2>Price, Moving Averages &amp; 30-Day Projection Cone</h2>
  <div class="toolbar">
    <button data-range="63">3M</button>
    <button data-range="126">6M</button>
    <button data-range="250" class="on">1Y</button>
    <button data-range="9999">2Y</button>
    <span style="width:12px"></span>
    <button data-tog="sma" class="on">SMA 20/50/200</button>
    <button data-tog="bb">Bollinger</button>
    <button data-tog="proj" class="on">Projection</button>
  </div>
  <div class="chartbox"><canvas id="mainChart"></canvas></div>
</div>

<div class="panel"><h2>RSI (14)</h2><div class="chartbox small"><canvas id="rsiChart"></canvas></div></div>
<div class="panel"><h2>MACD (12, 26, 9)</h2><div class="chartbox small"><canvas id="macdChart"></canvas></div></div>

<div class="panel">
  <h2>F&amp;O Calculator &mdash; Nifty Futures &amp; Options (lot size 75)</h2>
  <div class="inputs">
    <label>Days to expiry <input type="number" id="dte" value="30" min="1" max="365"></label>
    <label>Risk-free rate % p.a. <input type="number" id="rfr" value="6.5" step="0.1"></label>
    <label>Strikes each side <input type="number" id="nstr" value="8" min="3" max="15"></label>
  </div>
  <div class="fno-grid" id="fnoCards"></div>
</div>

<div class="panel">
  <h2>Theoretical Option Chain (Black-Scholes)</h2>
  <div class="note">Model prices, <b>not live market quotes.</b> "Bid" is an estimated sell price, "Ask" an estimated buy price (spread modelled around the theoretical value). Uses 20-day annualised volatility, flat across strikes &mdash; so it ignores the real-world volatility smile. ATM row highlighted.</div>
  <table class="chain">
    <thead><tr>
      <th>Call Bid<br><span style="font-weight:400;text-transform:none">(sell)</span></th>
      <th>Call Ask<br><span style="font-weight:400;text-transform:none">(buy)</span></th>
      <th>Call LTP</th><th class="strike" style="text-align:center">Strike</th><th>Put LTP</th>
      <th>Put Bid<br><span style="font-weight:400;text-transform:none">(sell)</span></th>
      <th>Put Ask<br><span style="font-weight:400;text-transform:none">(buy)</span></th>
    </tr></thead>
    <tbody id="chainBody"></tbody>
  </table>
</div>

<div class="panel">
  <h2>3D Option Premium Landscape</h2>
  <div class="note">Every bar is one strike's theoretical premium &mdash; <b>green calls</b> on the back row, <b>red puts</b> on the front. Each bar is labelled with its <b>strike price</b> (below) and <b>premium in ₹</b> (on top); the ATM strike is tagged and glows brightest. Taller bar = pricier option; the tallest sit deepest in-the-money. Drag to rotate, or let it spin. Updates live with the inputs above.</div>
  <div class="toolbar"><button id="spinBtn" class="on">Auto-rotate: on</button></div>
  <div id="three3d"></div>
  <div class="legend3d"><span><i style="background:#3fb950"></i>Calls</span><span><i style="background:#f85149"></i>Puts</span><span>Brightest bar = ATM strike · drag to look around</span></div>
</div>

<div class="panel">
  <h2>Prediction Accuracy Scoreboard</h2>
  <div class="note">Each session the daily job logs a next-day prediction, then scores it once the real close arrives. This is the honest test of the model &mdash; watch whether directional accuracy actually beats 50%. It usually won't by much; index moves are close to a coin flip day to day.</div>
  <div class="score" id="scoreCards"></div>
  <table id="scoreTable"><thead><tr><th>Predicted on</th><th>For date</th><th>Ref close</th><th>Predicted</th><th>Actual</th><th>Abs err</th><th>Direction</th></tr></thead><tbody></tbody></table>
</div>

<div class="panel">
  <h2>Signal Summary</h2>
  <table id="sigTable"><thead><tr><th>Indicator</th><th>Value</th><th>Reading</th></tr></thead><tbody></tbody></table>
</div>

<footer>Educational tool only. Statistical projections assume the past return distribution continues &mdash; real markets gap on news, policy and global events.<br>Not affiliated with NSE. Rebuilt automatically each trading day.</footer>

<script>
const RAW = "__RAW__";
const PREDICTIONS = __PREDS__;

// ---INDICATORS-START---
function parseData(raw){
  const dates=[],closes=[];
  raw.split(';').forEach(r=>{const [d,c]=r.split(',');dates.push(d);closes.push(parseFloat(c));});
  return {dates,closes};
}
function sma(arr,n){
  const out=new Array(arr.length).fill(null);let sum=0;
  for(let i=0;i<arr.length;i++){sum+=arr[i];if(i>=n)sum-=arr[i-n];if(i>=n-1)out[i]=sum/n;}
  return out;
}
function ema(arr,n){
  const out=new Array(arr.length).fill(null);const k=2/(n+1);
  let prev=arr.slice(0,n).reduce((a,b)=>a+b,0)/n;out[n-1]=prev;
  for(let i=n;i<arr.length;i++){prev=arr[i]*k+prev*(1-k);out[i]=prev;}
  return out;
}
function rsi(arr,n){
  const out=new Array(arr.length).fill(null);
  let g=0,l=0;
  for(let i=1;i<=n;i++){const d=arr[i]-arr[i-1];if(d>0)g+=d;else l-=d;}
  let ag=g/n,al=l/n;
  out[n]=al===0?100:100-100/(1+ag/al);
  for(let i=n+1;i<arr.length;i++){
    const d=arr[i]-arr[i-1];
    ag=(ag*(n-1)+(d>0?d:0))/n;
    al=(al*(n-1)+(d<0?-d:0))/n;
    out[i]=al===0?100:100-100/(1+ag/al);
  }
  return out;
}
function macd(arr){
  const e12=ema(arr,12),e26=ema(arr,26);
  const line=arr.map((_,i)=>(e12[i]!=null&&e26[i]!=null)?e12[i]-e26[i]:null);
  const valid=line.filter(v=>v!=null);
  const sigValid=ema(valid,9);
  const signal=new Array(arr.length).fill(null);
  let vi=0;
  for(let i=0;i<arr.length;i++){if(line[i]!=null){signal[i]=sigValid[vi];vi++;}}
  const hist=line.map((v,i)=>(v!=null&&signal[i]!=null)?v-signal[i]:null);
  return {line,signal,hist};
}
function bollinger(arr,n,k){
  const mid=sma(arr,n);
  const up=new Array(arr.length).fill(null),lo=new Array(arr.length).fill(null);
  for(let i=n-1;i<arr.length;i++){
    let s=0;for(let j=i-n+1;j<=i;j++){s+=(arr[j]-mid[i])**2;}
    const sd=Math.sqrt(s/n);up[i]=mid[i]+k*sd;lo[i]=mid[i]-k*sd;
  }
  return {mid,up,lo};
}
function logStats(arr,n){
  const rets=[];
  for(let i=Math.max(1,arr.length-n);i<arr.length;i++)rets.push(Math.log(arr[i]/arr[i-1]));
  const mu=rets.reduce((a,b)=>a+b,0)/rets.length;
  const sd=Math.sqrt(rets.reduce((a,b)=>a+(b-mu)**2,0)/(rets.length-1));
  return {mu,sd,n:rets.length};
}
function projection(arr,days,lookback){
  const {mu,sd}=logStats(arr,lookback);
  const S=arr[arr.length-1];
  const med=[],up=[],lo=[];
  for(let t=1;t<=days;t++){
    const drift=mu*t,vol=1.28*sd*Math.sqrt(t);
    med.push(S*Math.exp(drift));up.push(S*Math.exp(drift+vol));lo.push(S*Math.exp(drift-vol));
  }
  return {med,up,lo,mu,sd};
}
// Black-Scholes
function normCdf(x){
  const t=1/(1+0.2316419*Math.abs(x));
  const d=0.3989423*Math.exp(-x*x/2);
  const p=d*t*(0.3193815+t*(-0.3565638+t*(1.781478+t*(-1.821256+t*1.330274))));
  return x>0?1-p:p;
}
function bs(S,K,T,r,sig,type){
  const d1=(Math.log(S/K)+(r+sig*sig/2)*T)/(sig*Math.sqrt(T));
  const d2=d1-sig*Math.sqrt(T);
  return type==='C'
    ? S*normCdf(d1)-K*Math.exp(-r*T)*normCdf(d2)
    : K*Math.exp(-r*T)*normCdf(-d2)-S*normCdf(-d1);
}
// ---INDICATORS-END---

const {dates,closes}=parseData(RAW);
const N=closes.length,last=closes[N-1],prev=closes[N-2];
const s20=sma(closes,20),s50=sma(closes,50),s200=sma(closes,200);
const r14=rsi(closes,14),m=macd(closes),bb=bollinger(closes,20,2);
const PROJ_DAYS=30,LOOKBACK=120;
const proj=projection(closes,PROJ_DAYS,LOOKBACK);
const annVol=(()=>{const {sd}=logStats(closes,20);return sd*Math.sqrt(252)*100;})();

function futureDates(startISO,n){
  const out=[];const d=new Date(startISO+'T00:00:00Z');
  while(out.length<n){d.setUTCDate(d.getUTCDate()+1);const g=d.getUTCDay();if(g!==0&&g!==6)out.push(d.toISOString().slice(0,10));}
  return out;
}
const fdates=futureDates(dates[N-1],PROJ_DAYS);

document.getElementById('updated').textContent=
  `Historical daily closes ${dates[0]} → ${dates[N-1]} · ${N} sessions · Source: Yahoo Finance (^NSEI)`;
const chg=last-prev,chgP=chg/prev*100;
const trendSig=last>s200[N-1]?(last>s50[N-1]?'Bullish':'Mixed'):(last<s50[N-1]?'Bearish':'Mixed');
const trendCls=trendSig==='Bullish'?'up':trendSig==='Bearish'?'down':'neu';
document.getElementById('cards').innerHTML=`
  <div class="card"><div class="lbl">Last Close</div><div class="val">${last.toLocaleString('en-IN')}</div><div class="sm">${dates[N-1]}</div></div>
  <div class="card"><div class="lbl">Day Change</div><div class="val ${chg>=0?'up':'down'}">${chg>=0?'+':''}${chg.toFixed(1)} (${chgP.toFixed(2)}%)</div><div class="sm">vs ${dates[N-2]}</div></div>
  <div class="card"><div class="lbl">RSI (14)</div><div class="val ${r14[N-1]>70?'down':r14[N-1]<30?'up':''}">${r14[N-1].toFixed(1)}</div><div class="sm">${r14[N-1]>70?'Overbought':r14[N-1]<30?'Oversold':'Neutral zone'}</div></div>
  <div class="card"><div class="lbl">Volatility (20d ann.)</div><div class="val">${annVol.toFixed(1)}%</div><div class="sm">from log returns</div></div>
  <div class="card"><div class="lbl">Trend (vs SMA 50/200)</div><div class="val ${trendCls}">${trendSig}</div><div class="sm">SMA50 ${s50[N-1].toFixed(0)} · SMA200 ${s200[N-1].toFixed(0)}</div></div>`;

Chart.defaults.color='#8b949e';Chart.defaults.borderColor='#30363d';
const state={range:250,sma:true,bb:false,proj:true};
let mainChart;
function buildMain(){
  const start=Math.max(0,N-state.range);
  const labels=dates.slice(start).concat(state.proj?fdates:[]);
  const pad=arr=>arr.slice(start).concat(state.proj?new Array(PROJ_DAYS).fill(null):[]);
  const futPad=arr=>new Array(N-start).fill(null).concat(arr);
  const ds=[{label:'Close',data:pad(closes),borderColor:'#58a6ff',borderWidth:2,pointRadius:0,tension:.1}];
  if(state.sma){
    ds.push({label:'SMA 20',data:pad(s20),borderColor:'#d29922',borderWidth:1,pointRadius:0});
    ds.push({label:'SMA 50',data:pad(s50),borderColor:'#bc8cff',borderWidth:1,pointRadius:0});
    ds.push({label:'SMA 200',data:pad(s200),borderColor:'#f85149',borderWidth:1,pointRadius:0});
  }
  if(state.bb){
    ds.push({label:'BB Upper',data:pad(bb.up),borderColor:'rgba(139,148,158,.5)',borderWidth:1,pointRadius:0,borderDash:[4,4]});
    ds.push({label:'BB Lower',data:pad(bb.lo),borderColor:'rgba(139,148,158,.5)',borderWidth:1,pointRadius:0,borderDash:[4,4],fill:'-1',backgroundColor:'rgba(139,148,158,.06)'});
  }
  if(state.proj){
    ds.push({label:'Projected median',data:futPad(proj.med),borderColor:'#3fb950',borderWidth:2,pointRadius:0,borderDash:[6,4]});
    ds.push({label:'80% band high',data:futPad(proj.up),borderColor:'rgba(63,185,80,.35)',borderWidth:1,pointRadius:0,borderDash:[3,3]});
    ds.push({label:'80% band low',data:futPad(proj.lo),borderColor:'rgba(63,185,80,.35)',borderWidth:1,pointRadius:0,borderDash:[3,3],fill:'-1',backgroundColor:'rgba(63,185,80,.07)'});
  }
  if(mainChart)mainChart.destroy();
  mainChart=new Chart(document.getElementById('mainChart'),{
    type:'line',data:{labels,datasets:ds},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{labels:{boxWidth:12,font:{size:11}}}},
      scales:{x:{ticks:{maxTicksLimit:12,font:{size:10}}},y:{ticks:{font:{size:10}}}}}});
}
buildMain();
document.querySelectorAll('[data-range]').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('[data-range]').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');state.range=+b.dataset.range;buildMain();});
document.querySelectorAll('[data-tog]').forEach(b=>b.onclick=()=>{
  state[b.dataset.tog]=!state[b.dataset.tog];b.classList.toggle('on');buildMain();});

new Chart(document.getElementById('rsiChart'),{type:'line',
  data:{labels:dates.slice(-250),datasets:[{label:'RSI 14',data:r14.slice(-250),borderColor:'#d29922',borderWidth:1.5,pointRadius:0}]},
  options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
    scales:{x:{ticks:{maxTicksLimit:10,font:{size:9}}},y:{min:0,max:100,ticks:{stepSize:30,font:{size:9}},grid:{color:c=>[30,70].includes(c.tick.value)?'#8b0000':'#30363d'}}}}});

new Chart(document.getElementById('macdChart'),{
  data:{labels:dates.slice(-250),datasets:[
    {type:'bar',label:'Histogram',data:m.hist.slice(-250),backgroundColor:m.hist.slice(-250).map(v=>v>=0?'rgba(63,185,80,.55)':'rgba(248,81,73,.55)')},
    {type:'line',label:'MACD',data:m.line.slice(-250),borderColor:'#58a6ff',borderWidth:1.5,pointRadius:0},
    {type:'line',label:'Signal',data:m.signal.slice(-250),borderColor:'#d29922',borderWidth:1.5,pointRadius:0}]},
  options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{boxWidth:12,font:{size:10}}}},
    scales:{x:{ticks:{maxTicksLimit:10,font:{size:9}}},y:{ticks:{font:{size:9}}}}}});

// ---- F&O calculator + option chain ----
function renderFno(){
  const dte=Math.max(1,+document.getElementById('dte').value||30);
  const r=(+document.getElementById('rfr').value||6.5)/100;
  const T=dte/365;
  const fair=last*Math.exp(r*T);
  const atm=Math.round(last/50)*50;
  const {sd}=logStats(closes,20);
  const sigT=sd*Math.sqrt(dte*252/365);
  const move1=last*sigT;
  const straddle=0.8*last*sigT;
  const lot=75;
  document.getElementById('fnoCards').innerHTML=`
    <div class="card"><div class="lbl">Futures fair value (${dte}d)</div><div class="val">${fair.toFixed(1)}</div><div class="sm">spot × e^(r·T), carry only</div></div>
    <div class="card"><div class="lbl">ATM strike</div><div class="val">${atm}</div><div class="sm">nearest 50-point strike</div></div>
    <div class="card"><div class="lbl">Expected move (±1σ)</div><div class="val">±${move1.toFixed(0)}</div><div class="sm">${(last-move1).toFixed(0)} – ${(last+move1).toFixed(0)} (~68%)</div></div>
    <div class="card"><div class="lbl">ATM straddle est.</div><div class="val">≈ ${straddle.toFixed(0)}</div><div class="sm">₹${(straddle*lot).toLocaleString('en-IN',{maximumFractionDigits:0})} / lot ${lot}</div></div>
    <div class="card"><div class="lbl">Contract value</div><div class="val">₹${(last*lot/100000).toFixed(1)}L</div><div class="sm">spot × lot ${lot}</div></div>`;
  renderChain();
}
function renderChain(){
  const dte=Math.max(1,+document.getElementById('dte').value||30);
  const r=(+document.getElementById('rfr').value||6.5)/100;
  const nStr=Math.max(3,Math.min(15,+document.getElementById('nstr').value||8));
  const T=dte/365,sig=annVol/100,S=last,atm=Math.round(S/50)*50;
  const half=p=>Math.max(0.25,p*0.01+0.5);
  let rows='';const chain=[];
  for(let i=nStr;i>=-nStr;i--){
    const K=atm+i*50;
    const call=bs(S,K,T,r,sig,'C'),put=bs(S,K,T,r,sig,'P');
    const cB=Math.max(0,call-half(call)),cA=call+half(call);
    const pB=Math.max(0,put-half(put)),pA=put+half(put);
    const hl=K===atm?' style="background:#1c2333"':'';
    rows+=`<tr${hl}>
      <td class="up">${cB.toFixed(1)}</td><td class="down">${cA.toFixed(1)}</td><td><b>${call.toFixed(1)}</b></td>
      <td class="strike">${K}${K===atm?' •':''}</td>
      <td><b>${put.toFixed(1)}</b></td><td class="up">${pB.toFixed(1)}</td><td class="down">${pA.toFixed(1)}</td></tr>`;
    chain.push({K,call,put,atm});
  }
  document.getElementById('chainBody').innerHTML=rows;
  window._chain=chain;
  if(typeof update3D==='function')update3D();
}
renderFno();
['dte','rfr','nstr'].forEach(id=>document.getElementById(id).oninput=renderFno);

// ---- Accuracy scoreboard ----
(function(){
  const scored=PREDICTIONS.filter(p=>p.actual!=null);
  const hits=scored.filter(p=>p.dir_hit).length;
  const mae=scored.length?scored.reduce((a,p)=>a+Math.abs(p.pred_next-p.actual),0)/scored.length:0;
  const mape=scored.length?scored.reduce((a,p)=>a+Math.abs(p.pred_next-p.actual)/p.actual*100,0)/scored.length:0;
  const pending=PREDICTIONS.find(p=>p.actual==null);
  const hr=scored.length?hits/scored.length*100:0;
  document.getElementById('scoreCards').innerHTML=`
    <div class="card"><div class="lbl">Predictions scored</div><div class="val">${scored.length}</div><div class="sm">since tracking began</div></div>
    <div class="card"><div class="lbl">Directional accuracy</div><div class="val ${scored.length?(hr>=50?'up':'down'):''}">${scored.length?hr.toFixed(0)+'%':'—'}</div><div class="sm">50% = coin flip</div></div>
    <div class="card"><div class="lbl">Mean abs error</div><div class="val">${scored.length?mae.toFixed(0):'—'}</div><div class="sm">${scored.length?mape.toFixed(2)+'% of price':'awaiting data'}</div></div>
    <div class="card"><div class="lbl">Next prediction</div><div class="val">${pending?pending.pred_next.toFixed(0):'—'}</div><div class="sm">${pending?'for '+pending.for_date:'none pending'}</div></div>`;
  const rows=PREDICTIONS.slice().reverse().slice(0,15).map(p=>{
    const dir=p.actual==null?'<span class="neu">pending</span>':(p.dir_hit?'<span class="up">✓ hit</span>':'<span class="down">✗ miss</span>');
    const err=p.actual==null?'—':Math.abs(p.pred_next-p.actual).toFixed(1);
    const act=p.actual==null?'—':p.actual.toFixed(1);
    return `<tr><td>${p.made_on}</td><td>${p.for_date}</td><td>${p.ref_close.toFixed(1)}</td><td>${p.pred_next.toFixed(1)}</td><td>${act}</td><td>${err}</td><td>${dir}</td></tr>`;
  }).join('');
  document.querySelector('#scoreTable tbody').innerHTML=rows||'<tr><td colspan="7" style="color:#8b949e">No predictions logged yet — the daily job will start filling this in.</td></tr>';
})();

// ---- Signals ----
const goldenCross=s50[N-1]>s200[N-1];
const macdBull=m.line[N-1]>m.signal[N-1];
const hi52=Math.max(...closes.slice(-250)),lo52=Math.min(...closes.slice(-250));
const rows=[
  ['Price vs SMA 200',`${last.toFixed(0)} vs ${s200[N-1].toFixed(0)}`,last>s200[N-1]?['Above — long-term uptrend','up']:['Below — long-term downtrend','down']],
  ['Price vs SMA 50',`${last.toFixed(0)} vs ${s50[N-1].toFixed(0)}`,last>s50[N-1]?['Above — medium-term strength','up']:['Below — medium-term weakness','down']],
  ['SMA 50 vs SMA 200',`${s50[N-1].toFixed(0)} vs ${s200[N-1].toFixed(0)}`,goldenCross?['Golden-cross regime','up']:['Death-cross regime','down']],
  ['RSI (14)',r14[N-1].toFixed(1),r14[N-1]>70?['Overbought — stretch risk','down']:r14[N-1]<30?['Oversold — bounce candidate','up']:['Neutral','neu']],
  ['MACD vs Signal',`${m.line[N-1].toFixed(1)} vs ${m.signal[N-1].toFixed(1)}`,macdBull?['Bullish momentum','up']:['Bearish momentum','down']],
  ['52-week range',`${lo52.toFixed(0)} – ${hi52.toFixed(0)}`,[`${((last-lo52)/(hi52-lo52)*100).toFixed(0)}% of range from low`,'neu']],
  [`Projected median (+${PROJ_DAYS}d)`,proj.med[PROJ_DAYS-1].toFixed(0),
    [`80% band: ${proj.lo[PROJ_DAYS-1].toFixed(0)} – ${proj.up[PROJ_DAYS-1].toFixed(0)} (drift ${(proj.mu*100).toFixed(3)}%/d, σ ${(proj.sd*100).toFixed(2)}%/d over ${LOOKBACK} sessions)`, proj.mu>=0?'up':'down']]
];
document.querySelector('#sigTable tbody').innerHTML=
  rows.map(([a,b,[t,c]])=>`<tr><td>${a}</td><td>${b}</td><td class="${c}">${t}</td></tr>`).join('');

// ---- At-a-glance sentiment gauge ----
(function(){
  let sc=0;
  sc+=last>s200[N-1]?25:-25;
  sc+=last>s50[N-1]?20:-20;
  sc+=goldenCross?15:-15;
  sc+=Math.max(-20,Math.min(20,(r14[N-1]-50)/50*20));
  sc+=macdBull?20:-20;
  sc=Math.max(-100,Math.min(100,sc));
  const cx=122,cy=122,rr=94;
  const th=(90-0.9*sc)*Math.PI/180;
  const tx=cx+rr*Math.cos(th),ty=cy-rr*Math.sin(th);
  const w=sc>40?['Bullish','#3fb950']:sc>15?['Leaning Bullish','#7ee787']:sc>-15?['Neutral','#d29922']:sc>-40?['Leaning Bearish','#ffa198']:['Bearish','#f85149'];
  document.getElementById('gauge').innerHTML=
   `<svg width="248" height="150" viewBox="0 0 248 150">
      <defs><linearGradient id="gg" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="#f85149"/><stop offset="0.5" stop-color="#d29922"/><stop offset="1" stop-color="#3fb950"/></linearGradient></defs>
      <path d="M ${cx-rr} ${cy} A ${rr} ${rr} 0 0 1 ${cx+rr} ${cy}" fill="none" stroke="url(#gg)" stroke-width="16" stroke-linecap="round"/>
      <line x1="${cx}" y1="${cy}" x2="${tx.toFixed(1)}" y2="${ty.toFixed(1)}" stroke="#e6edf3" stroke-width="4" stroke-linecap="round"/>
      <circle cx="${cx}" cy="${cy}" r="7" fill="#e6edf3"/>
      <text x="26" y="146" fill="#8b949e" font-size="11">Bearish</text>
      <text x="196" y="146" fill="#8b949e" font-size="11">Bullish</text>
    </svg>`;
  document.getElementById('verdictWord').innerHTML=`<span style="color:${w[1]}">${w[0]}</span>`;
  const parts=[
    last>s200[N-1]?'trading above its 200-day average (long-term uptrend)':'below its 200-day average (long-term downtrend)',
    macdBull?'short-term momentum is positive':'short-term momentum is negative',
    r14[N-1]>70?'and momentum looks overbought':r14[N-1]<30?'and it looks oversold':'with RSI in neutral territory'
  ];
  document.getElementById('verdictExplain').textContent=
    `Nifty is ${parts.join(', ')}. This is a mechanical read of past prices, not a recommendation — the gauge weighs trend, momentum and RSI into a single -100 to +100 score (${sc.toFixed(0)}).`;
})();

// ---- 3D option premium landscape (Three.js) ----
var _scene,_cam,_renderer,_group,_bars,_rot=0,_spin=true,_drag=false,_lx=0;
function init3D(){
  const el=document.getElementById('three3d');if(!el||!window.THREE)return;
  const w=el.clientWidth||800,h=el.clientHeight||440;
  _scene=new THREE.Scene();
  _cam=new THREE.PerspectiveCamera(48,w/h,0.1,500);
  _cam.position.set(0,20,38);_cam.lookAt(0,5,0);
  _renderer=new THREE.WebGLRenderer({alpha:true,antialias:true});
  _renderer.setSize(w,h);_renderer.setPixelRatio(Math.min(2,window.devicePixelRatio||1));
  el.appendChild(_renderer.domElement);
  _scene.add(new THREE.AmbientLight(0xffffff,0.65));
  const dl=new THREE.DirectionalLight(0xffffff,0.85);dl.position.set(12,24,14);_scene.add(dl);
  const dl2=new THREE.DirectionalLight(0x58a6ff,0.3);dl2.position.set(-14,10,-10);_scene.add(dl2);
  _group=new THREE.Group();_scene.add(_group);
  const grid=new THREE.GridHelper(44,22,0x30363d,0x1c222b);_group.add(grid);
  el.addEventListener('pointerdown',e=>{_drag=true;_lx=e.clientX;el.style.cursor='grabbing';});
  window.addEventListener('pointerup',()=>{_drag=false;if(el)el.style.cursor='grab';});
  window.addEventListener('pointermove',e=>{if(_drag){_rot+=(e.clientX-_lx)*0.01;_lx=e.clientX;}});
  window.addEventListener('resize',()=>{const w=el.clientWidth,h=el.clientHeight;if(!w)return;_cam.aspect=w/h;_cam.updateProjectionMatrix();_renderer.setSize(w,h);});
  const btn=document.getElementById('spinBtn');
  btn.onclick=()=>{_spin=!_spin;btn.classList.toggle('on',_spin);btn.textContent='Auto-rotate: '+(_spin?'on':'off');};
  update3D();animate3D();
}
function animate3D(){requestAnimationFrame(animate3D);if(_spin&&!_drag)_rot+=0.004;if(_group)_group.rotation.y=_rot;if(_renderer)_renderer.render(_scene,_cam);}
function makeLabel(text,color,worldW){
  const cv=document.createElement('canvas');
  const font='bold 48px Segoe UI, Arial, sans-serif';
  let ctx=cv.getContext('2d');ctx.font=font;
  const pad=18,w=Math.ceil(ctx.measureText(text).width)+pad*2,h=76;
  cv.width=w;cv.height=h;
  ctx=cv.getContext('2d');ctx.font=font;ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.fillStyle=color||'#e6edf3';ctx.fillText(text,w/2,h/2);
  const tex=new THREE.CanvasTexture(cv);tex.anisotropy=4;tex.needsUpdate=true;
  const mat=new THREE.SpriteMaterial({map:tex,transparent:true,depthTest:false,depthWrite:false});
  const sp=new THREE.Sprite(mat);const aspect=w/h,ww=worldW||4;
  sp.scale.set(ww,ww/aspect,1);return sp;
}
function update3D(){
  if(!_scene)return;
  if(_bars){_group.remove(_bars);_bars.traverse(o=>{if(o.geometry)o.geometry.dispose();if(o.material){if(o.material.map)o.material.map.dispose();o.material.dispose();}});}
  _bars=new THREE.Group();
  let arr=window._chain||[];
  const maxN=13;
  if(arr.length>maxN){const s=Math.floor((arr.length-maxN)/2);arr=arr.slice(s,s+maxN);}
  if(!arr.length){return;}
  const maxP=Math.max(1,...arr.map(d=>Math.max(d.call,d.put)));
  const span=arr.length,gap=2.9;
  const leftX=(-(span-1)/2)*gap;
  arr.forEach((d,i)=>{
    const x=(i-(span-1)/2)*gap;
    const isAtm=d.K===d.atm;
    [['call',-2.9,0x3fb950,'#7ee787'],['put',2.9,0xf85149,'#ffa198']].forEach(([k,z,col,tcol])=>{
      const hgt=Math.max(0.08,d[k]/maxP*13);
      const geo=new THREE.BoxGeometry(1.7,hgt,1.7);
      const mat=new THREE.MeshPhongMaterial({color:col,shininess:70,transparent:true,opacity:isAtm?1:0.82,emissive:col,emissiveIntensity:isAtm?0.35:0.08});
      const mesh=new THREE.Mesh(geo,mat);mesh.position.set(x,hgt/2,z);_bars.add(mesh);
      const pl=makeLabel('₹'+Math.round(d[k]),tcol,2.6);
      pl.position.set(x,hgt+1.1,z);_bars.add(pl);
    });
    const sl=makeLabel(String(d.K),isAtm?'#ffffff':'#c9d1d9',isAtm?3.6:3.0);
    sl.position.set(x,0.7,0);_bars.add(sl);
    if(isAtm){const at=makeLabel('▲ ATM','#d29922',2.6);at.position.set(x,2.2,0);_bars.add(at);}
  });
  const cl=makeLabel('CALLS','#3fb950',4);cl.position.set(leftX-gap*1.5,1.4,-2.9);_bars.add(cl);
  const pu=makeLabel('PUTS','#f85149',4);pu.position.set(leftX-gap*1.5,1.4,2.9);_bars.add(pu);
  const ti=makeLabel('NIFTY 50 OPTIONS  ·  theoretical premium (₹) by strike','#e6edf3',17);
  ti.position.set(0,15.5,0);_bars.add(ti);
  _group.add(_bars);
}
if(window.THREE){init3D();}else{window.addEventListener('load',init3D);}
</script>
</body>
</html>'''

# ---------------------------------------------------------------- main -----
if __name__ == '__main__':
    add = None
    if len(sys.argv) >= 4 and sys.argv[1] == '--add':
        add = (sys.argv[2], sys.argv[3])
    rebuild(add=add)
