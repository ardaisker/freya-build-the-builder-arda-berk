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
    # parallel tool calls can overwrite each other's log line, so each product also has its own marker
    pending = []
    for f in pf:
        pid = str(f.get('product_id'))
        key = ''.join([ch if ch.isalnum() else '_' for ch in pid])
        if pid in promised or pid in noted or str(getv('promised_' + key, '')) or str(getv('noted_' + key, '')) or str(getv('tried_' + key, '')):
            continue
        pending.append(pid)
    if len(pf) > 1 and pending and transfers == 0 and rounds < len(pf) and BN_DEFAULT:
        now_o = str(getv('call_outcome', ''))
        now_r = str(getv('call_reason', ''))
        reason = BN_DEFAULT
        for row in BN_MAP:
            if row[0] == now_o and row[1] == now_r:
                reason = row[2]
                break
        # the customer raised exactly one special claim and the one leftover product has no note: that claim is its reason
        flagged = [row[2] for row in BN_FLAGS if str(getv(row[0], '')) == row[1]]
        if len(flagged) == 1 and len(pending) == 1 and rounds == 0 and (':' + flagged[0] + ';') not in str(getv('notes_log', '')):
            reason = flagged[0]
        vars['bn_product'] = pending[0]
        vars['bn_reason'] = reason
        vars['notes_log'] = str(getv('notes_log', '')) + pending[0] + ':' + reason + ';'
        vars['noted_' + ''.join([ch if ch.isalnum() else '_' for ch in pending[0]])] = '1'
        vars['bn_rounds'] = str(rounds + 1)
        vars['bn_go'] = '1'
except Exception as e:
    vars['bn_go'] = '0'
