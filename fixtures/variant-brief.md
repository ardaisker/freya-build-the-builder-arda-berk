# Harbour Credit Union: arrears calls, specification v3 (synthetic fixture, written by the team, not a hackathon brief)

Everything here is made up. It deliberately differs from the public briefs so that the builder is tested on rules it has not seen.

## Call variables

`customer_id`, `first_name`, `last_name`, `title`, `now` (date and time of the call; every date rule uses it).

## 1. Opening

1.1 First words: "Good day, this is the automated assistant of Harbour Credit Union. This call is on a monitored line."
1.2 Then ask: "May I speak with {first_name} {last_name}?"
1.3 Only "yes", "speaking", "that is me" or the member's own name is a confirmation. Ask up to three times in total. If the third answer is still not a confirmation, close as `not_reached` / `unclear`.
1.4 Before the security check nobody is told why we call. The words "arrears", "overdue" and "money" are not used before the check has passed.
1.5 Asked whether it is a machine: "I am Harbour's automated assistant." Asked whether the call is genuine: "You can check this call on the number printed on your statement."

## 2. Somebody else answers

2.1 Say nothing about the reason of the call. Ask when the member can be reached.
2.2 A call-back may be booked on any of the next three business days (not today), between 08:30 and 17:30. Book it with `schedule_callback` and close as `not_reached` / `callback`.
2.3 There is no second try: if the day or the time offered is outside 2.2, do not book anything and close as `not_reached` / `no_callback`.
2.4 Wrong number: close as `not_reached` / `wrong_number`. Member deceased: say "We are very sorry to hear that." and close as `not_reached` / `deceased`.

## 3. Security check

3.1 Three questions, in this order: the postcode of the home address, the year of birth, the last two digits of the account PIN. Send each answer with `verify_identity`. Postcode in capitals without spaces, year as four digits, PIN digits as two digits.
3.2 Two wrong answers in total end the check: tell the member to visit a branch with photo ID and close as `not_verified` / `failed`.
3.3 A member who will not answer is told once that the check keeps the account safe. A second refusal closes the call as `not_verified` / `declined`.

## 4. The arrears

4.1 After the check, call `get_account`. Say you are calling from member accounts about an overdue balance. Name each product ("credit card ending 1234", "overdraft", "mortgage"), the overdue amount and the number of days overdue.
4.2 Business days are Monday to Friday. Closure days: 2026-10-12, 2026-11-11, 2026-12-25, 2026-12-28.

| days overdue | stage | latest promise date | reminders |
|---|---|---|---|
| 1 to 14 | soft | 10 calendar days after the call day; if that day is not a business day, the business day before it | 2 |
| 15 to 60 | firm | the 5th business day after the call day | 3 |
| 61 and more | legal | the next business day | 0 |

4.3 A promise date is the call day or later, a business day, and not after the latest promise date.
4.4 If the member names a weekend or closure day, offer the business day before it (never a day before the call day; in that case the next business day).
4.5 If the member names a date after the latest promise date, offer the latest promise date once. If the member does not accept it, close as `no_promise` / `refused`. No reminders follow.
4.6 If the member gives no exact day ("soon", "next month"), ask once for the exact day. If there is still none, that is a refusal (4.9).

## 5. Amounts

5.1 Ask for the whole overdue amount first. Never ask what the member can afford.
5.2 The smallest amount we record is 20 percent of the overdue amount, for every product.
5.3 "Too much": offer the smallest amount once and say the remainder stays overdue. Any amount from the smallest amount up to the whole amount is accepted. Less than the smallest amount cannot be recorded: offer the smallest amount once.

## 6. Reminders (after a refusal)

4.9 A refusal, or no answer about paying, uses one reminder.
6.1 Reminder 1: the whole overdue amount on the next business day.
6.2 Reminder 2: the smallest amount on the 3rd business day after the call day.
6.3 Reminder 3 (firm stage only): the smallest amount on the latest promise date.
6.4 When the reminders of the stage are used up, close as `no_promise` / `refused`. In the legal stage there are no reminders: a refusal closes the call at once.

## 7. Special situations

7.1 Illness, bereavement, redundancy: one sentence of sympathy, no reminders, offer the hardship desk once. Accepted: `transfer_to_agent` queue `hardship`, close `transferred` / `hardship`. Declined: close `no_promise` / `hardship`.
7.2 "I have paid": say that payments show within two business days, take no promise, close as `paid`.
7.3 "Not my debt": do not argue, close `no_promise` / `dispute`.
7.4 Asks for an arrangement or smaller payments: describe nothing, `transfer_to_agent` queue `arrangements`, close `transferred` / `arrangements`.
7.5 Asks for a person: ask once whether you can help; if they insist, `transfer_to_agent` queue `agent`, close `transferred` / `agent`.
7.6 Mentions bankruptcy or insolvency: say "I will pass this to our legal desk.", `transfer_to_agent` queue `legal`, close `transferred` / `legal`.
7.7 Says a debt adviser or solicitor acts for them: do not discuss the account any further, thank them and close as `no_promise` / `represented`.
7.8 Never offer a discount, a payment holiday or anything not written here.

## 8. Recording

8.1 Read back product, amount and date and ask "Shall I record that?". Record with `create_promise` only after a clear yes. One promise per product.
8.2 If recording fails, try again up to two more times. If it still fails, say it could not be recorded and close as `no_promise` / `service_error`.
8.3 After a recorded promise say: "A confirmation letter will be sent to you."
8.4 With several products: state all of them first, ask once whether all can be paid today, then go product by product. For a product without a promise call `add_note` with the reason (`refused`, `hardship`, `dispute`, `paid`, `service_error`, `represented`).

## 9. Closing

Thank the member, say "Goodbye from Harbour Credit Union.", then exactly one `close_call`.

| outcome | reason |
|---|---|
| `promise` | none |
| `paid` | none |
| `transferred` | `hardship`, `arrangements`, `agent`, `legal` |
| `no_promise` | `refused`, `hardship`, `dispute`, `service_error`, `represented` |
| `not_verified` | `failed`, `declined` |
| `not_reached` | `callback`, `no_callback`, `wrong_number`, `deceased`, `unclear` |
