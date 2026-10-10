# ---- natural-language day parsing (English), relative to `today` and the spec's weekday rules ----
_ONES = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen']
_ORD1 = ['zeroth', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth', 'eleventh', 'twelfth', 'thirteenth', 'fourteenth', 'fifteenth', 'sixteenth', 'seventeenth', 'eighteenth', 'nineteenth']
_TENS = dict(zip(['twenty', 'thirty'], [20, 30]))
_TENS_ORD = dict(zip(['twentieth', 'thirtieth'], [20, 30]))

def word_number(s):
    """'twenty-sixth' -> 26, 'six' -> 6, '26th' -> 26. None if not a number."""
    s = str(s).lower().strip().replace('-', ' ')
    m = re.match(r'^(\d+)(st|nd|rd|th)?$', s)
    if m:
        return int(m.group(1))
    parts = s.split()
    total = 0
    ok = False
    for p in parts:
        if p in _ONES:
            total += _ONES.index(p); ok = True
        elif p in _ORD1:
            total += _ORD1.index(p); ok = True
        elif p in _TENS:
            total += _TENS[p]; ok = True
        elif p in _TENS_ORD:
            total += _TENS_ORD[p]; ok = True
        elif p in ('and', 'the', 'of'):
            continue
        else:
            return None
    return total if ok else None

VAGUE = ['next week', 'week after', 'end of', 'beginning of', 'start of', 'salary', 'pay day', 'payday', 'paycheck', 'couple of', 'few days', 'few weeks', 'sometime', 'some time', 'later', 'soon', 'as soon', 'when i', 'after i', 'month', 'not sure', 'maybe', 'around the', 'mid']

def _month_index(tok):
    t = tok.lower()[:3]
    for i, m in enumerate(MONTHS):
        if m.lower()[:3] == t:
            return i + 1
    return None

def _weekday_index(tok):
    t = tok.lower()[:3]
    for i, w in enumerate(WD_SHORT):
        if w.lower() == t:
            return i
    return None

def resolve_weekday(today, wd, qualifier):
    """qualifier: 'this' | 'next' | '' following SPEC.calendar rules."""
    c = SPEC.get('calendar') or dict()
    nxt_rule = str(c.get('next_weekday_means') or 'following calendar week')
    this_rule = str(c.get('this_weekday_means') or 'current week')
    mon = today - datetime.timedelta(days=today.weekday())
    if qualifier == 'next':
        if 'occurrence' in nxt_rule:
            d = today + datetime.timedelta(days=1)
            while d.weekday() != wd:
                d = d + datetime.timedelta(days=1)
            return d
        return mon + datetime.timedelta(days=7 + wd)
    if qualifier == 'this':
        if 'occurrence' in this_rule:
            d = today
            while d.weekday() != wd:
                d = d + datetime.timedelta(days=1)
            return d
        return mon + datetime.timedelta(days=wd)
    d = today + datetime.timedelta(days=1)
    while d.weekday() != wd:
        d = d + datetime.timedelta(days=1)
    return d

def parse_day_text(text, today):
    """Returns (date or None, status) with status in ok | vague | unknown."""
    s = str(text or '').lower().strip()
    s = re.sub(r'[,.!?]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    if not s or s == '-':
        return None, 'unknown'
    if 'day after tomorrow' in s:
        return today + datetime.timedelta(days=2), 'ok'
    if 'tomorrow' in s:
        return today + datetime.timedelta(days=1), 'ok'
    if re.search(r'\btoday\b|\bnow\b|right away', s):
        return today, 'ok'
    m = re.search(r'(\d\d\d\d)-(\d\d)-(\d\d)', s)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))), 'ok'
        except Exception:
            return None, 'unknown'
    m = re.search(r'\b(\d\d?)[/.](\d\d?)(?:[/.](\d\d(?:\d\d)?))?\b', s)
    if m:
        try:
            y = int(m.group(3)) if m.group(3) else today.year
            if y < 100:
                y += 2000
            d = datetime.date(y, int(m.group(2)), int(m.group(1)))
            if not m.group(3) and d < today:
                d = datetime.date(y + 1, int(m.group(2)), int(m.group(1)))
            return d, 'ok'
        except Exception:
            return None, 'unknown'
    toks = s.split()
    month = None
    for t in toks:
        if len(t) >= 3 and _month_index(t) and t[:3] in [x.lower()[:3] for x in MONTHS]:
            month = _month_index(t)
            break
    wd = None
    qual = ''
    for i, t in enumerate(toks):
        if len(t) >= 3 and _weekday_index(t) is not None and t[:3] in [x.lower() for x in WD_SHORT]:
            wd = _weekday_index(t)
            if i > 0 and toks[i - 1] in ('this', 'next', 'coming'):
                qual = 'next' if toks[i - 1] == 'next' else 'this'
            break
    day = None
    year = None
    m = re.search(r'\b(20\d\d)\b', s)
    if m:
        year = int(m.group(1))
    for t in toks:
        if re.match(r'^\d\d?(st|nd|rd|th)?$', t) and not (year and t == str(year)):
            v = int(re.sub(r'\D', '', t))
            if 1 <= v <= 31:
                day = v
                break
    if day is None:
        ws = re.sub(r'\b(the|of|on|this|next|coming|in|at|around|about|by|for|a|an|to|pay|i|can|will|could)\b', ' ', s)
        ws = re.sub(r'\s+', ' ', ws).strip()
        cand = []
        for n in range(1, 4):
            for i in range(0, max(0, len(ws.split()) - n + 1)):
                chunk = ' '.join(ws.split()[i:i + n])
                v = word_number(chunk)
                if v is not None and 1 <= v <= 31 and not _month_index(chunk) and _weekday_index(chunk) is None:
                    cand.append((n, v))
        if cand:
            cand.sort()
            day = cand[-1][1]
    if day is not None:
        y = year or today.year
        if month is None:
            d = None
            for k in range(0, 3):
                mo = today.month + k
                yy = y + (mo - 1) // 12
                mo = (mo - 1) % 12 + 1
                try:
                    cand_d = datetime.date(yy, mo, day)
                except Exception:
                    continue
                if cand_d >= today:
                    d = cand_d
                    break
            if d is None:
                return None, 'unknown'
            return d, 'ok'
        try:
            d = datetime.date(y, month, day)
        except Exception:
            return None, 'unknown'
        if not year and d < today - datetime.timedelta(days=30):
            d = datetime.date(y + 1, month, day)
        return d, 'ok'
    if wd is not None:
        return resolve_weekday(today, wd, qual), 'ok'
    for v in VAGUE:
        if v in s:
            return None, 'vague'
    return None, 'unknown'

def parse_time_text(text):
    """'11:00', '11 am', 'around eleven', 'half past five', 'eleven thirty', 'noon' -> 'HH:MM' or ''."""
    s = str(text or '').lower().strip().replace('.', ':')
    if not s or s == '-':
        return ''
    if re.search(r'\bnoon\b|\bmidday\b', s):
        return '12:00'
    m = re.search(r'\b(\d\d?):(\d\d)\s*(am|pm|a m|p m)?', s)
    if m:
        h = int(m.group(1)); mi = int(m.group(2)); ap = (m.group(3) or '').replace(' ', '')
        if ap == 'pm' and h < 12: h += 12
        if ap == 'am' and h == 12: h = 0
        return '%02d:%02d' % (h, mi)
    m = re.search(r'\b(\d\d?)\s*(am|pm|a m|p m|o\'?clock)?', s)
    hour = None
    if m:
        hour = int(m.group(1)); ap = (m.group(2) or '').replace(' ', '')
        if ap == 'pm' and hour < 12: hour += 12
        if ap == 'am' and hour == 12: hour = 0
    else:
        ws = re.sub(r'\b(around|about|at|the|in|morning|afternoon|evening|o\'clock|oclock|half|past|quarter|to|after)\b', ' ', s)
        for n in (2, 1):
            toks = ws.split()
            for i in range(0, max(0, len(toks) - n + 1)):
                v = word_number(' '.join(toks[i:i + n]))
                if v is not None and 0 <= v <= 23:
                    hour = v
                    break
            if hour is not None:
                break
    if hour is None:
        return ''
    minute = 0
    if 'half past' in s:
        minute = 30
    elif 'quarter past' in s:
        minute = 15
    elif 'quarter to' in s:
        minute = 45; hour -= 1
    else:
        ws = re.sub(r'\b(\d\d?)\b', ' ', s)
        m2 = re.search(r'\b(thirty|fifteen|forty five|forty-five|twenty|ten|five)\b', ws)
        if m2 and hour is not None and 'half' not in s:
            v = word_number(m2.group(1))
            if v is not None and 0 < v < 60:
                minute = v
    if ('afternoon' in s or 'evening' in s or 'tonight' in s) and hour < 12:
        hour += 12
    elif hour is not None and 1 <= hour <= 6 and not re.search(r'\bam\b|a m|morning', s):
        hour += 12
    if ('morning' in s) and hour == 12:
        hour = 0
    if hour < 0 or hour > 23:
        return ''
    return '%02d:%02d' % (hour, minute)
