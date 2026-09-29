# new_agent v0.1 — DSM-spec scheduler (generative intentions) + greedy field executor.
# Architecture: harness-first, scheduler/executor split, layer contracts w/ telemetry.
# Spec: new_agent/SPEC.md (mined from 34 DSM replays).

# ---- engine tables (kaggle-environments 1.32.7 semantics) ----
CROPS = {
    'WHEAT':      {'seed': 10,  'first': 2,  'maxday': 4,  'interval': 0, 'maxyield': 6, 'ongoing': False},
    'CARROT':     {'seed': 20,  'first': 2,  'maxday': 3,  'interval': 0, 'maxyield': 4, 'ongoing': False},
    'TOMATO':     {'seed': 50,  'first': 8,  'maxday': 8,  'interval': 1, 'maxyield': 4, 'ongoing': True},
    'STRAWBERRY': {'seed': 100, 'first': 10, 'maxday': 10, 'interval': 2, 'maxyield': 4, 'ongoing': True},
    'MELON':      {'seed': 80,  'first': 10, 'maxday': 12, 'interval': 0, 'maxyield': 6, 'ongoing': False},
}
ANIMALS = {
    'GOOSE': {'cost': 300, 'structure': 'COOP',    'product': 'EGG',  'interval': 1},
    'COW':   {'cost': 400, 'structure': 'PASTURE', 'product': 'MILK', 'interval': 2},
    'SHEEP': {'cost': 500, 'structure': 'PASTURE', 'product': 'WOOL', 'interval': 3},
}
PRODUCTS = ['WHEAT', 'CARROT', 'TOMATO', 'STRAWBERRY', 'MELON', 'EGG', 'MILK', 'WOOL', 'FERTILIZER']
SELLABLE = list(PRODUCTS)
SHED_TILES = [(4, 4), (5, 4), (4, 5), (5, 5)]

# ---- telemetry + layer contracts ----
T = {'steps': 0, 'errors': 0, 'sched_fire': {}, 'exec_tasks': {}, 'market_orders': 0,
     'alarms': []}

def REPORT():
    out = dict(T)
    out['sched_fire'] = dict(T['sched_fire'])
    out['exec_tasks'] = dict(T['exec_tasks'])
    return out

class Layer:
    """Contract: trigger() decides, run() acts, every fire is counted.
    Harness fails loudly on never-fire."""
    NAME = 'base'
    def __init__(self):
        self.fired = 0
    def trigger(self, ctx):
        return True
    def run(self, ctx):
        raise NotImplementedError
    def __call__(self, ctx):
        if self.trigger(ctx):
            self.fired += 1
            T['sched_fire'][self.NAME] = T['sched_fire'].get(self.NAME, 0) + 1
            self.run(ctx)

# ---- per-seat persistent state (fresh namespace per game => safe) ----
STATE = {}

def getst(seat):
    st = STATE.get(seat)
    if st is None:
        st = STATE[seat] = {'day': -1, 'req': {}, 'line': None}
    return st

# ---- world model (ctx) ----
class Ctx:
    def __init__(self, obs):
        self.obs = obs
        self.seat = int(obs.get('player', 0)) if isinstance(obs, dict) else int(getattr(obs, 'player', 0))
        g = (lambda k, d=None: obs.get(k, d)) if isinstance(obs, dict) else (lambda k, d=None: getattr(obs, k, d))
        self.day = int(g('day', 0)); self.hour = int(g('hour', 0)); self.step = int(g('step', 0))
        farms = g('farms', [])
        self.farm = farms[self.seat]
        self.rival = farms[1 - self.seat] if len(farms) > 1 else {}
        priv = g('private', {})
        pg = (lambda k, d=None: priv.get(k, d)) if isinstance(priv, dict) else (lambda k, d=None: getattr(priv, k, d))
        self.shed = dict(pg('shed', {}) or {})
        self.seeds = dict(pg('seeds', {}) or {})
        self.invs = list(pg('inventories', []) or [])
        mk = g('market', {}) or {}
        mkg = (lambda k, d=None: mk.get(k, d)) if isinstance(mk, dict) else (lambda k, d=None: getattr(mk, k, d))
        self.prices = dict(mkg('prices', {}) or {})
        town = g('town', {}) or {}
        tg = (lambda k, d=None: town.get(k, d)) if isinstance(town, dict) else (lambda k, d=None: getattr(town, k, d))
        self.shops = list(tg('unlocked_shops', []) or [])
        fg = (lambda k, d=None: self.farm.get(k, d)) if isinstance(self.farm, dict) else (lambda k, d=None: getattr(self.farm, k, d))
        self.money = float(fg('money', 0))
        self.farmer = list(fg('farmer', [4, 4]))
        self.hands = [list(h) for h in (fg('hands', []) or [])]
        self.hires_today = int(fg('hires_today', 0))
        self.tiles = fg('tiles', []) or []
        self.orders = []          # market orders emitted this step
        self.unit_cmds = {}       # actor_idx -> command
        # derived
        self.herd = {'COW': 0, 'SHEEP': 0, 'GOOSE': 0}
        self.standing_crops = {}
        self.scan_tiles()
        while len(self.invs) < 1 + len(self.hands):
            self.invs.append({})
        # owned animals incl shed + carried (for on-demand building)
        self.owned = dict(self.herd)
        for a in ANIMALS:
            self.owned[a] = self.owned.get(a, 0) + int(self.shed.get(a, 0) or 0)
            for inv in self.invs:
                self.owned[a] += int((inv or {}).get(a, 0) or 0)

    def scan_tiles(self):
        self.empty_tiles = []
        self.plants = []      # (x, y, tile)
        self.structs = []     # (x, y, tile)
        self.weeds = []
        for y, row in enumerate(self.tiles):
            for x, t in enumerate(row):
                if t == 'LOCKED' or t == 'LOCKED':
                    continue
                if t is None:
                    self.empty_tiles.append((x, y))
                elif isinstance(t, dict):
                    if t.get('kind') == 'WEED':
                        self.weeds.append((x, y))
                    elif t.get('kind') == 'PLANT':
                        self.plants.append((x, y, t))
                        self.standing_crops[t.get('crop')] = self.standing_crops.get(t.get('crop'), 0) + 1
                    elif 'animal' in t:
                        self.structs.append((x, y, t))
                        a = t.get('animal')
                        if a in self.herd:
                            self.herd[a] += 1
                    elif t.get('kind') in ('COOP', 'PASTURE'):
                        self.structs.append((x, y, t))

    def price(self, item):
        try:
            return float(self.prices.get(item, 1) or 1)
        except Exception:
            return 1.0

# ---- helpers ----
def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def step_toward(pos, tgt):
    x, y = pos
    tx, ty = tgt
    if x < tx: return ['EAST']
    if x > tx: return ['WEST']
    if y < ty: return ['SOUTH']
    if y > ty: return ['NORTH']
    return None

def shed_adjacent(pos):
    # engine _is_shed_adjacent: standing ON one of the 4 inner-corner access tiles.
    # (Neighbors are NOT adjacent: PICKUP/DROP/PLACE-shed emitted there silently fail.)
    return tuple(pos) in [(4, 4), (5, 4), (4, 5), (5, 5)]

def nearest_shed_tile(pos):
    return min(SHED_TILES, key=lambda t: manhattan(pos, t))

def bank_cmd(ctx, st, inv, exclude=('WHEAT', 'FERTILIZER')):
    """Cap-safe shed bank. DROP dumps the whole inventory and the engine
    destroys whatever doesn't fit past the 100-slot cap; ['PLACE', item, n]
    moves only what fits and keeps the excess carried. So: DROP when the
    whole load fits (one action, everything), PLACE the biggest stack when
    only part fits, hold (None) when the shed is full -- holding is free,
    a shed trip for a destroyed bank is not. A per-step room budget (same
    pattern as sleft/wleft/aleft) keeps siblings banking in the same step
    from overselling the same room."""
    if st.get('roomstep') != ctx.step:
        try:
            total = sum(int(v or 0) for v in ctx.shed.values())
        except Exception:
            total = 0
        st['roomstep'] = ctx.step
        st['roomleft'] = 100 - total
    room = int(st.get('roomleft', 0) or 0)
    no = set(exclude) | set(ANIMALS)
    stacks = [(int(v or 0), k) for k, v in inv.items()
              if int(v or 0) > 0 and k not in no]
    if not stacks:
        return None
    carried = sum(int(v or 0) for v in inv.values())
    # DROP-destroys protected stacks: DROP empties the WHOLE inventory, so
    # an excluded item riding a DROP is banked anyway and sold by the next
    # market pass -- the second root cause of FERTILIZE 0/day (a feeder's
    # pocket dumped with its produce). Only DROP when nothing excluded is
    # carried; otherwise PLACE the biggest unprotected stack (one action,
    # same cost, the protected stack stays in the pocket for its own path).
    protected = sum(int(v or 0) for k, v in inv.items()
                    if int(v or 0) > 0 and k in exclude)
    if carried <= room and protected == 0:
        st['roomleft'] = room - carried
        return ['DROP']
    stacks.sort(reverse=True)
    v, k = stacks[0]
    n = min(v, room)
    if n <= 0:
        return None
    st['roomleft'] = room - n
    return ['PLACE', k, n]

# ---- scheduler: DSM-spec day script (strategy #1) ----
# day -> shopping list in priority order (HIRE, LAND, ANIMAL, PROD, SEED), plus crop targets.
def d6_branch(shops):
    yarn = 'YARN_STORE' in shops
    pizza = 'PIZZA_SHOP' in shops
    egg = 'BAKERY' in shops or 'BRUNCH_SPOT' in shops
    ice = 'ICE_CREAM_SHOP' in shops or 'SMOOTHIE_SHOP' in shops
    if yarn:
        return 'sheep'
    if pizza or ice:
        return 'cow+'
    if egg:
        return 'mixed'  # geese earn with bakeries; cows fill rest
    return 'mixed'

# Match town drain (day-24, 8 shops): milk ~19/day ≈ 12-14 cows, wool ~13/day
# ≈ 10 sheep with yarn, egg ~13/day ≈ 6-8 geese. Overproducing linear/sq goods
# floors them at $1 (+59 wool / +76 milk / +62 straw net over I0).
LINE_HERD = {
    'sheep': {'COW': 8,  'SHEEP': 6,  'GOOSE': 6},
    'cow+':  {'COW': 12, 'SHEEP': 3,  'GOOSE': 6},
    'mixed': {'COW': 9,  'SHEEP': 4,  'GOOSE': 8},
}

def herd_target(day, line):
    """Cumulative owned-animal targets (shed+carried+placed). Self-healing deficit."""
    if day == 0:
        return {'COW': 2, 'SHEEP': 3, 'GOOSE': 0}  # DSM d0: 2C+3S ($2300); the 3rd sheep's d6 wool (~6u w/ care bank) funds LAND
    if day < 5:
        return {'COW': 2, 'SHEEP': 3, 'GOOSE': 0}
    # TRY 55 (loop 3B): d5 sheep+goose headstart. Revenue decomposition:
    # his d6 wave is MID-FLIGHT funded by the d6 wool spike ($2976: ~4-5
    # sheep x 4u x $172); our 3 sheep make ~$1000, stalling the wave a day
    # (payback lag = the d10 money hole). d5 wallet (~$360 + $800 sales)
    # affords +1 sheep +1-2 geese; daycap/placement pace the rest. d5
    # target joins the d6 ramp (TRY 34's wallet-blocked attempt now rides
    # the wall-30 savings).
    # ramp: d6 bulk buy is deficit-closed over d6-d12 (budget-capped each step)
    t = dict(LINE_HERD.get(line, LINE_HERD['mixed']))
    if line == 'sheep':
        # PKG1 DSM ramp (mined stands: d6 3.1S, d8 4.0, d10 5.3, d12 6.3;
        # geese d6 0.6, d8 2.0, d10 3.8, d12 5.2)
        if day < 8:   t['SHEEP'] = min(t['SHEEP'], 4)
        elif day < 10: t['SHEEP'] = min(t['SHEEP'], 5)
        elif day < 12: t['SHEEP'] = min(t['SHEEP'], 6)
        if day < 8:   t['GOOSE'] = min(t['GOOSE'], 2)
        elif day < 10: t['GOOSE'] = min(t['GOOSE'], 4)
        if day >= 22:
            t = dict(t); t['SHEEP'] = 6  # endgame: let crashed wool herd go
    else:
        if day < 8:   t['COW'] = min(t['COW'], 6); t['GOOSE'] = min(t['GOOSE'], 4)
        elif day < 10: t['COW'] = min(t['COW'], 9)
        elif day < 12: t['COW'] = min(t['COW'], 11)
    if day >= 26:
        t['GOOSE'] = 0  # stop egg replacements; crash-prone late
    if day >= 28:
        t = {k: 0 for k in t}  # terminal: no replacements
    return t

def land_want(day, ctx, st):
    """Never buy the $4000 4th quadrant (SKIP4 v12: the 4th quad's 25 tiles
    arrive mid-spike, scatter the crew, and never pay back $4000 before
    terminal. Latch still fires at _owned>=2)."""
    # TRY 14 turnover system (parity loop): TRY 8 land (+21 plants),
    # TRY 7/10 targets (room+orders), TRY 13 early wheat (tiles freed,
    # +54 plants alone). Union test of the turnover engine.
    # PKG2 FULL-FIELD GATE (backtrack: his d20 EMPTY 2.7/side vs our ~31.
    # Radius-5 crew can't cover a 100-tile sprawl: far plantings die unseen
    # (DIG 69 vs 36, carrot 30->2). He expands INTO a full field (41% ever
    # buy quad4, money-agnostic); we buy by calendar into emptiness. 3rd
    # land only when the field is actually full (empties < 8).
    w = (1 if day >= 6 else 0) + (1 if day >= 9 else 0) + (1 if day >= 12 else 0)
    w = min(w, 3)
    # PKG3 PAYDAY GATE (mined: q4 buys 38x d10 / 1x d11 / 1x d12 / 1x d18;
    # 49/90 sides NEVER buy. Gate = d10-11 flush affording $4000 + operating
    # cash, NOT calendar. Calendar-buying into emptiness builds the 100-tile
    # sprawl the radius-5 crew cannot cover (DIG 69, carrot 30->2). Compact
    # 75-tile field or nothing.
    # PKG9 FORCE-Q3 (backtrack: v327 proved coverage must be positional.
    # 75 compact tiles the radius-5 crew covers by position; 100-tile sprawl
    # needs priority tricks that churn (DIG 72) or cascade (22k). His q3-49
    # sides end 97k median -- scale suffices. q4-38 question shelved until
    # q3 behavior is exact.
    if w >= 3:
        w = 2
    return w

def shopping(day, ctx, st):
    """Return list of (kind, item, qty) in priority order for this day."""
    L = []
    def H(n): L.append(('HIRE', '', n))
    def LD(n): L.append(('LAND', '', n))
    def A(sp, n): L.append(('A', sp, n))
    def P(it, n): L.append(('P', it, n))
    def S(cr, n): L.append(('S', cr, n))
    if day == 0:
        # DSM d0 EXACT (112076061 audited): 2C+3S ($2300) + 6 MELON ($480) +
        # 15 WHEAT seed ($150) + 9 prod wheat ($225) + 4 hires ($7) = $3162 vs
        # $3000 + 6 wheat sales (~$150+). P9 (not 6) carries 4 wheat into d1 AM;
        # the trim to 6 starved d1 dawn feeding (d2 sheep escapes).
        H(4); A('COW', 2); A('SHEEP', 3); S('MELON', 6); S('WHEAT', 15); P('WHEAT', 9)
    elif day == 1:
        # DSM d1: 9 hires, ~6 feed wheat, MELON 12 (d10-spike stockpile: quads-1
        # fits ~19 free tiles, planters pull as wheat harvests clear; buys
        # self-pace via money caps when the $104 dawn wallet is thin).
        # dsm24: honest 4 hands (quota 4 + retry until filled), nearest-first
        # dispatch. The 9-hand crutch is gone; walks must carry the day.
        H(4); P('WHEAT', 6); S('MELON', 12); S('WHEAT', 6)
    elif day == 2:
        # SPEC melon line: 6 (d0) + ~12 (d1) + ~3 (d2) ~= 21 seeds total.
        # MELON CATCH-UP: the d1 wallet ($7-43) fills ~1 of the MELON-12 quota
        # (req counts emissions and resets at dawn, so broke-day quota dies
        # silently). d2's wallet (~$516) can fund the gap, and d2-planted melon
        # still hits full 6u (window age 6..12 = d8-d15, ripe d12+). Top up to
        # 12 standing+seeds; self-heals like the durables (recomputed daily).
        try:
            _mhave = int(ctx.standing_crops.get('MELON', 0) or 0) \
                + int((ctx.seeds or {}).get('MELON', 0) or 0)
        except Exception:
            _mhave = 12
        H(6); P('WHEAT', 4); S('MELON', max(3, 12 - _mhave)); S('STRAWBERRY', 4)
    elif day == 3:
        try:
            _mhave3 = int(ctx.standing_crops.get('MELON', 0) or 0) \
                + int((ctx.seeds or {}).get('MELON', 0) or 0)
        except Exception:
            _mhave3 = 12
        # d3-planted melon still reaches 6u (window d9-d15, ripe d13+ -> sells
        # d13-15, slightly late cash but full value). Same top-up to 12.
        H(6); S('MELON', max(0, 12 - _mhave3)); S('STRAWBERRY', 6)
    elif day == 4:
        H(6); P('WHEAT', 2); S('STRAWBERRY', 2)
    elif day == 5:
        H(6); P('WHEAT', 2)
    elif day == 6:
        H(8)
        P('WHEAT', 12); S('STRAWBERRY', 8); S('WHEAT', 12)
        # species branch at d6 (herd buy follows in MarketEmit via htgt)
    elif day == 7:
        H(9); P('WHEAT', 14); S('WHEAT', 6); S('STRAWBERRY', 8)
    elif day == 8:
        H(9); P('WHEAT', 16); S('WHEAT', 8)
    elif day == 9:
        H(10); P('WHEAT', 12); S('WHEAT', 18)
        S('CARROT', 4); S('CARROT', 4); S('STRAWBERRY', 8); P('FERTILIZER', 10)
        if 'YARN_STORE' in ctx.shops and st['line'] != 'sheep' and ctx.herd['SHEEP'] < 7 and not LINE_FORCE:
            st['line'] = 'sheep'  # late yarn: switch to sheep line, deficit logic tops up
    elif day == 10:
        # dsm44: H(13) not H(14) -- 14 workers max (DSM: 13 hands + farmer).
        H(13); P('WHEAT', 40); S('WHEAT', 16)
        S('CARROT', 6); S('CARROT', 2); S('STRAWBERRY', 8)
    elif day == 11:
        H(11); S('WHEAT', 16); P('WHEAT', 16); P('FERTILIZER', 24)
        S('CARROT', 6); S('CARROT', 2); S('STRAWBERRY', 8)
    elif day == 12:
        H(11); S('WHEAT', 12); P('WHEAT', 16); P('FERTILIZER', 22)
        S('CARROT', 6); S('CARROT', 5); S('STRAWBERRY', 6)
    elif 13 <= day <= 27:
        H(12 if day < 26 else 10)
        S('WHEAT', 12); S('CARROT', 8); P('WHEAT', 16)
        if day % 2 == 0: P('FERTILIZER', 16)
        # SEEDPILE: bought 8-9/d, planted ~2/d (stands SHRINK 25->16 by policy),
        # drawer 17 straw ($1700) d15. Replacement need ~1-2/d (weeds).
        S('CARROT', 4); S('STRAWBERRY', 3)
        if day % 3 == 0: S('STRAWBERRY', 2)
    elif day >= 28:
        # TRY 74: DSM crew curve holds 10.5 (d28) / 10.0 (d29) hands; our
        # H(6) dropped crew 12 -> 10 -> 6 and starved the final harvest
        # (crew d29 -40%, the biggest L1 gap). Hands reset nightly but a
        # d28 hand still works d28+d29, and stands at d27 are wheat/carrot
        # ready to flip. His late SELL:WHEAT 778 vs our 381 is this labor.
        H(10)
        # d28-29: final bank-rush hands. Hands are DAY-LABOR (farm['hands']
        # resets nightly), so d29 hires act d29 (hired step s acts from s+1)
        # and earn their fib back harvesting/banking the final field. Cutting
        # d29 hires left the farmer alone on the last day (-1.4k on 200003).
        # Seeds/animals stay unbought: they can never pay back.
        # no feed buys — starve crashed lines, keep profitable cows fed via shed wheat only
    return L

CROP_TARGETS = [
    (0,  {'WHEAT': 12, 'MELON': 12}),
    (1,  {'WHEAT': 20, 'MELON': 12, 'STRAWBERRY': 6}),
    (2,  {'WHEAT': 22, 'MELON': 14, 'STRAWBERRY': 14}),
    (6, {'WHEAT': 9, 'MELON': 10, 'STRAWBERRY': 7}),
    # TRY 58 (loop 3B): d6 targets = his d6 stands (W1-5/S7/M10), not 28/24.
    # Quad-1 is 25 tiles; our d6 30+ stands leave 1 empty tile, BUILD fails,
    # bought animals can't place, and the unplaced-gate (correctly) freezes
    # the wave. His 22 stands leave room 3+ and the d6 wave places same-day.
    # Wheat/straw ramp d7-10 with land-2 instead of front-loading quad-1.
    (9,  {'WHEAT': 10, 'MELON': 8, 'STRAWBERRY': 19, 'TOMATO': 1}),
    # PKG1: DSM measured medians as orders (d10 M11/S20/W15/T3; d12
    # W26/S27/T3/C2; d15 W23/S31/T8/C6; d20 W21/S27/T15/C8; d25 W31/S14/T7/C11).
    (11, {'WHEAT': 26, 'STRAWBERRY': 27, 'TOMATO': 3, 'CARROT': 2, 'MELON': 2}),
    (15, {'WHEAT': 23, 'STRAWBERRY': 31, 'TOMATO': 8, 'CARROT': 6}),
    (20, {'WHEAT': 21, 'STRAWBERRY': 27, 'TOMATO': 15, 'CARROT': 8}),
    (25, {'WHEAT': 31, 'STRAWBERRY': 14, 'TOMATO': 7, 'CARROT': 11}),
]

def crop_targets(day):
    t = {}
    for d, tt in CROP_TARGETS:
        if d <= day:
            # TRY 29 (loop 2): COPY, not alias. The latch below does += on
            # st['crops']; with an alias that mutated the global CROP_TARGETS
            # rows every latched step (strawberry target 31->63 by d13,
            # +13 surplus stands whose labor crowded out wheat d10-15).
            t = dict(tt)
    return t

class Scheduler(Layer):
    NAME = 'dsm_script'
    def run(self, ctx):
        st = getst(ctx.seat)
        if st['day'] != ctx.day:
            st['day'] = ctx.day
            st['req'] = {}
            st['tplant'] = 0
            st['cplant'] = 0
            st['wplant'] = 0
            st['nurse'] = {}
            if ctx.day == 6:
                st['line'] = LINE_FORCE or d6_branch(ctx.shops)
        if st['line'] is None:
            st['line'] = (LINE_FORCE or (d6_branch(ctx.shops) if ctx.day >= 6 else 'mixed'))
        # one-shot rush latches (evaluated intraday, latched once)
        if ctx.day == 10 and st['line'] == 'sheep' and ctx.money > 3000:
            st['rush10'] = True
        if ctx.day == 11 and st['line'] == 'sheep' and ctx.money > 4000:
            st['rush11'] = True
        st['shop'] = shopping(ctx.day, ctx, st)
        st['crops'] = crop_targets(ctx.day)
        st['htgt'] = herd_target(ctx.day, st['line'])
        st['lwant'] = land_want(ctx.day, ctx, st)
        # SCALE LATCH (adopted 2026-09-26 as v10: +6966/16 t=2.79 wins 13/16;
        # audit-seed 200001 +11491; parity [+1206,-15053,+12264]):
        # after 3rd land while funded (d11-26, money>3000, shed wheat covers
        # herd, 6+ empties), S/T/C +4/+2/+2. v9's shed-dup fix freed ~10
        # acts/day, supplying the water labor the latch needs. COST: seed1-
        # type tails (-15k, unrecoverable weeds when the field is already
        # behind at latch time); audit weeds 27->36 on 200001 but score still
        # +11.5k. NO hire-half: max-quota logic made H(4) dead code (16-seed
        # scores byte-identical with/without it). Roll back on mean-negative.
        try:
            _q = list(ctx.farm.get('unlocked_quadrants', []) if isinstance(ctx.farm, dict)
                      else getattr(ctx.farm, 'unlocked_quadrants', []))
            _owned = len(_q) - int(st.get('quad0', len(_q)))
        except Exception:
            _owned = 0
        try:
            _herd = sum(int(v or 0) for v in ctx.herd.values())
            _shedW = int(ctx.shed.get('WHEAT', 0) or 0)
        except Exception:
            _herd, _shedW = 99, 0
        _lat = (11 <= ctx.day <= 26 and _owned >= 2 and ctx.money > 3000
                and _shedW >= _herd and len(ctx.empty_tiles) >= 6)
        st['latched'] = bool(_lat)
        if _lat:
            for _k, _inc in (('STRAWBERRY', 4), ('TOMATO', 2), ('CARROT', 2)):
                st['crops'][_k] = int(st['crops'].get(_k, 0) or 0) + _inc
        # STRAW WALL (dsm62): seeds on hand are dead capital; planters idling
        # at target 24 froze straw ~23 vs base ~42 on rich seeds. When rich
        # (money>8000) raise the wall to 40 (price never crashes). Poor seeds
        # can't afford it -> unaffected. (dsm42's wall failed only because it
        # rode with confounds; tested alone here on the dsm44 core.)
        # TRY 54 (loop 3B): straw wall 40 -> 30, retested on the alias-fixed
        # base. Revenue decomposition (90 DSM sides): the d10 money gap is
        # OVERSPEND not under-earn (~$11k seeds vs his ~$7.6k; strawberry
        # 71x$100 vs 44 = $2700 of the $4302 gap). TRY 28's wall-30 test was
        # void (alias bug held targets at 51-63 regardless). Now targets are
        # honest: wall 30 + latch 4 = 34 ~= his 31 stands.
        if ctx.money > 8000:
            st['crops']['STRAWBERRY'] = max(int(st['crops'].get('STRAWBERRY', 0) or 0), 30)

import os as _os
# Experiment control: LINE_FORCE=mixed|cow+|sheep pins the species line so
# A/B compares aren't confounded by shop-draw RNG (shop unlocks share the
# game RNG stream with weed spawns, so the same seed can deal different
# shops to different code versions). Unset for real games.
LINE_FORCE = _os.environ.get('LINE_FORCE') or None

def _fib(n):
    # MUST match engine: _fib(0)=1,_fib(1)=1,_fib(2)=2,_fib(3)=3,_fib(4)=5...
    a, b = 1, 1
    for _ in range(max(0, n)):
        a, b = b, a + b
    return a

class MarketEmit(Layer):
    NAME = 'market'
    def run(self, ctx):
        st = getst(ctx.seat)
        if 'quad0' not in st:
            try:
                st['quad0'] = len(list(ctx.farm.get('unlocked_quadrants', []) if isinstance(ctx.farm, dict) else getattr(ctx.farm, 'unlocked_quadrants', [])))
            except Exception:
                st['quad0'] = 0
        orders = []
        # 0) emergency feed: unfed animals + no wheat ANYWHERE + cash -> wheat.
        # POCKET BLINDNESS (dsm33): the old check saw shed 0 while 20 wheat
        # sat in pockets (5 units x carry 4) -> rebought 10-30 every few steps
        # (d0-1 bought 119 wheat vs his 10; $2500 locked in feed, melon
        # window closed). Count pockets: buy only true shortfall.
        try:
            unfed = sum(1 for _, _, t in ctx.structs if 'animal' in t and not t.get('fed_today'))
        except Exception:
            unfed = 0
        try:
            _pockW = sum(int((inv or {}).get('WHEAT', 0) or 0) for inv in ctx.invs)
        except Exception:
            _pockW = 0
        shed_wheat = int(ctx.shed.get('WHEAT', 0) or 0)
        _short = max(0, unfed - shed_wheat - _pockW)
        if _short > 0 and ctx.day < 28 and len(orders) < 10:
            orders.append(['BUY_PRODUCT', 'WHEAT', min(_short + 1, 12)])
        # 1) sells first (raise cash, free shed). ALWAYS dump shed produce —
        #    price-hold gates re-learned as catastrophic (melon gate at 1.0x
        #    froze the whole cash engine after first sales; wool same).
        #    Batch only when quote is healthy; when weak still SELL (DSM-style
        #    continuous dump beats hold: ablations -10k..-13k).
        #    Wheat reserve = feed runway only (never 2*herd which starved sales).
        herd_n = sum(ctx.herd.values())
        quota0 = 0
        for k, item, qty in st.get('shop', []):
            if k == 'HIRE':
                quota0 = max(quota0, qty)
        crisis = len(ctx.hands) < max(1, quota0 // 2)
        # feed runway: enough wheat for ~1.5 days of herd (FEED buys can top up).
        # FEED=1 wheat/animal/day ALL species (engine-verified): herd_n units
        # is exactly ~1 day of feed, so herd_n+1 is a 1-day runway + 1 spare.
        reserve = (1 if ctx.day <= 2 else (0 if ctx.day >= 28 else (max(1, herd_n) if crisis else herd_n + 1)))  # dsm31: FEED AGGRESSION (mined: his d0 sells 6/9 wheat with 5 mouths, buys 10 wheat-seed+3 melon; d1 converts every fert dollar to 12 melon+hands, feeding hand-to-mouth. Our herd_n+1 runway stockpiles feed while the melon window closes. d0-2 runway=1: fert income covers daily feed, spare dollars become melon.)
        liquidate = ctx.day >= 27
        # healthy-quote batching (soft): sell full shed when weak or liquidating.
        # High-value one-shots trickle (DSM 112076061 d10: MELON 12+6+6+6+6
        # across h10-h19, never a 30-dump: same-step dumping floods the quote
        # --- our 30-batch printed MELON $178 d11 vs DSM ~$240+).
        BATCH = {'MILK': 20, 'WOOL': 12, 'MELON': 6, 'STRAWBERRY': 24,
                 'TOMATO': 20, 'CARROT': 20, 'FERTILIZER': 20, 'EGG': 40, 'WHEAT': 40}
        BASE = {'MILK': 160, 'WOOL': 200, 'MELON': 250, 'STRAWBERRY': 120,
                'TOMATO': 60, 'CARROT': 35, 'FERTILIZER': 100, 'EGG': 50, 'WHEAT': 25}
        # SELL CAP (dsm36): at most 4 sell orders/step. Sells used to fill all
        # 10 slots whenever the shed held 7+ varieties, crowding out seed orders
        # (300006 d14: 0 straw-seed orders -> straw froze 22 vs 42 -> -41k).
        # Shed produce doesn't rot; unsold retries next step. Spreading sells
        # across steps also floods quotes less (melon $178 lesson).
        # SELL-PRIORITY (dsm348). The loop used to walk SELLABLE in fixed
        # order (WHEAT, CARROT, TOMATO, STRAWBERRY, MELON, EGG, MILK, WOOL,
        # FERTILIZER) under a 4-order cap, so the first four items that had
        # stock consumed every slot and the five most valuable products were
        # STRUCTURALLY STARVED of sell orders all game. Measured on 344,
        # seed 300001: shed peaks at the 100-unit cap and the end-of-game
        # shelf is exactly the starved tail -- MILK 9, WOOL 8, EGG 9,
        # FERTILIZER 30 (~$7.6k never converted to money), while 25 milk +
        # 30 wool units sit harvested-but-unsold (~$13.5k). This is a
        # throughput bug, not a market tactic: we grow the goods and then
        # fail to bank them. Fix = order the sell candidates by current
        # value, most valuable first, so each of the 4 slots always carries
        # the most money on the shelf.
        _sell_n = 0
        _cand = []
        for item in SELLABLE:
            have = int(ctx.shed.get(item, 0) or 0)
            q = (have - reserve) if item == 'WHEAT' else have
            if q <= 0:
                continue
            try:
                _px = float(ctx.price(item))
            except Exception:
                _px = BASE.get(item, 1)
            _cand.append((_px, item, q))
        _cand.sort(key=lambda z: -z[0])
        for _px, item, q in _cand:
            if _sell_n >= 4:
                break
            have = int(ctx.shed.get(item, 0) or 0)
            if item == 'WHEAT':
                q = have - reserve
            else:
                q = have
            if q <= 0 or len(orders) >= 10:
                continue
            # batch only while price still >= 0.92 * base (early scarcity);
            # at/below that sell everything (never hold into the crater).
            px = _px
            if liquidate or px < BASE.get(item, 1) * 0.92:
                pass  # full dump
            else:
                q = min(q, BATCH.get(item, 30))
            orders.append(['SELL', item, int(q)])
            _sell_n += 1
        # owned counts (exact, observable) for deficit-driven durables
        try:
            quads = len(list(ctx.farm.get('unlocked_quadrants', []) if isinstance(ctx.farm, dict) else getattr(ctx.farm, 'unlocked_quadrants', [])))
        except Exception:
            quads = st['quad0']
        lands_owned = max(0, quads - st['quad0'])
        owned_animals = dict(ctx.herd)
        for a in ANIMALS:
            owned_animals[a] = owned_animals.get(a, 0) + int(ctx.shed.get(a, 0) or 0)
            for inv in ctx.invs:
                owned_animals[a] += int((inv or {}).get(a, 0) or 0)
        hands_now = len(ctx.hands)
        # 2) durables: pure deficit (self-healing after broke days, never overbuys)
        # 2a) HIRE daily quota, no request memory (hands observable; retry until filled)
        quota = 0
        for k, item, qty in st.get('shop', []):
            if k == 'HIRE':
                quota = max(quota, qty)
        if hands_now < quota and len(orders) < 10:
            # DSM's ORDERS burst but his FILLS stagger by wallet; ours fill
            # instantly when rich -> whole crew same pos same target all day.
            # TRICKLE (dsm26): crisis (<half quota) fills fast; otherwise one
            # HIRE per step and >=5 steps between fills, so each hand walks
            # out alone to whatever is needy now (DSM d1: 4 hands, pairs max).
            try:
                _tnow = T.get('steps', 0)
            except Exception:
                _tnow = 0
            if hands_now > int(st.get('hire_prev', 0)):
                st['hire_last_fill'] = _tnow
            st['hire_prev'] = hands_now
            if ctx.day <= 1 and hands_now >= max(1, quota // 2):
                # trickle ONLY d0-1 (poverty mimicry: stagger dawn arrivals so
                # the crew fans out). d2+ bursts: the wave/shops need crews NOW
                # (all-day trickle strangled the d6 wave: -14.6k t=-2.02).
                if _tnow - int(st.get('hire_last_fill', -99)) >= 5:
                    n = 1
                else:
                    n = 0
            else:
                n = min(quota - hands_now, 10 - len(orders), 8)
            for _ in range(n):
                orders.append(['HIRE'])
            hands_now += n
        # hire reserve: only reserve the NEXT 1-2 hires (partial fill is OK;
        # a full-quotum fib reserve gated shopping 62% of steps → $0 spiral).
        rem = max(0, quota - len(ctx.hands))
        next2 = sum(_fib(ctx.hires_today + k) for k in range(1, min(rem, 2) + 1))
        # never gate when we already have most of the day's hands, or when broke
        # (broke must SELL/shop, not freeze). Gate only rich-side overbuy of hires
        # relative to remaining cash for seeds.
        soft_gated = rem > 2 and ctx.money < (next2 + 800)
        if soft_gated and rem > 0:
            T['exec_tasks']['hire_soft_gate'] = T['exec_tasks'].get('hire_soft_gate', 0) + 1
        # 2b) LAND cumulative want — LAST (capacity is deferrable; seeds/animals
        #    earn, land only holds). Moved after consumables; see 2d.
        # 2c) ANIMALS deficit vs cumulative herd target, labor-paced AND feed-paced.
        #    No wallet gate: the d6 wave must fire on a thin wallet (feed_cap
        #    already blocks mouths we can't feed; feed wheat is pre-bought).
        htgt = st.get('htgt', {})
        if not soft_gated:
            hands_now2 = len(ctx.hands)
            # d0: hires trickle in 2/step but the quota (4) is committed cash;
            # cap on anticipated crew so the 5th head (3rd sheep = d6 LAND
            # money) is bought day 0 instead of stalling at 4 head on wallet.
            hands_eff = hands_now2
            if ctx.day == 0:
                for k, item, qty in st.get('shop', []):
                    if k == 'HIRE':
                        hands_eff = max(hands_eff, qty)
            herd_cap = 4 + 2 * hands_eff
            try:
                # Escape-aware, not instantaneous. Escape fires at
                # consecutive_unfed >= 2, so an animal that ate yesterday
                # (consecutive 0) and simply hasn't eaten yet today is NOT a
                # feed risk -- it will be fed before midnight. Keying this gate
                # on raw fed_today starved the herd: a role-separated crew feeds
                # by mid-morning, so the gate saw "unfed" every dawn and froze
                # every animal purchase, capping the whole economy at 4 head.
                unfed_now = sum(1 for _, _, t in ctx.structs
                                if 'animal' in t and not t.get('fed_today')
                                and int(t.get('consecutive_unfed', 0) or 0) >= 1)
            except Exception:
                unfed_now = 0
            shedW = int(ctx.shed.get('WHEAT', 0) or 0)
            owned_now = sum(owned_animals.get(a, 0) for a in ('COW', 'SHEEP', 'GOOSE'))
            # d0: P10 covers 4 head x 2d = 8 feed and lands same-step (market
            # before units), so the empty-shed feed_cap must not push $1800 of
            # animal buys to t1 where they collide with the melon top-up and
            # leave $98 (killing d1 hires $33 -> water collapse -> 806).
            if ctx.day == 0:
                feed_cap = herd_cap
            else:
                # Pipeline-aware (d6-wave lesson): P-wheat ordered today arrives
                # next step at the latest, and escape needs 2 consecutive unfed
                # days — so feed ordered today covers animals placed today.
                # Without this the d6 wave deadlocks (shed empty -> room 0 ->
                # no buys -> money piles while herd stalls at 5 vs DSM 7-12).
                # Count only funded pipeline (broke emissions may never land).
                pipe = 0
                if ctx.money >= 100:
                    try:
                        pipe = min(int(st['req'].get(('P', 'WHEAT'), 0) or 0), 8)
                    except Exception:
                        pipe = 0
                # TRY 57 (loop 3B): full wave system. Each piece helped alone
                # (+1-2 herd) but the wave is a pipeline: cushion->d5 fills->
                # wool wallet->headroom fills->schedule ceilings. Any single
                # cork stalls everything downstream. Union: headroom (unfreeze
                # under taper-less full coverage: unfed clears AM, room opens
                # midday) + schedule (ceilings follow his 6.1->16.7) + zero
                # cushion animals AND geese d5-8. Falsify on d15 money
                # (payback), not d10 (deployment dip): herd d10 14+, money
                # d15 24000+, FEED <= 420.
                feed_cap = owned_now + 2 if unfed_now > 0 else max(owned_now, min(herd_cap, shedW + pipe + (6 if ctx.money > 3000 else 0)))
            if ctx.day < 6:
                feed_cap = min(feed_cap, 10)
            elif ctx.day < 8:
                feed_cap = min(feed_cap, 12)
            elif ctx.day < 10:
                feed_cap = min(feed_cap, 15)
            # Paced buys (seed-200001 lesson): cash waves must NOT convert into
            # one-day splurges the barns can't absorb (d10: $5300 of animals,
            # half never placed, feed demand doubled -> late collapse 40k->26k).
            # DSM paces +7 d6 then ~2/day to 21 by d11, always placed. Two gates:
            # (1) no new buys while any owned animal is unplaced (shed/carried);
            # (2) at most 4 head/day so BUILD+PLACE+feed keep up.
            unplaced = 0
            for a in ANIMALS:
                unplaced += int(ctx.shed.get(a, 0) or 0)
            for inv in ctx.invs:
                for a in ANIMALS:
                    unplaced += int((inv or {}).get(a, 0) or 0)
            bought_key = ('A', ctx.day)
            bought_today = int(st['req'].get(bought_key, 0) or 0)
            # d0 needs 2C+3S = 5 head same-day (5 units place in parallel);
            # d6 branch wave needs up to 9 (DSM 112076061 d6: 5 COW + 4 GOOSE
            # trickled 1/step h7-h17). Later waves stay at 4/day so
            # BUILD+PLACE+feed keep up. Unplaced-gate below paces to delivery.
            daycap = 5 if ctx.day == 0 else (9 if ctx.day == 6 else 4)
            buy_room = max(0, daycap - bought_today)
            # TRY 59 (loop 3B): pipeline, don't freeze. The unplaced gate
            # (any unplaced -> zero buys) deadlocks the paced wave: buy 1,
            # wait half a day for delivery, buy 1... (measured d6: 1 cow
            # unplaced at s158 froze the other 8 daycap). His delivery keeps
            # up because his buys never stall behind one slow placement.
            # Allow 3 in flight (daycap 4-9/day + wallet still cap totals;
            # the 200001 splurge ($5300 at once) stays impossible).
            if unplaced > 0:
                buy_room = max(0, min(buy_room, 3 - unplaced))
            # AFFORDABILITY gate (200002 lesson): BUY_ANIMAL fails SILENTLY on
            # short wallet or full shed, but st['req'] counts EMISSIONS -- d10
            # room opened on $233, 4 broke buys burned the daycap, and the
            # funded afternoon bought nothing (-18k). Emit only what wallet +
            # shed cover this step; retries across steps land the wave when
            # sales arrive. $100 cushion keeps a hire/seed slice alive.
            spend = 0
            try:
                shed_free = 100 - sum(int(v or 0) for v in ctx.shed.values())
            except Exception:
                shed_free = 0
            # GOOSE_LINE: the shared loop below runs COW/SHEEP first and eats
            # all daily slots, so goose deficits (mixed wants 8) never fill --
            # census showed 0 geese placed all game. Reserve 1 slot/day d6-21
            # under the SAME gates (feed room, zero unplaced, deficit vs htgt).
            # Coop coverage needs no new code: build_kind/place_animal already
            # build on demand for waiting geese. Buy-stop d21: first yield +4d,
            # reward locks d29 22:00, so later geese never pay back $300.
            if (GOOSE_LINE_ON and 6 <= ctx.day <= 21 and len(orders) < 10
                    and buy_room > 0 and unplaced == 0):
                gwant = max(0, int(htgt.get('GOOSE', 0) or 0)
                            - owned_animals.get('GOOSE', 0))
                groom = max(0, min(herd_cap, feed_cap) - owned_now)
                g = min(gwant, groom, buy_room, 1, 10 - len(orders))
                if g > 0 and (not AFFORD_GATE_ON or (
                        ctx.money - spend >= 300 * g + (0 if 5 <= ctx.day <= 8 else 100) and shed_free >= g)):
                    orders.append(['BUY_ANIMAL', 'GOOSE', g])
                    owned_animals['GOOSE'] = owned_animals.get('GOOSE', 0) + g
                    owned_now += g
                    buy_room -= g
                    spend += 300 * g
                    shed_free -= g
                    st['req'][bought_key] = int(st['req'].get(bought_key, 0) or 0) + g
            for a in ('COW', 'SHEEP', 'GOOSE'):
                if len(orders) >= 10 or buy_room <= 0:
                    break
                want = max(0, int(htgt.get(a, 0) or 0) - owned_animals.get(a, 0))
                room = max(0, min(herd_cap, feed_cap) - owned_now)
                want = min(want, room, buy_room)
                if want > 0:
                    n = min(want, 10 - len(orders), 3)
                    if AFFORD_GATE_ON:
                        # TRY 56 (loop 3B): spend-to-zero during the wave.
                        # His d1 wallet ($7-11) still fills 7.4 hires; his d5
                        # ($375+sales) fills the wave. He keeps no $100
                        # cushion; our cushion paces d5-6 fills to zero and
                        # the wave slips a day (payback lag = d10 hole).
                        # Narrow: animals only, days 5-8 only (the 200002
                        # broke-day lesson stays everywhere else).
                        _cush = 0 if (5 <= ctx.day <= 8) else 100
                        while n > 0 and (ctx.money - spend < ANIMALS[a]['cost'] * n + _cush
                                         or shed_free < n):
                            n -= 1  # shrink to affordable: partial fills keep
                        if n <= 0:
                            continue  # the wave moving; retry a later step,
                    cost = ANIMALS[a]['cost'] * n  # don't burn daycap on fails
                    orders.append(['BUY_ANIMAL', a, n])
                    owned_animals[a] = owned_animals.get(a, 0) + n
                    owned_now += n
                    buy_room -= n
                    spend += cost
                    shed_free -= n
                    st['req'][bought_key] = int(st['req'].get(bought_key, 0) or 0) + n
        # 3) consumables: request-counted slices. Never fully gated — seed/feed
        #    purchases ARE the income loop; only trim qty when cash is thin.
        #    HUNGER GATE (d2 lesson, seed-0: the d2 melon top-up $320 ate the
        #    fert-sale cash while 3/5 head sat cu=1 with 0 shed wheat; 1 feed
        #    all day, 3rd sheep escaped): escape-risk animals + empty wheat
        #    shelf => seeds wait, wheat+hires only. Lifts itself when fed.
        try:
            hungry = any('animal' in t and int(t.get('consecutive_unfed', 0) or 0) >= 1
                         for _, _, t in ctx.structs)
        except Exception:
            hungry = False
        starving = hungry and int(ctx.shed.get('WHEAT', 0) or 0) < sum(ctx.herd.values())
        for k, item, qty in st.get('shop', []):
            if len(orders) >= 10:
                break
            if k not in ('P', 'S'):
                continue
            key = (k, item)
            done = st['req'].get(key, 0)
            if done >= qty:
                continue
            if k == 'P':
                # cash-aware: always allow small top-ups (feed/fert), cap big ones.
                # Never 0: $20 of wheat seed breaks a broke-then-empty-tiles spiral.
                # Fertilizer is a yield BOOST, not survival: only when rich, and
                # never stockpile (buy+sell same-day round-trips bled cash:
                # shed passes straight through to the dump when application
                # lags supply). Buy only when the shed holds < 8.
                if item == 'FERTILIZER' and ctx.money < 2500:
                    continue
                if item == 'FERTILIZER' and int(ctx.shed.get('FERTILIZER', 0) or 0) >= 8:
                    continue
                # d0 trickle (DSM 112076061 d0: 1-2/step funded by 1 sale/step;
                # a full-burst $2357 step0 hits the $3000 wall and the leftover
                # remainder starves d0-PM feed -> d2 escapes). 2/step completes
                # P9+M6+WS15 by ~h10 with sales between every buy.
                if ctx.day == 0:
                    cap = 2
                elif starving and item == 'WHEAT':
                    cap = 20  # hunger: full wheat quota at once, no trickle
                else:
                    cap = 20 if ctx.money >= 2000 else (6 if ctx.money >= 400 else 2)
                # One BUY order carries any qty; remaining order slots gate
                # whether we emit at all, not the qty (old 10-len min
                # fragmented d0 buys across t0-t2 and seeds landed late).
                n = min(qty - done, cap)
                if n > 0:
                    orders.append(['BUY_PRODUCT', item, n])
                    st['req'][key] = done + n
            elif k == 'S':
                # never stockpile: seeds are dead capital ($13k piles observed).
                # Buy only below on-hand caps; planters pull from stock first.
                # d0 melon burst (10) must clear the cap; straw buffer 14 for the
                # d9-11 wall burst (planters pull ~4-6/day; never-crash $233).
                SEEDCAP = {'WHEAT': 20, 'CARROT': 10, 'TOMATO': 8, 'STRAWBERRY': 14, 'MELON': 14}
                if int(ctx.seeds.get(item, 0) or 0) >= SEEDCAP.get(item, 10):
                    continue
                # hunger gate (soft): escape-risk + empty shelf => seeds
                # trickle to 1 while wheat flows full (a hard skip stalled the
                # seed-2 melon wall at 7-10/12: -$13k).
                if ctx.day == 0:
                    cap = 2  # d0 trickle (see P-block note)
                elif starving:
                    cap = 1
                else:
                    cap = 10 if ctx.money >= 1500 else (4 if ctx.money >= 400 else 2)
                n = min(qty - done, cap)
                if n > 0:
                    orders.append(['BUY_SEED', item, n])
                    st['req'][key] = done + n
        # 2d) LAND last: capacity never outranks income on a thin wallet.
        #     Self-healing deficit (retries until filled), but only when rich
        #     enough that land can't starve hires/seeds/feed. First plot costs
        #     only $1000 (LAND_PRICES=[1000,2000,4000]) so DSM buys it d6 with
        #     wool money; gate it at 1200, later plots at 2500.
        if lands_owned < st.get('lwant', 0) and len(orders) < 10:
            gate = 1200 if lands_owned == 0 else 2500
            if ctx.money >= gate:
                orders.append(['BUY_LAND'])
        ctx.orders = orders
        T['market_orders'] += len(orders)

# new_agent STIG v1 — stigmergic field executor (see STIG_DESIGN.md + DSM_OS_SPEC.md).
# Macro layers above (Ctx/Scheduler/MarketEmit) are byte-identical to agent.py v0.1
# frozen base. ONLY the field layer below is new. No roles, no columns, no claims.

# A/B flags referenced by the copied MarketEmit (both OFF, matching frozen base).
GOOSE_LINE_ON = True
AFFORD_GATE_ON = False

STIG_RADIUS = 5       # TRY 20 wake radius (parity loop): sleep-in-field
                          # (TRY 4) strands planters away from freed tiles
                          # (full drawer + deficit + idle coexist). His same-day
                          # replant 94% needs sleepers to SEE freed tiles.
STIG_PERSIST = 1.5    # directional bonus: DSM same-direction persistence 46%
STIG_DIST_W = 2.0     # legacy weight, superseded by NEAREST_FIRST below
STIG_NEAREST_FIRST = True  # dsm24 rewrite: nearest needy tile wins, urgency
        # only breaks ties (val weight < 1 step). Value-first scoring let a
        # distant HARVEST/FEED drag units across the map past near work.
STIG_BANK_LOAD = 8    # carrying this much produce -> shed becomes top target
STIG_WHEAT_CARRY = 4  # DSM PICKUP WHEAT amounts cluster 2-4
STIG_FERT_DAY = 9     # DSM embargo: no field fert before d9 (it sells then)


class StigExec(Layer):
    NAME = 'stig'

    def tile_at(self, ctx, x, y):
        try:
            row = ctx.tiles[y]
        except Exception:
            return None
        try:
            return row[x]
        except Exception:
            return None

    def ripe(self, ctx, t):
        try:
            cd = CROPS.get(t.get('crop'), {})
            age = ctx.day - int(t.get('planted_day', 0) or 0)
            yld = int(t.get('yield_units', 0) or 0)
        except Exception:
            return False, 0
        if cd.get('ongoing'):
            return (age >= cd.get('first', 99)) and yld > 0, yld
        # Melon liquidation: one-shot tiles free for strawberries the moment
        # they hold banked cash (opp harvests all d10 at ~4.8, sells same day
        # -> $18k spike; waiting for 6.0 smears to d12-13 and the tile sits
        # occupied). Time value + tile reuse beat the last ~1.5u/plant.
        if t.get('crop') == 'MELON':
            return (age >= cd.get('first', 0)) and yld > 0, yld
        # TRY 14: wheat ripe at yld>=2 (his 1-6 spread, turnover engine).
        if t.get('crop') == 'WHEAT':
            return (yld >= 2) and age >= cd.get('first', 0), yld
        # DSM-811 CARROT TURNOVER (traced seed1: 27/31 carrots expire EOD age
        # 3 = maxday with yld 3 banked, $0 — ripe() only fired at age>3 (too
        # late) or age==3+watered (too narrow: units never arrive same day).
        # Harvest at yld>=2 & age>=2 like wheat: banks ~2u guaranteed vs 87%
        # total-loss rate. Expected 2.0 vs 0.39/u-run. Same trap may hit melon
        # (ripe age>=10, expiry EOD 12) — separate lever, not touched here.
        if t.get('crop') == 'CARROT':
            return (yld >= 2) and age >= cd.get('first', 0), yld
        mx = cd.get('maxyield', 6)
        maxday = cd.get('maxday', 99)
        first = cd.get('first', 0)
        # Engine HARVEST FAILS below first_yield_day even with yield banked
        # (fert can push melon to 6 by age 9); acting on it camps the unit
        # all day spamming no-ops AND pulls walkers map-wide via plant_need.
        r = (yld >= mx or age > maxday or (age == maxday and t.get('watered_today'))) \
            and age >= first
        return r and yld > 0, yld

    def fert_pays(self, ctx, t):
        """FERTILIZE only when the bonus can land. The engine max()es
        fertilized_until_day, so repeats on an active tile are pure no-ops --
        and the on-tile rule fires FERTILIZE instead of WATER while pocket
        fert lasts, so one unit dumps its whole pocket on one plant over
        consecutive steps. Ongoing crops tick +1 on production eves
        (days_since_first % interval == 0) with +1 more iff watered that eve
        while fert is active: fert applied day d covers eves d..d+2. One-shots
        bank +1/watering (+2 fert) only inside [(maxday+1)//2, maxday], cap
        maxyield: fert past maxyield-2 buys nothing."""
        try:
            crop = t.get('crop')
            cd = CROPS.get(crop)
            if cd is None:
                return False
            day = ctx.day
            fu = t.get('fertilized_until_day', -1)
            if fu is None:
                fu = -1
            if int(fu) >= day:
                return False  # already active: a repeat is a pure no-op
            age = day - int(t.get('planted_day', 0) or 0)
            if cd.get('ongoing'):
                if crop not in ('STRAWBERRY', 'TOMATO'):
                    return False
                first, iv, mx = cd['first'], max(1, cd['interval']), cd['maxyield']
                for eve in (day, day + 1, day + 2):
                    dsf = (eve + 1) - int(t.get('planted_day', 0) or 0) - first
                    if dsf >= 0 and dsf % iv == 0 and dsf // iv + 1 <= mx:
                        return True
                return False
            # TRY 15 wheat fert retry (parity loop): TRY 9 proved the gate
            # fires (+21 ferts) but starved for in-window wheat on the small
            # wall; TRY 14 rebuilt wheat turnover, so retry on this base.
            if crop not in ('MELON', 'WHEAT'):
                return False
            ws = (cd['maxday'] + 1) // 2
            yld = int(t.get('yield_units', 0) or 0)
            return ws <= age <= cd['maxday'] and yld <= cd['maxyield'] - 2
        except Exception:
            return False

    def prod_eve(self, ctx, t):
        """True iff this tile has a strawberry production eve TODAY (end of
        day ticks +1, +1 more iff watered today while fert active). Engine:
        dsf = (day+1-planted-first) % iv == 0, production_count <= maxyield."""
        try:
            if t.get('crop') != 'STRAWBERRY':
                return False
            cd = CROPS.get('STRAWBERRY')
            day = ctx.day
            planted = int(t.get('planted_day', 0) or 0)
            first, iv, mx = cd['first'], max(1, cd['interval']), cd['maxyield']
            dsf = (day + 1) - planted - first
            return dsf >= 0 and dsf % iv == 0 and dsf // iv + 1 <= mx
        except Exception:
            return False

    def plant_need(self, ctx, x, y, t):
        """(value, kind) for a plant tile, 0 if nothing to do."""
        r, yld = self.ripe(ctx, t)
        if r:
            return 8.0, 'HARVEST'
        # PKG14 SPENT-TILE GATE (backtrack: d22+ ~25 spent-straw tiles demand
        # daily water with zero production left (ongoing, all ticks done) --
        # ~2 hands watering corpses while carrot wave dies. His water budget
        # (1093) can't cover corpses either; his tiles auto-clear at
        # lifespan (his d25 S14, d29 S7). No remaining eves + no yield =
        # nothing to do (ripe above already harvests leftovers).
        try:
            _cd = CROPS.get(t.get('crop'), {})
            if _cd.get('ongoing'):
                _rem = False
                _planted = int(t.get('planted_day', 0) or 0)
                _first, _iv, _mx = _cd['first'], max(1, _cd['interval']), _cd['maxyield']
                for _eve in range(ctx.day, 30):
                    _dsf = (_eve + 1) - _planted - _first
                    if _dsf >= 0 and _dsf % _iv == 0 and _dsf // _iv + 1 <= _mx:
                        _rem = True
                        break
                if not _rem:
                    return 0.0, None
        except Exception:
            pass
        if not t.get('watered_today'):
            cu = int(t.get('consecutive_unwatered', 0) or 0)
            if cu >= 1:
                return 10.0, 'WATER'
            # Melon window water: every missed window day is -1u cash forever
            # (one-shot, no catch-up). 7.0 beats routine 5.0, yields to eve
            # 8.0/HARVEST 8.0. Conflict-free before d12 (first straw eve d12).
            try:
                _mage = ctx.day - int(t.get('planted_day', 0) or 0)
            except Exception:
                _mage = -1
            if t.get('crop') == 'MELON' and 6 <= _mage <= 12:
                return 7.0, 'WATER'
            # Eve pass: today's strawberry production eves outrank routine
            # field work (ties ripe HARVEST 8.0, below hungry FEED 10.0).
            # The bonus needs water AND fert-active on the eve; fert_pays
            # already aims fert at windows, this aims the water.
            if self.prod_eve(ctx, t):
                return 8.0, 'WATER'
            return 5.0, 'WATER'
        return 0.0, None

    def struct_need(self, ctx, x, y, t, inv, pos=None):
        """(value, cmd) for an animal structure, 0 if nothing to do.
        FEED needs pocket wheat; CARE/COLLECT/HARVEST never do (a wheat-less
        unit must still visit: collect-fert is the broke-day income that buys
        tomorrow's wheat). No NEED_WHEAT blindness, ever.
        TRY 42 (loop 3A): routine hunger pulls only at touch range. His
        feeding is nearest-carrier opportunism (no map-wide marches to
        cu==0 mouths); ours dragged loaded carriers up to 5 tiles. On-tile
        rule 1 still feeds on touch; escape-risk (cu>=1) still pulls
        map-wide at 10.0."""
        if t.get('animal') is None:
            return 0.0, None
        wheat = int(inv.get('WHEAT', 0) or 0)
        if not t.get('fed_today'):
            if wheat > 0:
                cu = int(t.get('consecutive_unfed', 0) or 0)
                if cu >= 1:
                    return 10.0, 'FEED'
                if pos is not None and abs(pos[0] - x) + abs(pos[1] - y) > 2:
                    return 0.0, None
                return 7.0, 'FEED'
        try:
            yld = int(t.get('yield_units', 0) or 0)
        except Exception:
            yld = 0
        mh = ANIMAL_MAXHELD.get(t.get('animal'), 6)
        if t.get('fed_today') and not t.get('cared_today') and yld < mh:
            return 5.0, 'CARE'
        if t.get('fertilizer_available'):
            return 4.5, 'COLLECT_FERTILIZER'
        if yld > 0:
            return 8.0, 'HARVEST'
        if not t.get('fed_today'):
            return 3.0, 'VISIT'  # no wheat: still worth walking over (collect next)
        return 0.0, None

    def run(self, ctx):
        st = getst(ctx.seat)
        sg = st.setdefault('stig', {})
        if sg.get('day') != ctx.day:
            sg['day'] = ctx.day
            sg['dirs'] = {}
        dirs = sg['dirs']
        taken = set()
        reserved = set()  # walk-target reservation (dsm26): a tile picked as
        # a walk destination is reserved for the step, so the next unit never
        # follows the first. taken covers worked tiles; reserved covers tiles
        # being walked to. Shed trips are NOT reserved (shared shed is fine).
        n = 1 + len(ctx.hands)
        invs = [dict(inv or {}) for inv in ctx.invs]
        while len(invs) < n:
            invs.append({})
        shed_left = dict(ctx.shed)
        seeds_left = dict(ctx.seeds)
        tgts = dict(st.get('crops', {}) or {})

        def produce_load(inv):
            return sum(int(v or 0) for k, v in inv.items()
                       if k in ('CARROT', 'TOMATO', 'STRAWBERRY', 'MELON', 'EGG',
                                'MILK', 'WOOL', 'WHEAT'))

        for i in range(n):
            p = list(ctx.farmer) if i == 0 else list(ctx.hands[i - 1])
            inv = invs[i]
            cmd = self.unit_cmd(ctx, st, sg, dirs, taken, reserved, i, p, inv, invs,
                                shed_left, seeds_left, tgts)
            if cmd is None:
                cmd = ['PASS']
            ctx.unit_cmds[i] = cmd
            # ACT BREAKS STRIDE: every act clears direction memory so units
            # stop at near jobs instead of streaming past them.
            if cmd[0] not in ('NORTH', 'SOUTH', 'EAST', 'WEST'):
                dirs.pop(i, None)
            T['exec_tasks']['stig_' + cmd[0]] = T['exec_tasks'].get('stig_' + cmd[0], 0) + 1

    # ---------------- per-unit policy ----------------
    def unit_cmd(self, ctx, st, sg, dirs, taken, reserved, i, p, inv, invs,
                 shed_left, seeds_left, tgts):
        x, y = int(p[0]), int(p[1])
        t = self.tile_at(ctx, x, y)
        on_shed = (x, y) in SHED_TILES_SET
        # One actor per tile per step (shed excepted: shed_act has its own
        # budgets). Without this the crew piles onto the top-value tile and
        # 11/12 actions no-op (d10: 14 units WATERed (8,2) 13x; d13: 50
        # HARVEST cmds on 5 melon tiles). Chains survive: taken resets steps.
        # STIG v9 shed-dup fix (adopted 2026-09-26: +7515/16 t=2.54 wins
        # 13/16; repeat_probe shed-tile repeats 3-9 -> 0; audit weeds 33->27;
        # pins +5217/+13200/+14321): on-tile work honors taken even on shed
        # tiles. The 4 shed tiles hold STRUCTURES (first builds land on them);
        # the old `not on_shed` exemption let all 13 units run rule 1 on the
        # same shed-tile animal in one step (stale shared obs, all no-ops).
        # shed_act (rule 4) never checked claimed: banking throughput untouched.
        claimed = (x, y) in taken
        # PKG12 MASS-PICK (mined: his d11 plants 15 (8.7 wheat) because d10
        # mass-pick frees 10 melon tiles -- opportunity, not priority. Our
        # d10-12 smear kills the d11 window. d10-11: ripe MELON harvests first
        # (on-tile only, no seek change, no water touched). Narrow.
        if not claimed and isinstance(t, dict) and t.get('kind') == 'PLANT' \
                and t.get('crop') == 'MELON' and not on_shed:
            try:
                _mday = int(ctx.day)
            except Exception:
                _mday = 0
            if _mday in (10, 11):
                _mr, _my = self.ripe(ctx, t)
                if _mr:
                    taken.add((x, y))
                    return ['HARVEST']
        # 1) on-tile animal work
        if not claimed and isinstance(t, dict) and t.get('animal') is not None:
            if not t.get('fed_today') and int(inv.get('WHEAT', 0) or 0) > 0:
                inv['WHEAT'] = int(inv.get('WHEAT', 0) or 0) - 1
                taken.add((x, y))
                return ['FEED']
            if t.get('fed_today') and not t.get('cared_today'):
                try:
                    yld = int(t.get('yield_units', 0) or 0)
                except Exception:
                    yld = 0
                if yld < ANIMAL_MAXHELD.get(t.get('animal'), 6):
                    taken.add((x, y))
                    return ['CARE']
            if t.get('fertilizer_available'):
                taken.add((x, y))
                return ['COLLECT_FERTILIZER']
            try:
                yld = int(t.get('yield_units', 0) or 0)
            except Exception:
                yld = 0
            if yld > 0:
                taken.add((x, y))
                return ['HARVEST']
        # 1b) on-tile weed
        if not claimed and isinstance(t, dict) and t.get('kind') == 'WEED' and not on_shed:
            taken.add((x, y))
            return ['DIG']
        # 2) on-tile plant work
        if not claimed and isinstance(t, dict) and t.get('kind') == 'PLANT' and not on_shed:
            r, yld = self.ripe(ctx, t)
            if r:
                taken.add((x, y))
                return ['HARVEST']
            if not t.get('watered_today'):
                # PKG10 application gate: melon window d6+ (yield units), all
                # else STIG_FERT_DAY (cash embargo). fert_pays verifies window.
                _fd = STIG_FERT_DAY if t.get('crop') != 'MELON' else 6
                if ctx.day >= _fd and int(inv.get('FERTILIZER', 0) or 0) > 0 \
                        and self.fert_pays(ctx, t):
                    inv['FERTILIZER'] = int(inv.get('FERTILIZER', 0) or 0) - 1
                    taken.add((x, y))
                    return ['FERTILIZE']
                taken.add((x, y))
                return ['WATER']
        # 3) standing on empty: build/place/plant right here
        if not claimed and t is None and not on_shed:
            c = self.empty_act(ctx, st, taken, i, (x, y), inv, invs,
                               shed_left, seeds_left, tgts)
            if c is not None:
                return c
        # 4) shed tile: bank then load
        if on_shed:
            c = self.shed_act(ctx, st, taken, i, (x, y), inv, invs,
                              shed_left, seeds_left, tgts)
            if c is not None:
                return c
        # 5) carrying an unplaced animal: deliver it
        carry = None
        for a in ANIMALS:
            if int(inv.get(a, 0) or 0) > 0:
                carry = a
                break
        if carry is not None:
            return self.deliver(ctx, taken, i, (x, y), carry)
        # 6) move to best work within radius
        return self.seek(ctx, st, dirs, taken, reserved, i, (x, y), inv, invs,
                         shed_left, seeds_left, tgts)

    def empty_act(self, ctx, st, taken, i, pos, inv, invs,
                  shed_left, seeds_left, tgts):
        # waiting animal in pocket -> BUILD structure here (taken holds tile)
        for a in ANIMALS:
            if int(inv.get(a, 0) or 0) > 0:
                kind = ANIMALS[a]['structure']
                taken.add(pos)
                return ['BUILD_PASTURE' if kind == 'PASTURE' else 'BUILD_COOP']
        # shed ring reservation: tiles within 2 of the shed stay empty for
        # structures (pastures exiled to the corner cost ~5 moves/feed).
        # Plant here only if the field has no room elsewhere.
        if min(abs(pos[0] - sx) + abs(pos[1] - sy) for sx, sy in SHED_TILES) <= 2:
            if any(min(abs(x - sx) + abs(y - sy) for sx, sy in SHED_TILES) > 2
                   for x, y in ctx.empty_tiles):
                return None
        # plant deficit crop
        crop = self.pick_crop(ctx, st, seeds_left, tgts)
        if crop is not None and int(seeds_left.get(crop, 0) or 0) > 0:
            seeds_left[crop] = int(seeds_left.get(crop, 0) or 0) - 1
            # scheduled-rhythm counters increment on ACTUAL plants only
            # (pick_crop is read-only: seek calls it per tile evaluated).
            # PKG19 NURSE: planter tends this newborn 2 days (sticky
            # position defeats drift; no global priority change).
            try:
                if crop == 'TOMATO':
                    st['tplant'] = int(st.get('tplant', 0) or 0) + 1
                elif crop == 'CARROT':
                    st['cplant'] = int(st.get('cplant', 0) or 0) + 1
                elif crop == 'WHEAT':
                    st['wplant'] = int(st.get('wplant', 0) or 0) + 1
                if isinstance(st.get('nurse'), dict):
                    st['nurse'][i] = (pos[0], pos[1], int(ctx.day) + 2)
            except Exception:
                pass
            taken.add(pos)
            return ['PLANT', crop]
        return None

    def pick_crop(self, ctx, st, seeds_left, tgts):
        best, bestd = None, 0
        # TERMINAL CLOSURE (adopted 2026-09-26: +2484/16 t=4.85 wins 14/16;
        # parity gates identical, pins +3395/+5373/-1328; audit weeds 30->29):
        # never plant what cannot yield before the d29 lock (probe: 72-78
        # PLANT acts d20-29/game incl 14 doomed $100 strawberry). Plant-by =
        # 29 - first_yield_day. Freed labor flows to harvest/bank; drawer
        # seeds go unspent (sunk).
        try:
            _day = int(ctx.day)
        except Exception:
            _day = 0
        _BY = {'WHEAT': 27, 'CARROT': 27, 'TOMATO': 21, 'STRAWBERRY': 19, 'MELON': 19}
        # TRY 60 (loop 3B): melon plants d0-2, before wheat. Biggest-deficit
        # lets wheat (want 20-22) eat every freed tile d1-3 while melon seeds
        # sit in pockets to d3; those d3 melons ripen d13, missing the d10
        # $10k payday (his: 10 stands d2, mass-pick d10-11, ~44 units). Melon
        # is a 10-day one-shot: a d3 planting is a d13 harvest. First 10
        # melon seeds plant before any d0-2 wheat.
        if _day <= 2 and int(ctx.standing_crops.get('MELON', 0) or 0) < 10 \
                and int(seeds_left.get('MELON', 0) or 0) > 0:
            return 'MELON'
        # PKG1 scheduled rhythm (mined: T ~1-2/d from d8, C wave d20-26).
        # Biggest-deficit alone never elects T/C (wheat want always bigger);
        # DSM plants them on schedule regardless. Same-day water covers them
        # (plant_need WATER 5.0 > seek-plant 4.5; cu>=1 10.0 catches backlog).
        try:
            _tp = int(st.get('tplant', 0) or 0)
        except Exception:
            _tp = 99
        # PKG7 WHEAT-SECURE QUOTA (backtrack: quota T/C took first plant
        # events daily, wheat d20 fell to 13-19 vs his steady 21-26. His
        # wheat never dips (replant-first); scheduled T/C fire only when
        # wheat is at/near target (deficit <= 3). Narrow: quota gating only.
        try:
            _wdef = int(tgts.get('WHEAT', 0) or 0) - int(ctx.standing_crops.get('WHEAT', 0) or 0)
        except Exception:
            _wdef = 0
        # PKG11 STRAW-SENIOR (exam backtrack: quota T/C d10-15 ate the straw
        # ramp events (straw +4 vs his +13); straw is the cash crop both
        # builds share (his S30-33, pipe S33). T/C fire only when straw is
        # also near target (deficit <= 4). Narrow: quota gating only.
        try:
            _sdef = int(tgts.get('STRAWBERRY', 0) or 0) - int(ctx.standing_crops.get('STRAWBERRY', 0) or 0)
        except Exception:
            _sdef = 0
        # (v326: <=3 never opened (deficit runs 5-8); <=6 opens when wheat
        # within 6 of target -- his deficit band is 0-5, ours 5-8. Opens
        # sometimes, wheat keeps precedence otherwise.)
        # PKG12 HIS MIX (mined: tomato ~1/d d10-20, not 2/d; 2/d over-plants
        # (dies) and steals wheat refill events. 1/d.)
        # DSM-809 TRUE RATE-SWAP (pipe19: 142W/52C/0T vs our ~170/15/12 at the
        # SAME water 36.5/d and ~2 deaths — the swap is labor-neutral. dsm803
        # ADDED carrot (total plantings up -> water bankruptcy -> wheat +9).
        # Here carrot REPLACES wheat/tomato: tomato off entirely, carrot
        # ungated by wheat deficit, wheat capped 5/d d20-26 (frees ~2-3
        # plantings/d for carrot). Feed insurance kept (P-wheat buys stay).
        if False and 8 <= _day <= 20 and _tp < 1 and _wdef <= 6 and _sdef <= 4 \
                and int(tgts.get('TOMATO', 0) or 0) - int(ctx.standing_crops.get('TOMATO', 0) or 0) > 0 \
                and int(seeds_left.get('TOMATO', 0) or 0) > 0 \
                and _day <= _BY.get('TOMATO', 29):
            return 'TOMATO'
        try:
            _cp = int(st.get('cplant', 0) or 0)
        except Exception:
            _cp = 99
        _cquota = (9 if 25 <= _day <= 26 else (6 if 22 <= _day <= 24 else (3 if 20 <= _day <= 21 else (1 if 12 <= _day <= 19 else 0))))
        if _cquota and _cp < _cquota \
                and int(tgts.get('CARROT', 0) or 0) - int(ctx.standing_crops.get('CARROT', 0) or 0) > 0 \
                and int(seeds_left.get('CARROT', 0) or 0) > 0 \
                and _day <= _BY.get('CARROT', 29):
            return 'CARROT'
        try:
            _wp = int(st.get('wplant', 0) or 0)
        except Exception:
            _wp = 0
        for crop, want in tgts.items():
            if crop == 'TOMATO':
                continue  # swap: never plant tomato
            if crop == 'WHEAT' and 20 <= _day <= 26 and _wp >= 5:
                continue  # swap: wheat capped 5/d late, rest of labor to carrot
            if int(seeds_left.get(crop, 0) or 0) <= 0:
                continue
            if _day > _BY.get(crop, 29):
                continue
            d = int(want or 0) - int(ctx.standing_crops.get(crop, 0) or 0)
            if d > bestd:
                best, bestd = crop, d
        return best

    def shed_act(self, ctx, st, taken, i, pos, inv, invs,
                 shed_left, seeds_left, tgts):
        # bank produce (DROP dumps the WHOLE pocket: only DROP when no
        # wheat/fert/animals ride along, else PLACE the biggest produce stack)
        # Before the field-fert day fertilizer is CASH, not supply: bank it
        # same-day (d1 fert cash funds d1 wheat+hires; pockets-only banking
        # delayed all fert cash via the nightly auto-drop, starving d1).
        # d9+ it rides pockets to paying applications (fert_pays-gated);
        # banking it would shuttle supply to the shed and back (PICKUP acts +
        # pockets clogged with unappliable fert). Surplus sells via the
        # nightly auto-drop. WHEAT stays carried (feed supply); ANIMALS stay
        # carried (delivery).
        keep = ('WHEAT', 'FERTILIZER') if ctx.day >= STIG_FERT_DAY else ('WHEAT',)
        stacks = [(int(v or 0), k) for k, v in inv.items()
                  if int(v or 0) > 0 and k in ('CARROT', 'TOMATO', 'STRAWBERRY',
                      'MELON', 'EGG', 'MILK', 'WOOL', 'WHEAT', 'FERTILIZER')]
        produce = [(v, k) for v, k in stacks
                   if k not in keep and k not in ANIMALS]
        if produce:
            try:
                total = sum(int(v or 0) for v in shed_left.values())
            except Exception:
                total = 0
            room = 100 - total
            carried = sum(v for v, _ in produce)
            protected = sum(int(v or 0) for k, v in inv.items()
                            if int(v or 0) > 0 and (k in keep or k in ANIMALS))
            if carried <= room and protected == 0:
                for _, k in produce:
                    shed_left[k] = int(shed_left.get(k, 0) or 0) + int(inv.get(k, 0) or 0)
                    inv[k] = 0
                return ['DROP']
            produce.sort(reverse=True)
            v, k = produce[0]
            m = min(v, room)
            if m > 0:
                shed_left[k] = int(shed_left.get(k, 0) or 0) + m
                inv[k] = int(inv.get(k, 0) or 0) - m
                return ['PLACE', k, m]
        # load wheat for unfed herd
        try:
            unfed = sum(1 for _, _, s in ctx.structs
                        if s.get('animal') is not None and not s.get('fed_today'))
        except Exception:
            unfed = 0
        if unfed > 0 and int(inv.get('WHEAT', 0) or 0) < STIG_WHEAT_CARRY:
            have = int(shed_left.get('WHEAT', 0) or 0)
            m = min(STIG_WHEAT_CARRY - int(inv.get('WHEAT', 0) or 0), have)
            if m > 0:
                shed_left['WHEAT'] = have - m
                inv['WHEAT'] = int(inv.get('WHEAT', 0) or 0) + m
                return ['PICKUP', 'WHEAT', m]
        # load waiting animal for delivery: anything sitting in the shed
        # unplaced is a placement job (deficit-vs-htgt would read shed stock
        # as owned and never fetch). deliver() BUILDs when no struct is free.
        # Cap 2 concurrent deliverers on d0 (uncapped, the whole dawn crew
        # grabs animals and nobody plants: d0 19->9 plants); 5 after (the d6
        # wave needs 7+ placed in one day and 2-at-a-time stalls it to d9).
        carriers = 0
        for inv2 in invs:
            for a in ANIMALS:
                if int(inv2.get(a, 0) or 0) > 0:
                    carriers += 1
                    break
        cap = 2 if ctx.day == 0 else 5
        if carriers < cap:
            for a in ANIMALS:
                if int(shed_left.get(a, 0) or 0) > 0:
                    shed_left[a] = int(shed_left.get(a, 0) or 0) - 1
                    inv[a] = int(inv.get(a, 0) or 0) + 1
                    return ['PICKUP', a, 1]
        # NOTE: seeds are consumed from stock by PLANT directly (tracked via
        # seeds_left); units never carry seeds, so no seed PICKUP exists.
        # PKG10 MELON FERT (backtrack: his 60u d10 <- window water + fert;
        # ours 34-42u. Pre-9 fert ALL sold (d1 cash); melon window d6-12 gets
        # none. Units carry <=2 d6+ for paying applications (fert_pays gates
        # to melon-window/straw-eve; surplus still banks via keep rule).
        # Priced: ~$1k d6-8 cash not-sold -> +1u x 10 tiles x $250 = +$2.5k
        # d10 payday -> funds T/C seeds on poor seeds (variance fix).
        if (ctx.day >= STIG_FERT_DAY or ctx.day >= 6) and int(inv.get('FERTILIZER', 0) or 0) < (4 if ctx.day >= STIG_FERT_DAY else 2):
            have = int(shed_left.get('FERTILIZER', 0) or 0)
            _cap = 4 if ctx.day >= STIG_FERT_DAY else 2
            m = min(_cap - int(inv.get('FERTILIZER', 0) or 0), have)
            if m > 0:
                shed_left['FERTILIZER'] = have - m
                inv['FERTILIZER'] = int(inv.get('FERTILIZER', 0) or 0) + m
                return ['PICKUP', 'FERTILIZER', m]
        return None

    def deliver(self, ctx, taken, i, pos, carry):
        kind = ANIMALS[carry]['structure']
        cands = [(x, y) for x, y, s in ctx.structs
                 if s.get('kind') == kind and s.get('animal') is None
                 and (x, y) not in taken]
        if cands:
            tgt = min(cands, key=lambda t2: manhattan(pos, t2))
            if tuple(pos) == tgt:
                taken.add(tgt)
                return ['PLACE', carry]
            taken.add(tgt)
            return step_toward(pos, tgt) or ['PASS']
        cands = [t for t in ctx.empty_tiles if t not in taken]
        if not cands:
            return ['PASS']
        tgt = min(cands, key=lambda t2: manhattan(t2, (4, 4)) * 4 + manhattan(pos, t2))
        taken.add(tgt)
        if tuple(pos) == tgt:
            return ['BUILD_PASTURE' if kind == 'PASTURE' else 'BUILD_COOP']
        return step_toward(pos, tgt) or ['PASS']

    def seek(self, ctx, st, dirs, taken, reserved, i, pos, inv, invs,
             shed_left, seeds_left, tgts):
        px, py = pos
        lastd = dirs.get(i)
        best = None  # (score, tx, ty)
        # TRY 41 (loop 3A): bank threshold counts PRODUCE only, not wheat.
        # His carriers sleep loaded (dusk pockets 21.5); ours detour to the
        # shed with full wheat pockets because wheat counted toward the bank
        # trip threshold, then top up residue while there. Wheat rides, it
        # doesn't bank. (produce_load alias kept, unread in seek.)
        bank = produce_load = sum(int(v or 0) for k, v in inv.items()
                                   if k in ('CARROT', 'TOMATO', 'STRAWBERRY', 'MELON',
                                            'EGG', 'MILK', 'WOOL'))
        if ctx.day < STIG_FERT_DAY:
            # first 2 fert ride (melon program), rest banks as cash
            bank += max(0, int(inv.get('FERTILIZER', 0) or 0) - 2)
        fert_carry = int(inv.get('FERTILIZER', 0) or 0)
        R = STIG_RADIUS
        for y in range(max(0, py - 12), min(10, py + 13)):
            for x in range(max(0, px - 12), min(10, px + 13)):
                if (x, y) == (px, py) or (x, y) in taken or (x, y) in reserved:
                    continue
                d = abs(x - px) + abs(y - py)
                if d > 12:
                    continue
                t = self.tile_at(ctx, x, y)
                val, _kind = 0.0, None
                if isinstance(t, dict) and t.get('animal') is not None:
                    val, _kind = self.struct_need(ctx, x, y, t, inv, (px, py))
                elif isinstance(t, dict) and t.get('kind') == 'PLANT':
                    # PKG16 PAYDAY RUSH (exam: H2H d10 money 8 vs pipe 2288;
                    # shared shops crater for late sellers. d10: ripe MELON
                    # outranks field work (9.0, harvest-first accelerates
                    # income -- safe direction, unlike water priority).
                    # Narrow: d10, ripe melon only.
                    try:
                        _pday = int(ctx.day)
                    except Exception:
                        _pday = -1
                    if _pday == 10 and t.get('crop') == 'MELON':
                        _rr, _ry = self.ripe(ctx, t)
                        if _rr:
                            val, _kind = 9.0, 'HARVEST'
                        else:
                            val, _kind = self.plant_need(ctx, x, y, t)
                    else:
                        val, _kind = self.plant_need(ctx, x, y, t)
                elif t is None and (x, y) not in SHED_TILES_SET:
                    if any(int(inv.get(a, 0) or 0) > 0 for a in ANIMALS):
                        val = 7.0
                    elif self.pick_crop(ctx, st, seeds_left, tgts) is not None:
                        # shed-ring tiles are weak plant targets (reserved)
                        # INVERSION FIX (adopted 2026-09-26 as v11: +9595/16
                        # t=2.25 wins 10/16; parity [+12084,+41038,-12330]
                        # mean +13.6k; pinned avg 122.2k): seek-plant 6.0 sat
                        # ABOVE routine WATER 5.0, so units marched past
                        # thirsty plants to plant far tiles (root of seed1
                        # latch tail AND walk-claim -60k tails). At 4.5 water
                        # comes first, plant when nothing thirsty. On-tile
                        # planting (rule 3) untouched. COST: scale-able seeds
                        # under-plant (300008 -22.7k, seed2 -12.3k); fixes
                        # collapse seeds instead (300013 +49.5k, seed1 +41k).
                        # Next: weed-velocity brake to reclaim scale seeds.
                        # PKG17 OPPORTUNISTIC PLANT (exam: his d11 15 plants
                        # into 10 melon empties; our water-first (4.5<5.0)
                        # caps planting ~8/d, ramp +4 vs +13. Empty-rich
                        # (>=6) days plant-first (6.0>5.0); normal days
                        # water-first (4.5). Flex, not blanket (v310).
                        try:
                            _ne = len(ctx.empty_tiles)
                        except Exception:
                            _ne = 0
                        _pv = 6.0 if _ne >= 6 else 4.5
                        val = _pv if min(abs(x - sx) + abs(y - sy)
                                         for sx, sy in SHED_TILES) > 2 else 2.0
                elif isinstance(t, dict) and t.get('kind') == 'WEED':
                    val = 1.0
                if val <= 0:
                    continue
                # PKG13 WATER-ONLY LIFT (backtrack: residual deaths = drift,
                # not bunching (units spread, his backlog bigger). Far tiles
                # double-miss when corner crews drift; nearest-first never
                # sends anyone back (far-5.0 invisible). WATER visible
                # map-wide all day: val 5.0 binds ONLY when no near work
                # (else nearest wins), so no herding (v321 lifted urgents;
                # this lifts routine water). Plant/build stay local.
                # Dusk (h>=18): all water goes far (one-way walks, morning
                # feed anchors re-gather). Day: routine water (5.0, not
                # rescue/harvest/eve) goes far only if unit would else PASS
                # (approximated: allow; nearest-first still prefers near).
                if d > R and val < 9.0:
                    if _kind == 'WATER':
                        pass  # water goes far (drift correction)
                    else:
                        continue  # radius cap: only bank/load trips go far
                if STIG_NEAREST_FIRST:
                    score = -d + 0.09 * min(val, 10.0)
                else:
                    score = val - STIG_DIST_W * d
                if lastd is not None and d > 0:
                    # direction bonus: first step from pos toward (x,y)
                    s1 = step_toward(pos, (x, y))
                    if s1 is not None and s1[0] == lastd:
                        score += STIG_PERSIST
                if best is None or score > best[0]:
                    best = (score, x, y)
        # PKG19 nurse pull: tending unit returns to thirsty nursery if close
        # (<=4); beyond that released (someone nearer covers). Local only.
        try:
            _nz = (st.get('nurse') or {}).get(i)
        except Exception:
            _nz = None
        if _nz is not None:
            try:
                _nx, _ny, _nd = _nz
                if int(ctx.day) <= int(_nd):
                    _nt = self.tile_at(ctx, _nx, _ny)
                    if isinstance(_nt, dict) and _nt.get('kind') == 'PLANT' \
                            and not _nt.get('watered_today'):
                        _ndd = abs(_nx - px) + abs(_ny - py)
                        if 0 < _ndd <= 4 and (best is None or -_ndd + 0.45 > best[0]):
                            best = (-_ndd + 0.45, _nx, _ny)
                else:
                    st['nurse'].pop(i, None)
            except Exception:
                pass
        # shed trips: bank when loaded, load when hungry/thirsty-for-seed
        # d1-only fert-cash trip: pocket fert -> shed while the crew is broke.
        # Longer shuttles taxed field labor all game (unconditional: wave 3
        # days late, -8.7k; crisis-gated: -20.5k). d2+ has emergency P-orders
        # + nightly sales; only d1 has FEED 0 with no other income path.
        # BANK JITTER (dsm26): threshold 7/8/9 by unit index so pockets fill
        # at different rates and the crew never banks/leaves as one herd.
        _bank_at = STIG_BANK_LOAD + (i % 3) - 1
        if bank >= _bank_at or (fert_carry >= 2 and ctx.day <= 1):
            tgt = min(SHED_TILES, key=lambda s: manhattan(pos, s))
            if tuple(pos) == tuple(tgt):
                return None  # shed_act should have banked; fallback PASS
            return self.walk_to(dirs, i, pos, tuple(tgt))
        # wheat-load trip: unfed herd + empty pocket + shed stock -> go load.
        # (Without this, wheat-less units never visit the shed and the herd
        # starves 2 tiles away from salvation.)
        if int(inv.get('WHEAT', 0) or 0) <= 0 and int(shed_left.get('WHEAT', 0) or 0) > 0:
            try:
                hungry = any(s.get('animal') is not None and not s.get('fed_today')
                             for _, _, s in ctx.structs)
            except Exception:
                hungry = False
            if hungry:
                tgt = min(SHED_TILES, key=lambda s: manhattan(pos, s))
                if tuple(pos) != tuple(tgt):
                    return self.walk_to(dirs, i, pos, tuple(tgt))
        if best is None:
            # TRY 4 sleep-in-field (parity loop): DSM long walks are
            # field->field WATER (crops pull him outward); ours are
            # field->shed PICKUP/COLLECT (shed pulls us inward: this
            # drift-home fallback + bank trips re-center every loop on the
            # shed). His PASS 414 vs our 221: his units idle in the field
            # when nothing is near; ours march home and back. PASS in place.
            return ['PASS']
        _, tx, ty = best
        reserved.add((tx, ty))  # nobody follows: this tile is spoken for
        return self.walk_to(dirs, i, pos, (tx, ty))

    def walk_to(self, dirs, i, pos, tgt):
        s = step_toward(pos, tgt)
        if s is None:
            return ['PASS']
        dirs[i] = s[0]
        return s


SHED_TILES_SET = {(4, 4), (5, 4), (4, 5), (5, 5)}
ANIMAL_MAXHELD = {'GOOSE': 4, 'COW': 6, 'SHEEP': 6}

STIG = StigExec()
SCHED = Scheduler()
MARKET = MarketEmit()


# DSM-344: port of outside DSM-03/v3_last_water deadline mechanisms onto the
# 343 base (rate-swap + carrot turnover). Three orthogonal, clock-feasible
# levers our tree never tried (verified: no hour>=23/terminal guards in 343):
#  (midnight) forbid h23 PLANT (newborns start cu=1, EOD kills at cu>=2, no
#    watering step exists after h23) — outside stepwise meter: 14.0 -> 0.0
#    midnight newborn deaths/game, DIG -15, dawn deaths -8;
#  (terminal) d29 physical delivery phase (last action step 718 = d29 h22, no
#    final EOD banking): jobs budgeted work+return+DROP, sell projected shelf
#    — outside: +6.1k solo / +9.5k H2H on reference;
#  (last_water) d29 h23+ FERTILIZE that cannot prevent cu=1->2 death is refused
#    so the on-tile WATER executes instead (0-2 events/seed, tiny but free).
# Outside 6-seed: solo 143474.5 vs 137701.8 (+5.8k, t=2.65), H2H +9.36k
# (t=2.43), DIG 54.67->36.33, PASS +7.3% (within guard). Wheat (+0.3/6) and
# HARVEST (+10/65) gates stayed OPEN there too — no conflict with our swap
# (different mechanisms: clock/deadline vs mix/turnover; expected to stack).
EXPERIMENT = {'midnight': True, 'terminal': True, 'last_water': True}


class DeadlineExec(StigExec):
    def pick_crop(self, ctx, st, seeds_left, tgts):
        if EXPERIMENT.get('midnight') and ctx.hour >= 23:
            return None
        return super().pick_crop(ctx, st, seeds_left, tgts)

    def fert_pays(self, ctx, t):
        if EXPERIMENT.get('last_water') and ctx.hour >= 23 and not t.get('watered_today') and int(t.get('consecutive_unwatered', 0)) >= 1:
            return False
        return super().fert_pays(ctx, t)

    def run(self, ctx):
        if EXPERIMENT.get('terminal') and ctx.day == 29:
            return self.terminal(ctx)
        return super().run(ctx)

    def terminal(self, ctx):
        # Full terminal phase, not a feed-priority adjustment. Every job must
        # leave time for the actual final DROP. There is no final EOD rescue.
        positions = [tuple(ctx.farmer)] + [tuple(p) for p in ctx.hands]
        taken, reserved = set(), set()
        remaining = dict(ctx.shed)
        units = [dict(v or {}) for v in ctx.invs]
        for i, pos in enumerate(positions):
            inv = units[i]
            load = sum(int(inv.get(k, 0) or 0) for k in PRODUCTS)
            home = nearest_shed_tile(pos)
            home_dist = manhattan(pos, home)
            tile = self.tile_at(ctx, *pos)
            cmd = None
            if load and pos in SHED_TILES_SET:
                room = max(0, 100 - sum(int(v or 0) for v in remaining.values()))
                if load <= room:
                    cmd = ['DROP']
                    for k in PRODUCTS:
                        remaining[k] = int(remaining.get(k, 0) or 0) + int(inv.get(k, 0) or 0)
                elif room:
                    k = max(PRODUCTS, key=lambda k: int(inv.get(k, 0) or 0))
                    qty = min(room, int(inv.get(k, 0) or 0))
                    cmd = ['PLACE', k, qty]
                    remaining[k] = int(remaining.get(k, 0) or 0) + qty
                else:
                    cmd = ['PASS']
            elif load and ctx.hour + home_dist >= 22:
                cmd = step_toward(pos, home)
            if cmd is None and pos not in taken:
                cmd = self.terminal_tile(ctx, tile, pos)
                if cmd:
                    taken.add(pos)
            if cmd is None:
                choices = []
                for y, row in enumerate(ctx.tiles):
                    for x, t in enumerate(row):
                        target = (x, y)
                        if target in taken or target in reserved or target == pos:
                            continue
                        job = self.terminal_tile(ctx, t, target)
                        if job is None:
                            continue
                        distance = manhattan(pos, target)
                        back = manhattan(target, nearest_shed_tile(target))
                        service = 2 if job[0] == 'WATER' else 1
                        # Arrive, execute service, return, then DROP no later h22.
                        if ctx.hour + distance + service + back > 22:
                            continue
                        choices.append((distance, -int((t or {}).get('yield_units', 0) or 0), y, x))
                if load >= STIG_BANK_LOAD or not choices:
                    cmd = step_toward(pos, home) if load else ['PASS']
                elif choices:
                    _, _, ty, tx = min(choices)
                    reserved.add((tx, ty))
                    cmd = step_toward(pos, (tx, ty))
            cmd = cmd or ['PASS']
            ctx.unit_cmds[i] = cmd
            key = 'stig_' + cmd[0]
            T['exec_tasks'][key] = T['exec_tasks'].get(key, 0) + 1
        # Unit deposits happen BEFORE market. Sell precisely the projected
        # shelf, not a fake assumption that carried items are already banked.
        sells = [['SELL', k, int(remaining.get(k, 0) or 0)] for k in PRODUCTS if int(remaining.get(k, 0) or 0) > 0]
        hires = [o for o in ctx.orders if o and o[0] == 'HIRE']
        ctx.orders = (sells + hires)[:10]

    def terminal_tile(self, ctx, tile, pos):
        if not isinstance(tile, dict):
            return None
        back = manhattan(pos, nearest_shed_tile(pos))
        if ctx.hour + 1 + back > 22:
            return None
        yld = int(tile.get('yield_units', 0) or 0)
        if tile.get('animal'):
            if yld > 0:
                return ['HARVEST']
            if tile.get('fertilizer_available'):
                return ['COLLECT_FERTILIZER']
        if tile.get('kind') == 'PLANT':
            cd = CROPS.get(tile.get('crop'), {})
            age = ctx.day - int(tile.get('planted_day', 0) or 0)
            if age < cd.get('first', 99):
                return None
            if (not cd.get('ongoing') and not tile.get('watered_today')
                    and (cd.get('maxday', 0) + 1) // 2 <= age <= cd.get('maxday', 0)
                    and yld < cd.get('maxyield', 0) and ctx.hour + 2 + back <= 22):
                return ['WATER']
            if yld > 0:
                return ['HARVEST']
        return None


STIG = DeadlineExec()


# Submission entry point MUST be the last callable in this file: the platform
# loader (kaggle_environments.agent.get_last_callable) execs the module and
# takes the LAST callable in namespace order. A trailing DeadlineExec class
# (or STIG instance) shadowed agent() and the platform called
# DeadlineExec(obs, config) -> "Layer.__init__() takes 1 positional argument
# but 3 were given" (submission error 114860263). Keep this def last.
def agent(observation, configuration=None):
    try:
        T['steps'] += 1
        ctx = Ctx(observation)
        SCHED(ctx)
        MARKET(ctx)
        STIG(ctx)
        n = 1 + len(ctx.hands)
        hands = [ctx.unit_cmds.get(i, ['PASS']) for i in range(1, n)]
        return {'farmer': ctx.unit_cmds.get(0, ['PASS']), 'hands': hands, 'market': ctx.orders}
    except Exception:
        T['errors'] += 1
        return {'farmer': ['PASS'], 'hands': [], 'market': []}

