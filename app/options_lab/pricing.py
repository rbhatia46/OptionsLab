"""European Black–Scholes Greeks, IV from observed premium; no RV fallback."""
import math

YEAR_NS = 365.0 * 86400 * 1e9


def cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def price(kind, spot, strike, years, rate, vol):
    if years <= 0:
        return max(spot-strike, 0) if kind == 'C' else max(strike-spot, 0)
    d1 = (math.log(spot/strike) + (rate + vol*vol/2)*years)/(vol*math.sqrt(years))
    d2 = d1-vol*math.sqrt(years)
    disc = math.exp(-rate*years)
    return spot*cdf(d1)-strike*disc*cdf(d2) if kind == 'C' else strike*disc*cdf(-d2)-spot*cdf(-d1)


def implied_vol(kind, spot, strike, years, rate, premium):
    if min(spot,strike,years,premium) <= 0:
        return None
    discounted = strike*math.exp(-rate*years)
    lower = max(0, spot-discounted) if kind == 'C' else max(0, discounted-spot)
    upper = spot if kind == 'C' else discounted
    if not lower + 1e-7 < premium < upper - 1e-7:
        return None
    lo, hi = .0001, 10.0
    if price(kind, spot, strike, years, rate, hi) < premium:
        return None
    for _ in range(45):
        mid = (lo+hi)/2
        if price(kind,spot,strike,years,rate,mid) > premium:
            hi=mid
        else:
            lo=mid
    return (lo+hi)/2


def greeks(kind, spot, strike, years, rate, vol):
    if years <= 0 or vol <= 0:
        return None
    root = math.sqrt(years)
    d1 = (math.log(spot/strike)+(rate+vol*vol/2)*years)/(vol*root)
    d2 = d1-vol*root
    density = math.exp(-d1*d1/2)/math.sqrt(2*math.pi)
    disc = math.exp(-rate*years)
    theta = -spot*density*vol/(2*root)
    theta += -rate*strike*disc*cdf(d2) if kind == 'C' else rate*strike*disc*cdf(-d2)
    return dict(iv=vol, delta=cdf(d1) if kind == 'C' else cdf(d1)-1,
                gamma=density/(spot*vol*root), theta=theta/365, vega=spot*density*root/100)
