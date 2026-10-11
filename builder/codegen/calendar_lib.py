# ---- calendar helpers (shared by every code node) ----
WD_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
WD_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

def _cal():
    c = SPEC.get('calendar') or dict()
    wds = c.get('business_weekdays') or ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    idx = []
    for w in wds:
        w3 = str(w)[:3].title()
        if w3 in WD_SHORT:
            idx.append(WD_SHORT.index(w3))
    hol = set()
    for h in c.get('holidays') or []:
        try:
            hol.add(datetime.date.fromisoformat(str(h)[:10]))
        except Exception:
            pass
    return idx or [0, 1, 2, 3, 4], hol

def parse_now(v):
    s = str(v or '').strip()
    try:
        d = datetime.date.fromisoformat(s[:10])
    except Exception:
        d = datetime.date.today()
    t = '00:00'
    m = re.search(r'T(\d\d:\d\d)', s)
    if m:
        t = m.group(1)
    return d, t

def is_business(d):
    idx, hol = _cal()
    return d.weekday() in idx and d not in hol

def is_holiday(d):
    idx, hol = _cal()
    return d in hol

def next_business(d):
    x = d
    for _ in range(60):
        if is_business(x):
            return x
        x = x + datetime.timedelta(days=1)
    return x

def business_after(d, n):
    x = d
    k = 0
    for _ in range(400):
        x = x + datetime.timedelta(days=1)
        if is_business(x):
            k += 1
            if k >= n:
                return x
    return x

def last_business_of_week(d, week_offset):
    mon = d - datetime.timedelta(days=d.weekday()) + datetime.timedelta(days=7 * week_offset)
    x = mon + datetime.timedelta(days=6)
    for _ in range(7):
        if is_business(x):
            return x
        x = x - datetime.timedelta(days=1)
    return None

def fmt(d):
    return WD_NAMES[d.weekday()] + ' ' + str(d.day) + ' ' + MONTHS[d.month - 1] + ' ' + str(d.year)

def money(x):
    try:
        return '%.2f' % float(x)
    except Exception:
        return str(x)

def getv(name, default=''):
    v = vars.get(name)
    if isinstance(v, dict) and 'value' in v and len(v) <= 6:
        v = v.get('value')
    if v is None:
        return default
    return v

def _api(tool):
    return ((SPEC.get('api') or dict()).get('tools') or dict()).get(tool) or dict()

def now_value():
    name = ((SPEC.get('api') or dict()).get('call_vars') or dict()).get('now') or 'now'
    return getv(name)

def _norm(p):
    """One product with the names the rest of the code uses, whatever the API calls its fields."""
    g = _api('get_account')
    q = dict(p)
    q['product_id'] = p.get(g.get('product_id') or 'product_id')
    q['type'] = p.get(g.get('type') or 'type')
    q['past_due'] = p.get(g.get('past_due') or 'past_due')
    q['days_late'] = p.get(g.get('days_late') or 'days_late')
    return q

def products_from_vars():
    """get_account products: a list, a JSON string, or flattened keys. Returns a list of normalised dicts."""
    g = _api('get_account')
    key = g.get('products') or 'products'
    found = None
    cands = [getv('account_products'), getv('get_account_response.data.' + key), getv('get_account_response.data')]
    for c in cands:
        if isinstance(c, dict) and isinstance(c.get(key), list):
            found = c[key]
        elif isinstance(c, list):
            found = c
        elif isinstance(c, str) and c.strip().startswith('['):
            try:
                found = json.loads(c)
            except Exception:
                pass
        elif isinstance(c, str) and c.strip().startswith('\x7b'):
            try:
                o = json.loads(c)
                if isinstance(o.get(key), list):
                    found = o[key]
            except Exception:
                pass
        if found:
            break
    if not found:
        found = []
        for i in range(10):
            pre = 'get_account_response.data.' + key + '.' + str(i) + '.'
            p = dict()
            for k in list(vars.keys()):
                if str(k).startswith(pre) and vars.get(k) is not None:
                    p[str(k)[len(pre):]] = getv(k)
            if not p:
                break
            found.append(p)
    return [_norm(p) for p in found if isinstance(p, dict)]

def band_for(days_late):
    try:
        dl = int(float(days_late))
    except Exception:
        dl = 0
    for b in SPEC.get('bands') or []:
        try:
            if int(b.get('days_late_min', 0)) <= dl <= int(b.get('days_late_max', 10**6)):
                return b
        except Exception:
            pass
    bands = SPEC.get('bands') or []
    return bands[-1] if bands else dict()

def _num(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def floor_of(p):
    am = SPEC.get('amounts') or dict()
    fb = am.get('floor_by_type') or dict()
    field = fb.get(str(p.get('type')))
    if field and p.get(field) is not None:
        return p.get(field)
    pct = _num(am.get('floor_percent_of_past_due'))
    if pct > 0:
        return round(_num(p.get('past_due')) * pct / 100.0, 2)
    fixed = _num(am.get('floor_fixed_amount'))
    if fixed > 0:
        return min(fixed, _num(p.get('past_due'), fixed))
    return p.get('past_due')

def rule_date(rule, today, deadline):
    """A date from a date-rule object of the spec (see spec_schema.json). None if the rule is unknown."""
    r = rule if isinstance(rule, dict) else dict()
    ty = str(r.get('type') or '')
    n = int(_num(r.get('n')))
    one = datetime.timedelta(days=1)
    d = None
    if ty == 'today':
        d = next_business(today)
    elif ty == 'deadline':
        d = deadline
    elif ty == 'next_business_day':
        d = next_business(today + one)
    elif ty == 'business_days_after_today':
        d = business_after(today, n) if n > 0 else next_business(today)
    elif ty == 'calendar_days_after_today':
        d = today + datetime.timedelta(days=n)
        if str(r.get('roll') or 'next') == 'previous':
            for _ in range(10):
                if is_business(d) or d <= today:
                    break
                d = d - one
            d = next_business(d)
        else:
            d = next_business(d)
    elif ty == 'last_business_day_of_week':
        w = int(_num(r.get('week')))
        d = last_business_of_week(today, w)
        skip_today = r.get('if_today_use_next_week')
        if d is None or d < today or (d == today and skip_today is not False):
            d = last_business_of_week(today, w + 1)
    elif ty == 'end_of_month':
        y = today.year
        m = today.month
        for _ in range(2):
            nxt = datetime.date(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
            d = nxt - one
            for _k in range(10):
                if is_business(d):
                    break
                d = d - one
            if d >= today:
                break
            y = nxt.year
            m = nxt.month
    return d

KNOWN_DATE_RULES = ['today', 'deadline', 'next_business_day', 'business_days_after_today', 'calendar_days_after_today', 'last_business_day_of_week', 'end_of_month']

def rule_text(rule):
    """The bank's own wording of a date rule this code cannot compute; '' when it can compute it."""
    r = rule if isinstance(rule, dict) else dict()
    if str(r.get('type') or '') in KNOWN_DATE_RULES:
        return ''
    return str(r.get('text') or '').strip()

def deadline_text(band):
    """Not empty when the latest payment date cannot be computed here. Then the phone agent works from the bank's
    wording instead of a computed (and possibly wrong) date, and no code check is tied to it."""
    try:
        if int(_num(band.get('deadline_business_days_after_today'))) > 0:
            return ''
        r = band.get('deadline_rule')
        if isinstance(r, dict) and str(r.get('type') or '') in KNOWN_DATE_RULES:
            return ''
        t = rule_text(r) or str(band.get('deadline_text') or '').strip()
        return t or 'the bank\'s rule for the latest payment date, as given in your instructions'
    except Exception:
        return ''

def floor_text(p):
    """Not empty when the lowest acceptable amount cannot be computed here: the bank's wording of the rule."""
    try:
        am = SPEC.get('amounts') or dict()
        fb = am.get('floor_by_type') or dict()
        field = fb.get(str(p.get('type')))
        if field and p.get(field) is not None:
            return ''
        if _num(am.get('floor_percent_of_past_due')) > 0 or _num(am.get('floor_fixed_amount')) > 0:
            return ''
        return str(am.get('floor_rule_text') or '').strip()
    except Exception:
        return ''

def floor_say(f):
    if f.get('floor_text'):
        return 'the lowest amount the bank accepts (not computed by the system; work it out from this rule: "' + str(f.get('floor_text')) + '")'
    return money(f['floor'])

def deadline_say(f):
    if f.get('deadline_text'):
        return 'NOT COMPUTED by the system: work it out yourself from TODAY, the business-day list and this rule of the bank: "' + str(f.get('deadline_text')) + '"'
    return fmt(datetime.date.fromisoformat(f['deadline']))

def offer_date_say(o):
    if o.get('date_text'):
        return str(o.get('date_text'))
    return fmt(datetime.date.fromisoformat(o['date']))

def deadline_of(band, today):
    d = rule_date(band.get('deadline_rule'), today, None) if isinstance(band.get('deadline_rule'), dict) else None
    if d is None:
        n = int(_num(band.get('deadline_business_days_after_today')))
        d = business_after(today, n) if n > 0 else next_business(today)
    return d

def offers_for(band, n_allowed, today, deadline, soft_deadline=''):
    """The persuasion offers of one product: a list of dicts (amount kind, date), from spec.persuasion.attempts."""
    out = []
    for a in (SPEC.get('persuasion') or dict()).get('attempts') or []:
        if not isinstance(a, dict):
            continue
        bands = a.get('bands')
        if isinstance(bands, list) and bands and str(band.get('name')) not in [str(x) for x in bands]:
            continue
        if len(out) >= n_allowed:
            break
        d = rule_date(a.get('date_rule'), today, deadline)
        dtxt = ''
        if d is None:
            dtxt = rule_text(a.get('date_rule'))
            if not dtxt:
                continue
            dtxt = 'the day this rule of the bank gives (work it out yourself): "' + dtxt + '"'
            d = deadline if deadline is not None else today
        elif soft_deadline and str((a.get('date_rule') or dict()).get('type') or '') == 'deadline':
            dtxt = 'the latest payment date (work it out yourself from this rule of the bank: "' + soft_deadline + '")'
        if deadline is not None and d > deadline:
            d = deadline
        o = dict()
        o['amount'] = str(a.get('amount') or 'full')
        o['date'] = d.isoformat()
        if dtxt:
            o['date_text'] = dtxt
        out.append(o)
    return out

def offer_amount_text(o, f):
    kind = str(o.get('amount') or 'full')
    if kind == 'floor':
        return floor_say(f)
    return money(f['past_due'])

def label_of(p):
    pw = (SPEC.get('debt_statement') or dict()).get('product_wording') or dict()
    t = str(p.get('type') or 'product')
    w = pw.get(t) or t.replace('_', ' ')
    try:
        w = w.replace('\x7bcard_last4\x7d', str(p.get('card_last4') or ''))
        w = re.sub(r'\x7b(\w+)\x7d', lambda m: str(p.get(m.group(1)) or ''), w)
    except Exception:
        pass
    return w.strip()

def product_facts(today):
    """Per-product dict list: id, label, amounts, band, deadline, floor, attempts, offers."""
    out = []
    for p in products_from_vars():
        b = band_for(p.get('days_late'))
        f = dict()
        f['product_id'] = str(p.get('product_id') or '')
        f['type'] = str(p.get('type') or '')
        f['label'] = label_of(p)
        f['past_due'] = p.get('past_due')
        f['days_late'] = p.get('days_late')
        f['band'] = str(b.get('name') or '')
        dl = deadline_of(b, today)
        soft = deadline_text(b)
        if soft:
            dl = today + datetime.timedelta(days=120)       # no computed limit: nothing in code is tied to it
            f['deadline_text'] = soft
        f['deadline'] = dl.isoformat()
        ft = floor_text(p)
        if ft:
            f['floor_text'] = ft
            f['floor'] = 0
        else:
            f['floor'] = floor_of(p)
        f['attempts'] = int(_num(b.get('persuasion_attempts'), 1))
        f['offers'] = offers_for(b, f['attempts'], today, dl, soft)
        out.append(f)
    return out
