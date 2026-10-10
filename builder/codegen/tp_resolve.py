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
    attempts += 1
    vars['tp_attempts'] = str(attempts)
    d, dstatus = parse_day_text(day_text, today)
    if d is None and day_text in ('', '-'):
        d = today
        dstatus = 'ok'
    t = parse_time_text(time_text)
    allowed = str(cb.get('allowed_days') or 'today_or_next_business_day')
    try:
        max_ahead = int(cb.get('max_days_ahead', 1))
    except Exception:
        max_ahead = 1
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
    problems = []
    if d is None:
        problems.append('no exact day')
    elif d not in okdays:
        problems.append(fmt(d) + ' is outside the allowed days (' + ' or '.join([fmt(x) for x in okdays]) + ')')
    if not t:
        problems.append('no exact time')
    else:
        if t < frm or t > to:
            problems.append(t + ' is outside ' + frm + ' to ' + to)
        if d is not None and d == today and cb.get('must_be_after_now', True) and t <= now_time:
            problems.append(t + ' today is not later than now (' + now_time + ')')
    if not problems:
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
