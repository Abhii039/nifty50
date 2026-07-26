#!/usr/bin/env python3
"""
Fetch the latest Nifty 50 (^NSEI) daily close for the GitHub Actions job.

Reads the last date already in nifty50_state.json. If Yahoo has a newer session,
writes `date=` and `close=` to $GITHUB_OUTPUT so the workflow can call
`nifty_build.py --add <date> <close>`. If there is no new session, writes nothing
and exits 0 (the workflow just rebuilds). If the fetch fails entirely, exits 1 so
the run visibly fails instead of fabricating a price.
"""
import json, os, sys, time, urllib.request, datetime

STATE = 'nifty50_state.json'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
URLS = [
    'https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?range=5d&interval=1d',
    'https://query2.finance.yahoo.com/v8/finance/chart/%5ENSEI?range=5d&interval=1d',
]

def latest_from_yahoo():
    for url in URLS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': UA})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.load(resp)
                r = data['chart']['result'][0]
                ts = r['timestamp']
                cl = r['indicators']['quote'][0]['close']
                for i in range(len(ts) - 1, -1, -1):
                    if cl[i] is not None:
                        # Convert epoch (UTC) to the IST trading date.
                        d = datetime.datetime.utcfromtimestamp(ts[i] + 19800).strftime('%Y-%m-%d')
                        return d, round(float(cl[i]), 1)
            except Exception as e:
                sys.stderr.write(f'  {url} attempt {attempt + 1} failed: {e}\n')
                time.sleep(3)
    return None, None

def latest_from_stooq():
    """Fallback source. Stooq serves plain CSV and tends to allow datacenter IPs.
    NOTE: if the symbol ever changes, this returns None and the job fails visibly
    rather than guessing. Verify the symbol at stooq.com if the fallback misfires."""
    url = 'https://stooq.com/q/d/l/?s=%5Ensei&i=d'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode('utf-8', 'ignore').strip()
        lines = text.splitlines()
        if not lines or not lines[0].lower().startswith('date'):
            return None, None
        cols = lines[-1].split(',')          # Date,Open,High,Low,Close,Volume
        d = cols[0]
        c = round(float(cols[4]), 1)
        datetime.datetime.strptime(d, '%Y-%m-%d')   # validate date
        if c < 5000 or c > 100000:                  # sanity-bound the price
            return None, None
        return d, c
    except Exception as e:
        sys.stderr.write(f'  stooq failed: {e}\n')
        return None, None

def main():
    st = json.load(open(STATE, encoding='utf-8'))
    last = st['history'][-1][0]
    d, c = latest_from_yahoo()
    if d is None:
        sys.stderr.write('Yahoo unavailable, trying Stooq fallback...\n')
        d, c = latest_from_stooq()
    if d is None:
        sys.stderr.write('FETCH_FAILED: could not retrieve Nifty close from Yahoo or Stooq.\n')
        sys.exit(1)
    if d <= last:
        sys.stderr.write(f'NO_NEW: latest session {d} already recorded (last={last}).\n')
        return
    out = os.environ.get('GITHUB_OUTPUT')
    line = f'date={d}\nclose={c}\n'
    if out:
        with open(out, 'a') as f:
            f.write(line)
    sys.stderr.write(f'NEW: {d} close {c}\n')

if __name__ == '__main__':
    main()
