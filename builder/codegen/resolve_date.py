# ---- resolve_date: the customer named a payment day. Turn it into a date and a verdict the agent can act on. ----
try:
    today, now_time = parse_now(getv('now'))
    text = str(getv('customer_date_text', '')).strip()
    try:
        pf = json.loads(getv('pf_json', '[]') or '[]')
    except Exception:
        pf = []
    d, status = parse_day_text(text, today)
    verdict = ''
    resolved = ''
    if status == 'vague':
        dls = sorted(set([f['deadline'] for f in pf]))
        prop = ', '.join([fmt(datetime.date.fromisoformat(x)) for x in dls]) if dls else 'the deadline'
        verdict = 'DATE CHECK: "' + text + '" is not an exact day. Ask once for the exact day. If the customer still gives none, propose the latest allowed date: ' + prop + '.'
        status = 'vague'
    elif d is None:
        verdict = 'DATE CHECK: "' + text + '" could not be understood as a day. Ask the customer for the exact day (for example "Friday the sixteenth of October").'
        status = 'unknown'
    else:
        resolved = d.isoformat()
        if d < today:
            verdict = 'DATE CHECK: "' + text + '" = ' + fmt(d) + ', which is in the past. Ask for a day from today on.'
            status = 'past'
        elif not is_business(d):
            nb = next_business(d)
            why = 'a bank holiday' if is_holiday(d) else 'not a business day'
            verdict = 'DATE CHECK: "' + text + '" = ' + fmt(d) + '. That is ' + why + '. Do not accept it. Offer the next business day, ' + fmt(nb) + '.'
            late = [f for f in pf if nb > datetime.date.fromisoformat(f['deadline'])]
            if late:
                verdict += ' But for ' + ', '.join([f['label'] + ' (' + f['product_id'] + ')' for f in late]) + ' the latest allowed date is ' + ', '.join([fmt(datetime.date.fromisoformat(f['deadline'])) for f in late]) + ': offer that date for it instead.'
            status = 'not_business'
        else:
            ok = [f for f in pf if d <= datetime.date.fromisoformat(f['deadline'])]
            late = [f for f in pf if d > datetime.date.fromisoformat(f['deadline'])]
            verdict = 'DATE CHECK: "' + text + '" = ' + fmt(d) + ', a business day.'
            if not pf:
                verdict += ' Accept it.'
            if ok and not late:
                verdict += ' It is inside the deadline for every product. Accept it: read back product, amount and date and ask for confirmation.'
                status = 'ok'
            elif ok and late:
                verdict += ' Inside the deadline for ' + ', '.join([f['label'] + ' (' + f['product_id'] + ')' for f in ok]) + ': accept it for those. AFTER the deadline for ' + ', '.join([f['label'] + ' (' + f['product_id'] + ')' + ' whose latest date is ' + fmt(datetime.date.fromisoformat(f['deadline'])) for f in late]) + ': record that product on its own latest date and say so in the read-back.'
                status = 'partly_after_deadline'
            elif late:
                verdict += ' It is AFTER the latest allowed date. Say the latest date you can record is ' + ', '.join([fmt(datetime.date.fromisoformat(f['deadline'])) + ' for ' + f['label'] for f in late]) + ' and offer that date. If the customer refuses it, treat it as a refusal.'
                status = 'after_deadline'
            else:
                status = 'ok'
    vars['date_verdict'] = verdict
    vars['resolved_date'] = resolved
    vars['date_status'] = status
except Exception as e:
    vars['date_verdict'] = 'DATE CHECK: could not check the day. Ask the customer for the exact day and compare it with the business days and deadline in the facts.'
    vars['resolved_date'] = ''
    vars['date_status'] = 'error'
vars['customer_date_text'] = '-'
