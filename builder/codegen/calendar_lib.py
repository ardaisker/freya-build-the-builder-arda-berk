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

def products_from_vars():
    """get_account products: a list, a JSON string, or flattened keys. Returns a list of dicts."""
    cands = [getv('account_products'), getv('get_account_response.data.products'), getv('get_account_response.data')]
    for c in cands:
        if isinstance(c, dict) and isinstance(c.get('products'), list):
            return c['products']
        if isinstance(c, list):
            return c
        if isinstance(c, str) and c.strip().startswith('['):
            try:
                return json.loads(c)
            except Exception:
                pass
        if isinstance(c, str) and c.strip().startswith('\x7b'):
            try:
                o = json.loads(c)
                if isinstance(o.get('products'), list):
                    return o['products']
            except Exception:
                pass
    out = []
    for i in range(10):
        pre = 'get_account_response.data.products.' + str(i) + '.'
        pid = vars.get(pre + 'product_id')
        if pid is None:
            break
        p = dict()
        for k in ('product_id', 'type', 'card_last4', 'past_due', 'days_late', 'minimum_payment', 'instalment_amount'):
            if vars.get(pre + k) is not None:
                p[k] = vars.get(pre + k)
        out.append(p)
    return out

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

def floor_of(p):
    fb = (SPEC.get('amounts') or dict()).get('floor_by_type') or dict()
    field = fb.get(str(p.get('type')))
    if field and p.get(field) is not None:
        return p.get(field)
    for k in ('minimum_payment', 'instalment_amount'):
        if p.get(k) is not None:
            return p.get(k)
    return p.get('past_due')

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
    """Per-product dict list: id, label, amounts, band, deadline, floor, attempts, attempt dates."""
    out = []
    att1 = last_business_of_week(today, 0)
    if att1 is None or att1 <= today:
        att1 = last_business_of_week(today, 1)
    for p in products_from_vars():
        b = band_for(p.get('days_late'))
        f = dict()
        f['product_id'] = str(p.get('product_id') or '')
        f['type'] = str(p.get('type') or '')
        f['label'] = label_of(p)
        f['past_due'] = p.get('past_due')
        f['days_late'] = p.get('days_late')
        f['band'] = str(b.get('name') or '')
        try:
            dl = business_after(today, int(b.get('deadline_business_days_after_today', 7)))
        except Exception:
            dl = business_after(today, 7)
        f['deadline'] = dl.isoformat()
        f['floor'] = floor_of(p)
        try:
            f['attempts'] = int(b.get('persuasion_attempts', 1))
        except Exception:
            f['attempts'] = 1
        f['attempt1_date'] = att1.isoformat() if att1 else dl.isoformat()
        out.append(f)
    return out
