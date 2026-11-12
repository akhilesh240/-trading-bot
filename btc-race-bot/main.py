import os, sys, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vendor'))
import makefun_bars

# Deterministic cbBTC 1-minute strategy.
# It waits for a sharp oversold move, then enters only after momentum turns up.
# Positions are deliberately limited to reduce drawdown on an unknown live window.

RSI_N = 14
BAND_N = 20
ENTRY_RSI = 38.0
EXIT_RSI = 62.0
MAX_SLIPPAGE = 80
STAKE_BPS = 4500          # use at most 45% of equity per entry
TAKE_PROFIT_BPS = 45      # 0.45%
STOP_LOSS_BPS = 70         # 0.70%
TRAIL_TRIGGER_BPS = 35
TRAIL_GIVEBACK_BPS = 30
COOLDOWN = 4

class Series:
    def __init__(self):
        self.closes=[]
        self.last=None
        self.gain=None
        self.loss=None
        self.first=[]
        self.entry=None
        self.peak=None
        self.last_exit=-999999

series = {}

def push(bar):
    s=series.setdefault(bar['symbol'], Series())
    c=int(bar['c'])
    s.closes.append(c)
    if len(s.closes)>BAND_N:
        s.closes.pop(0)
    if s.last is not None:
        d=c-s.last
        up=max(d,0); down=max(-d,0)
        if s.gain is None:
            s.first.append((up,down))
            if len(s.first)==RSI_N:
                s.gain=sum(x[0] for x in s.first)/RSI_N
                s.loss=sum(x[1] for x in s.first)/RSI_N
        else:
            s.gain=(s.gain*(RSI_N-1)+up)/RSI_N
            s.loss=(s.loss*(RSI_N-1)+down)/RSI_N
    s.last=c

def rsi(s):
    if s.gain is None or s.loss is None: return None
    total=s.gain+s.loss
    return 50.0 if total==0 else 100.0*s.gain/total

def bands(s):
    if len(s.closes)<BAND_N: return None
    vals=s.closes
    mean=sum(vals)/len(vals)
    var=sum((x-mean)*(x-mean) for x in vals)/len(vals)
    sd=math.sqrt(var)
    return mean-2.0*sd, mean, mean+2.0*sd

def on_batch(state,batch):
    for bar in batch['bars']:
        push(bar)
    if state.warming_up:
        return []

    symbol='CBBTC'
    if symbol not in state.symbols or symbol not in series:
        return []
    s=series[symbol]
    price=state.close(symbol)
    rr=rsi(s); bb=bands(s)
    if price is None or rr is None or bb is None:
        return []

    held=state.positions.get(symbol)
    if held is not None:
        if s.entry is None:
            s.entry=price; s.peak=price
        if price>s.peak: s.peak=price
        pnl_bps=(price-s.entry)*10000//max(1,s.entry)
        peak_bps=(s.peak-s.entry)*10000//max(1,s.entry)
        draw_from_peak=(s.peak-price)*10000//max(1,s.peak)
        exit_now = (
            rr >= EXIT_RSI or
            pnl_bps >= TAKE_PROFIT_BPS or
            pnl_bps <= -STOP_LOSS_BPS or
            (peak_bps >= TRAIL_TRIGGER_BPS and draw_from_peak >= TRAIL_GIVEBACK_BPS)
        )
        if exit_now:
            s.entry=None; s.peak=None; s.last_exit=state.seq
            return [{'side':'sell','symbol':symbol,'qty':held.qty,'max_slippage_bps':MAX_SLIPPAGE}]
        return []

    # Cooldown after an exit avoids repeatedly buying a continuing selloff.
    if state.seq-s.last_exit < COOLDOWN:
        return []

    lower, middle, upper=bb
    # Require an oversold close near the lower band AND a positive one-minute turn.
    prev=s.closes[-2] if len(s.closes)>=2 else price
    rebound = price > prev
    oversold = price <= lower * 1.0015 or rr < ENTRY_RSI
    if oversold and rebound:
        max_by_weight=state.weight_room(symbol)
        stake=min(state.cash, state.equity*STAKE_BPS//10000, max_by_weight)
        minimum=int(state.hello['fees']['min_notional_quote_units'])
        if stake >= minimum and stake>0:
            s.entry=price; s.peak=price
            return [{'side':'buy','symbol':symbol,'notional_quote_units':stake,'max_slippage_bps':MAX_SLIPPAGE}]
    return []

makefun_bars.run(on_batch)
