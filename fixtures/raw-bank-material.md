# Northgate Savings Bank: material for the collections caller (not a clean specification)

Everything below is synthetic. Four documents follow: a mail from the head of collections, an extract of the
collections policy, a memo that changes part of it, and the code list the dialler uses.

---

## 1. Mail

From: Head of Collections
To: Dialler project
Subject: what the automated caller must do

Hi all,

quick summary for the caller build. We ring people who are between 1 and 60 days late. The caller must introduce
itself as the Northgate Savings virtual agent, say the call may be recorded, and ask for Mr or Ms + surname. Nothing
about the account until the security check is done, that includes the word "arrears" and the word "payment".

Security: we use the postcode of the registered address first and the year of birth second. The service wants the
postcode without spaces in capitals and the year as four digits. Two wrong answers in total and we stop, tell them to
ring the helpline on the back of their card, and log the call as not verified / failed. If they do not want to
answer, explain once that it protects their money; if they still will not, log not verified / declined. If they
ask "what is this about" instead of answering, that is the same as declining.

If a relative or anyone else picks up: say only who we are, do not say why we call, ask when the customer is
reachable. We can book a call-back for today or any of the next two working days, between nine and six, and
obviously later than the current time. One retry if the slot is bad, then give up and log not reached / no_callback.
Wrong number -> not reached / wrong_number. Customer passed away -> say "Please accept our condolences." and log not
reached / deceased. Never let a third party pay or hear a balance.

Thanks, see the policy extract for the money rules.

---

## 2. Collections policy, extract (version 7)

7.1 After verification the caller states that it calls from the arrears team, names the product (credit card
"ending <last four>", personal loan, car finance) and states the amount in arrears and the days in arrears.

7.2 Working days are Monday to Friday. Bank closure days: 2026-10-19, 2026-11-05, 2026-12-24, 2026-12-25,
2026-12-28, 2027-01-01.

7.3 Promise windows:
   days in arrears 1 to 10  -> "fresh" band  -> latest promise date is the 10th working day after the call day, one nudge.
   days in arrears 11 to 60 -> "aged" band   -> latest promise date is the 5th working day after the call day, two nudges.

7.4 A promise date is the call day or later, a working day, not later than the latest promise date. Weekend or closure
day named by the customer -> propose the following working day. Vague period -> ask once for the exact day, then
propose the latest promise date. Date after the latest promise date -> say the latest date we can take and offer it;
refusing that offer is a refusal.

7.5 "Next Monday" is the Monday of the following week; "this Monday" is the Monday of the current week.

7.6 Amounts: ask for the full arrears first. The caller never asks what the customer can afford. The smallest amount we
take is the minimum payment on a card and one instalment on a loan or car finance. If the full amount is too much,
offer the smallest amount once and say the remainder stays in arrears. Any amount between the smallest amount and the
full amount is accepted. Below the smallest amount: say we cannot take it and offer the smallest amount once.

7.7 Nudges (persuasion): nudge 1 proposes the last working day of the current week (if the call is on that day, the
last working day of the following week). Nudge 2, aged band only, proposes the smallest amount on the latest promise
date. A date or an amount from the customer is never a refusal. When the nudges are spent, stop and log no promise /
refused. Do not repeat an offer the customer turned down.

7.8 Hardship (illness, bereavement, job loss): one sentence of sympathy, no nudges, offer the care team once. Accepted ->
transfer to queue "care" and log transferred / care. Declined -> log no promise / hardship. This rule beats 7.7.

7.9 Already paid -> say it can take up to two working days to show, no promise, log paid. Not my debt / never had it /
closed years ago -> no argument, no promise, log no promise / dispute. Wants a plan or smaller instalments -> do not
describe one, transfer to queue "plans", log transferred / plans. Wants a person -> ask once if we can help, if they
insist transfer to queue "agent", log transferred / agent. "Is this a scam" -> they can call the number on their
card to check, then carry on. Anything we cannot answer from the tools: say we do not have that information.

7.10 Read-back: product, amount, date, "Is that right?". Record only on a clear yes. Say "recorded" only after the
tool confirms. If recording fails, try once more; if it fails again say we could not record it and log no promise /
service_error. After a recorded promise say: "We will send you a text message to confirm."

7.11 Never offer discounts, write-offs, plans or anything not in this policy.

7.12 Every call ends with one close_call, the last tool call, after a thank-you and goodbye.

---

## 3. Memo (overrides the policy where it differs)

Memo 2026-10-01. Two changes effective immediately:
(a) The security check now allows THREE wrong answers in total, not two.
(b) In the aged band the latest promise date is the 6th working day after the call day, not the 5th. The fresh band is
unchanged.

---

## 4. Code list used by the dialler

outcome codes: promise | paid | transferred | no_promise | not_verified | not_reached
reason codes by outcome:
  transferred: care, plans, agent
  no_promise: refused, hardship, dispute, service_error
  not_verified: failed, declined
  not_reached: callback, no_callback, wrong_number, deceased, unclear
note reasons (several products only): refused, hardship, dispute, paid, service_error
