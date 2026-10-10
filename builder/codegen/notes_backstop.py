# ---- notes_backstop: several products, the call is ending. A product with neither a promise nor a note gets its note here. ----
vars['bn_go'] = '0'
try:
    rounds = int(float(getv('bn_rounds', '0') or 0))
    pf = json.loads(str(getv('pf_json', '[]') or '[]'))
    promised = [x for x in str(getv('promises_log', '')).split(';') if x]
    noted = [x.split(':', 1)[0] for x in str(getv('notes_log', '')).split(';') if x]
    try:
        transfers = int(float(getv('transfer_to_agent_success_count', '0') or 0))
    except Exception:
        transfers = 0
    try:
        saved = int(float(getv('create_promise_success_count', '0') or 0))
    except Exception:
        saved = 0
    pending = [str(f.get('product_id')) for f in pf if str(f.get('product_id')) not in promised and str(f.get('product_id')) not in noted]
    if len(pf) > 1 and pending and transfers == 0 and saved <= len(promised) and rounds < len(pf) and BN_DEFAULT:
        now_o = str(getv('call_outcome', ''))
        now_r = str(getv('call_reason', ''))
        reason = BN_DEFAULT
        for row in BN_MAP:
            if row[0] == now_o and row[1] == now_r:
                reason = row[2]
                break
        vars['bn_product'] = pending[0]
        vars['bn_reason'] = reason
        vars['notes_log'] = str(getv('notes_log', '')) + pending[0] + ':' + reason + ';'
        vars['bn_rounds'] = str(rounds + 1)
        vars['bn_go'] = '1'
except Exception as e:
    vars['bn_go'] = '0'
