# ---- tp_resolve: someone else answered and named a callback day/time. Validate against the callback window. ----
try:
    today, now_time = parse_now(now_value())
    cb = (SPEC.get('third_party') or dict()).get('callback') or dict()
    day_text = str(getv('callback_day_text', '')).strip()
    time_text = str(getv('callback_time_text', '')).strip()
    try:
        attempts = int(float(getv('tp_attempts', '0') or 0))
    except Exception:
        attempts = 0
    d, dstatus = parse_day_text(day_text, today)
    t = parse_time_text(time_text)
    if day_text in ('', '-') and str(getv('tp_day_keep', '')):
        try:
            d = datetime.date.fromisoformat(str(getv('tp_day_keep', '')))
            dstatus = 'ok'
        except Exception:
            pass
    if not t and str(getv('tp_time_keep', '')):
        t = str(getv('tp_time_keep', ''))
    if d is None and t and re.search(r'\b(tonight|this (morning|afternoon|evening)|later today)\b', (day_text + ' ' + time_text).lower()):
        d = today
    complete = (d is not None) and bool(t)
    allowed = str(cb.get('allowed_days') or '')
    try:
        max_ahead = int(cb.get('max_days_ahead', 1))
    except Exception:
        max_ahead = 1
    if not allowed:
        allowed = 'any'                     # the material names no day limit: any of the next business days
        max_ahead = max(max_ahead, 10)
    okdays = []
    if ('today' in allowed or 'any' in allowed) and cb.get('include_today') is not False:
        okdays.append(today)
    nb = next_business(today + datetime.timedelta(days=1))
    if 'next_business' in allowed or 'any' in allowed:
        okdays.append(nb)
    if 'any' in allowed:
        x = today
        for _ in range(max_ahead):
            x = next_business(x + datetime.timedelta(days=1))
            if x not in okdays:
                okdays.append(x)
    frm = str(cb.get('from') or '00:00')
    to = str(cb.get('to') or '23:59')
    # a day outside the allowed days, or a time outside the hours, is already a proposal that cannot work
    decided = complete or (d is not None and d not in okdays) or (bool(t) and (t < frm or t > to))
    vars['tp_day_keep'] = d.isoformat() if (d is not None and not decided) else ''
    vars['tp_time_keep'] = t if not decided else ''
    if decided:
        attempts += 1
        vars['tp_attempts'] = str(attempts)
    problems = []
    if d is None:
        if complete or not decided:
            problems.append('no exact day')
    elif d not in okdays:
        problems.append(fmt(d) + ' is outside the allowed days (' + ' or '.join([fmt(x) for x in okdays]) + ')')
    if not t:
        if not decided:
            problems.append('no exact time')
    else:
        if t < frm or t > to:
            problems.append(t + ' is outside ' + frm + ' to ' + to)
        if d is not None and d == today and cb.get('must_be_after_now', True) and t <= now_time:
            problems.append(t + ' today is not later than now (' + now_time + ')')
    if not decided:
        vars['tp_status'] = 'retry'
        vars['tp_verdict'] = 'CALLBACK CHECK: ' + ('the day is known (' + fmt(d) + ') but not the time: ask at what time.' if d is not None else ('the time is known (' + t + ') but not the day: ask on which day.' if t else 'no day and no time were understood: ask when the customer can be reached, with day and time.'))
    elif not problems:
        vars['callback_date'] = d.isoformat()
        vars['callback_time'] = t
        vars['callback_say'] = fmt(d) + ' at ' + t
        vars['tp_status'] = 'ok'
        vars['tp_verdict'] = 'CALLBACK CHECK: ' + fmt(d) + ' at ' + t + ' is inside the window. Confirm it to the caller and say goodbye.'
    else:
        window = 'today (after ' + now_time + ')' if today in okdays else ''
        if nb in okdays:
            window = (window + ' or ' if window else '') + fmt(nb)
        window += ', between ' + frm + ' and ' + to
        if attempts <= 1 and cb.get('ask_again_once', True):
            vars['tp_status'] = 'retry'
            vars['tp_verdict'] = 'CALLBACK CHECK: the proposed time is not possible (' + '; '.join(problems) + '). Ask ONCE for another time: ' + window + '.'
        else:
            vars['tp_status'] = 'no'
            vars['tp_verdict'] = 'CALLBACK CHECK: the second proposal is also not possible (' + '; '.join(problems) + '). Do not schedule anything. Say you will try again another time and say goodbye.'
except Exception as e:
    vars['tp_status'] = 'no'
    vars['tp_verdict'] = 'CALLBACK CHECK: could not check the time. Do not schedule anything. Say goodbye.'
vars['callback_day_text'] = '-'
vars['callback_time_text'] = '-'
