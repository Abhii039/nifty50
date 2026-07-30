#!/usr/bin/env python3
"""
Walk-forward backtest of the next-day predictor, on the full close history in
nifty50_state.json (~19 years, 2007->today).

Run this before changing predict_log_return() in nifty_build.py. It scores every
candidate on every session after a 5-year warm-up, using only data available on
the day of the prediction, and asserts the shipped model still beats the old one.

  python backtest.py
"""
import json, math, os, sys, collections

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
from nifty_build import predict_log_return          # the shipped model

hist = json.load(open(os.path.join(DIR, 'nifty50_state.json'), encoding='utf-8'))['history']
D = [h[0] for h in hist]
C = [h[1] for h in hist]
N = len(C)
R = [0.0] + [math.log(C[i] / C[i - 1]) for i in range(1, N)]

WARMUP = 1250                                        # ~5 years


def shipped(i):     return predict_log_return(C[:i + 1])
def old_drift(i):   return sum(R[i - 119:i + 1]) / 120        # pre-2026 model
def always_up(i):   return 1e-9                               # base-rate bench
def follow_yday(i): return R[i] * 0.05                        # runner-up


def score(pred):
    """Directional hit rate and mean absolute error, out of sample."""
    hits = err = 0
    for i in range(WARMUP, N - 1):
        p = C[i] * math.exp(pred(i))
        if (p > C[i]) == (C[i + 1] > C[i]):
            hits += 1
        err += abs(p - C[i + 1])
    n = N - 1 - WARMUP
    return hits / n * 100, err / n, n


def main():
    base = sum(1 for i in range(WARMUP, N - 1) if C[i + 1] > C[i]) / (N - 1 - WARMUP) * 100
    print(f'test window {D[WARMUP]} .. {D[-1]}   up-day base rate {base:.2f}%\n')
    res = {}
    for f, name in ((shipped, 'shipped model'), (old_drift, 'old 120d drift'),
                    (always_up, 'always up'), (follow_yday, 'follow yesterday')):
        acc, mae, n = score(f)
        res[name] = acc
        print(f'{name:<18} acc {acc:5.2f}%   MAE {mae:6.1f}   n={n}')

    # Per-year, so a single lucky stretch can't carry the average.
    yr = collections.defaultdict(lambda: [0, 0, 0])
    for i in range(WARMUP, N - 1):
        up = C[i + 1] > C[i]
        yr[D[i][:4]][0] += (shipped(i) > 0) == up
        yr[D[i][:4]][1] += (old_drift(i) > 0) == up
        yr[D[i][:4]][2] += 1
    wins = sum(1 for a, b, _ in yr.values() if a > b)
    print('\nyear  shipped   old')
    for y in sorted(yr):
        a, b, n = yr[y]
        print(f'{y}   {a/n*100:5.1f}%  {b/n*100:5.1f}%   n={n}')
    print(f'\nshipped model wins {wins}/{len(yr)} years')

    cone()

    assert res['shipped model'] > res['old 120d drift'], 'model regressed vs old drift'
    assert res['shipped model'] > base, 'model no better than always predicting up'
    assert wins > len(yr) / 2, 'model not better in a majority of years'
    print('OK - shipped model beats the old drift, the base rate, and wins most years.')


def cone(H=30, LB=120):
    """The 30-day projection cone drawn in the app: same drift question, longer
    horizon. Checks the median's direction and that the 80% band really does
    contain ~80% of outcomes."""
    print(f'\n{H}-day projection cone:')
    out = {}
    for name, drift in (('120d drift', lambda i: sum(R[i - LB + 1:i + 1]) / LB),
                        ('full history', lambda i: sum(R[1:i + 1]) / i)):
        hits = err = cov = 0
        rng = range(WARMUP, N - H)
        for i in rng:
            seg = R[i - LB + 1:i + 1]
            m = sum(seg) / len(seg)
            sd = math.sqrt(sum((x - m) ** 2 for x in seg) / (len(seg) - 1))
            mu, a = drift(i), C[i + H]
            med = C[i] * math.exp(mu * H)
            w = 1.28 * sd * math.sqrt(H)
            hits += (med > C[i]) == (a > C[i])
            err += abs(med - a)
            cov += C[i] * math.exp(mu * H - w) <= a <= C[i] * math.exp(mu * H + w)
        n = len(rng)
        out[name] = (hits / n * 100, cov / n * 100)
        print(f'  {name:<14} dir {hits/n*100:5.2f}%   MAE {err/n:6.0f}   '
              f'80% band covers {cov/n*100:5.1f}%   n={n}')
    assert out['full history'][0] > out['120d drift'][0], 'cone drift regressed'
    assert abs(out['full history'][1] - 80) < 3, 'cone band badly calibrated'


if __name__ == '__main__':
    main()
