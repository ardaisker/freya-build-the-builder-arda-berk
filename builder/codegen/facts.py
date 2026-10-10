# ---- compute_facts: runs once after get_account. Writes `facts` (text for the prompts) and `pf_json`. ----
try:
    today, now_time = parse_now(getv('now'))
    pf = product_facts(today)
    lines = []
    lines.append('TODAY is ' + fmt(today) + ', time ' + now_time + '. Use only this date. Never the real clock.')
    bd = []
    x = today
    for _ in range(60):
        x = x + datetime.timedelta(days=1)
        if is_business(x):
            bd.append(fmt(x))
        if len(bd) >= 16:
            break
    lines.append('BUSINESS DAYS AFTER TODAY (a payment day must be today or one of these): ' + '; '.join(bd) + '.')
    hol = []
    for h in sorted(_cal()[1]):
        if today <= h <= today + datetime.timedelta(days=70):
            hol.append(fmt(h))
    lines.append('BANK HOLIDAYS (never a payment day): ' + (', '.join(hol) if hol else 'none in the next weeks') + '.')
    mon = today - datetime.timedelta(days=today.weekday())
    tw = []
    nw = []
    for i in range(7):
        d1 = mon + datetime.timedelta(days=i)
        d2 = mon + datetime.timedelta(days=7 + i)
        tw.append('this ' + WD_NAMES[i] + ' = ' + str(d1.day) + ' ' + MONTHS[d1.month - 1] + ('' if is_business(d1) else ' (not a business day)') + (' (past)' if d1 < today else ''))
        nw.append('next ' + WD_NAMES[i] + ' = ' + str(d2.day) + ' ' + MONTHS[d2.month - 1] + ('' if is_business(d2) else ' (not a business day)'))
    lines.append('WEEKDAY NAMES: ' + '; '.join(tw) + '. ' + '; '.join(nw) + '. A bare weekday name means the next one after today.')
    att1 = last_business_of_week(today, 0)
    if att1 is None or att1 <= today:
        att1 = last_business_of_week(today, 1)
    lines.append('PERSUASION ATTEMPT-1 DATE: ' + fmt(att1) + '.')
    if is_business(today):
        lines.append('Today is a business day, so "today" is an allowed payment day.')
    else:
        lines.append('Today is NOT a business day. The first allowed payment day is ' + fmt(next_business(today)) + '.')
    for f in pf:
        dl = datetime.date.fromisoformat(f['deadline'])
        plan = 'ATTEMPT PLAN for ' + f['product_id'] + ': attempt 1 = ' + money(f['past_due']) + ' (or the floor ' + money(f['floor']) + ' if the full amount was too much) on ' + fmt(att1) + '.'
        if f['attempts'] >= 2:
            plan += ' Attempt 2 = the floor ' + money(f['floor']) + ' on ' + fmt(dl) + '. After attempt 2 is refused: stop asking about this product.'
        else:
            plan += ' NO attempt 2 for this product: after attempt 1 is refused, stop asking about it at once.'
        lines.append('PRODUCT ' + f['product_id'] + ': ' + f['label'] + '. Past due ' + money(f['past_due']) + ', ' + str(f['days_late']) + ' days late, band "' + f['band'] + '". LATEST PAYMENT DATE (deadline) ' + fmt(dl) + '. FLOOR (lowest amount you may accept) ' + money(f['floor']) + '. Persuasion attempts allowed: ' + str(f['attempts']) + '. ' + plan)
    if len(pf) > 1:
        lines.append('There are ' + str(len(pf)) + ' late products, in this order: ' + ', '.join([f['product_id'] + ' ' + f['label'] for f in pf]) + '.')
    vars['facts'] = '\n'.join(lines)
    vars['pf_json'] = json.dumps(pf)
    vars['product_count'] = str(len(pf))
    vars['facts_state'] = 'ok' if pf else 'no_products'
    vars['today_iso'] = today.isoformat()
except Exception as e:
    vars['facts'] = 'Account facts are unavailable. Say you cannot access the account right now and close the call.'
    vars['pf_json'] = '[]'
    vars['product_count'] = '0'
    vars['facts_state'] = 'error'
    vars['today_iso'] = ''
vars['date_verdict'] = '-'
vars['customer_date_text'] = '-'
vars['promises_log'] = getv('promises_log', '')
vars['notes_log'] = getv('notes_log', '')
