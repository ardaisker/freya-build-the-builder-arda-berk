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
    for row in (SPEC.get('closing') or dict()).get('outcome_table') or []:
        if str(row.get('outcome')) == 'promise':
            return 'promise', ''
    return 'promise', ''

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
    outcome = ''
    reason = ''
    queue = str(getv('transfer_queue', '') or getv('transfer_to_agent_args.queue', '') or '')
    if _count('transfer_to_agent_success_count') > 0 and queue:
        for c in SPEC.get('special_cases') or []:
            if str(c.get('transfer_queue') or '') == queue:
                outcome, reason = _oc(c.get('accept_outcome') or c.get('outcome'))
                break
        if not outcome:
            outcome, reason = 'transferred', queue
    if not outcome:
        promises = [x for x in str(getv('promises_log', '')).split(';') if x]
        if promises or _count('create_promise_success_count') > 0:
            outcome, reason = _promise_outcome()
    if not outcome:
        notes = [x for x in str(getv('notes_log', '')).split(';') if x]
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
        elif _count('create_promise_failure_count') >= 2 and _count('create_promise_success_count') == 0:
            outcome, reason = _oc((SPEC.get('confirm_record') or dict()).get('failure_outcome'))
    if not outcome:
        outcome, reason = _oc((SPEC.get('persuasion') or dict()).get('exhausted_outcome'))
    if not outcome:
        outcome, reason = 'no_promise', 'refused'
    vars['outcome'] = outcome
    vars['reason'] = reason
except Exception as e:
    vars['outcome'] = 'no_promise'
    vars['reason'] = 'refused'
