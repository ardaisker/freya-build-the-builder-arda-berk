# ---- finalize: pick outcome and reason from what happened (tool counters, hook logs, extracted stance). ----
def _oc(o):
    if not isinstance(o, dict):
        return '', ''
    return str(o.get('outcome') or ''), str(o.get('reason') or '')

def _case(name):
    for c in SPEC.get('special_cases') or []:
        if str(c.get('name')) == name:
            return c
    return dict()

def _count(name):
    try:
        return int(float(getv(name, '0') or 0))
    except Exception:
        return 0

def _promise_outcome():
    return str((SPEC.get('api') or dict()).get('promise_outcome') or 'promise'), ''

def _note_outcome(reason):
    r = str(reason)
    for c in SPEC.get('special_cases') or []:
        if str(c.get('note_reason') or '') == r:
            o, rr = _oc(c.get('decline_outcome') or c.get('outcome'))
            if o:
                return o, rr
    if r == 'service_error':
        return _oc((SPEC.get('confirm_record') or dict()).get('failure_outcome'))
    return _oc((SPEC.get('persuasion') or dict()).get('exhausted_outcome'))

try:
    vars['finalize_debug'] = 'hf=' + repr(vars.get('hardship_flag'))[:80] + ' pc=' + repr(vars.get('product_count'))[:20] + ' nl=' + repr(vars.get('notes_log'))[:40] + ' pf=' + repr(vars.get('paid_flag'))[:40]
    outcome = ''
    reason = ''
    queue = str(getv('transfer_queue', '') or getv('transfer_to_agent_args.' + str(_api('transfer_to_agent').get('queue') or 'queue'), '') or '')
    if _count('transfer_to_agent_success_count') > 0 and queue:
        for c in SPEC.get('special_cases') or []:
            if str(c.get('transfer_queue') or '') == queue:
                outcome, reason = _oc(c.get('accept_outcome') or c.get('outcome'))
                break
        if not outcome:
            outcome, reason = str((SPEC.get('api') or dict()).get('transfer_outcome') or 'transferred'), queue
    if not outcome:
        promises = [x for x in str(getv('promises_log', '')).split(';') if x]
        if promises or _count('create_promise_success_count') > 0:
            outcome, reason = _promise_outcome()
    if not outcome and str(getv('case_outcome', '')):
        outcome, reason = str(getv('case_outcome', '')), str(getv('case_reason', ''))
    if not outcome:
        notes = [x for x in str(getv('notes_log', '')).split(';') if x]
        try:
            single = int(float(getv('product_count', '0') or 0)) <= 1
        except Exception:
            single = False
        if notes and single and (str(getv('hardship_flag', '')) == 'hardship' or str(getv('paid_flag', '')) == 'paid' or str(getv('dispute_flag', '')) == 'dispute'):
            notes = []      # one product: the flags decide, a stray note does not
        if notes:
            reasons = [n.split(':', 1)[1] if ':' in n else n for n in notes]
            paid_case = _case('already_paid')
            if reasons and all(r == str(paid_case.get('note_reason') or 'paid') for r in reasons):
                outcome, reason = _oc(paid_case.get('outcome'))
            else:
                first = [r for r in reasons if r != str(paid_case.get('note_reason') or 'paid')]
                outcome, reason = _note_outcome(first[0] if first else reasons[0])
    if not outcome:
        stance = str(getv('stance', '') or '')
        if str(getv('paid_flag', '')) == 'paid' or stance == 'already_paid':
            outcome, reason = _oc(_case('already_paid').get('outcome'))
        elif str(getv('dispute_flag', '')) == 'dispute' or stance == 'dispute':
            outcome, reason = _oc(_case('dispute').get('outcome'))
        elif str(getv('hardship_flag', '')) == 'hardship' or stance == 'hardship':
            outcome, reason = _oc(_case('hardship').get('decline_outcome'))
        elif (_count('promise_fail_n') if _count('promise_blocked_n') > 0 else _count('create_promise_failure_count')) >= 2 and _count('create_promise_success_count') == 0:
            outcome, reason = _oc((SPEC.get('confirm_record') or dict()).get('failure_outcome'))
    if not outcome:
        outcome, reason = _oc((SPEC.get('persuasion') or dict()).get('exhausted_outcome'))
    if outcome:
        vars['call_outcome'] = outcome
        vars['call_reason'] = reason
except Exception as e:
    pass
