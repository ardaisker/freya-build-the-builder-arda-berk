From: Dana Whitfield <collections-policy@northgate.example>
To: Voice team
Subject: FW: FW: RE: call rules for the autumn campaign

Hi all, pasting Marek's rules below. Please follow them, but see my note at the very bottom, it overrides.

> Marek: we say "Northgate Savings, automated line" first, then ask for Mr/Ms {last_name}. Only a clear "yes/speaking" counts, two tries max, then
> close not_reached / unclear.
> Security: ask birth year and postcode (in this order). Two wrong answers in total end the call: not_verified / failed_check.
> Anyone who is late up to 20 days: promise date within 7 calendar days of today. 21-60 days: within 3 business days. More than 60: transfer to the
> legal queue, do not negotiate. Business days are Mon-Fri, bank holidays 2026: 2026-11-11, 2026-12-25, 2026-12-28.
> Smallest promise we take: 30 percent of overdue_amount for credit cards, 50 percent for overdrafts, 25 percent for mortgages.
> Customer says it is paid: note "paid", close paid. Customer says it is not theirs: note "dispute", close no_promise. Customer cannot pay due to
> illness or job loss: transfer to hardship queue, close transferred.
> Do not accept dates on weekends or holidays; offer the next business day.

Dana's note: the 21-60 band was changed after Marek wrote this. It is now "within 4 business days", not 3. Also mortgages: smallest promise is 20 percent, not 25.
Also: we no longer transfer the over-60 customers to legal; send them to the "arrangements" queue instead.

Code list for close_call reasons (from the old system, ignore the ones that do not exist in the API): CC01 unclear, CC02 failed_check, CC03 paid, CC04 promise made, CC05 refused.
