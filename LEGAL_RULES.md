# KrashiMitra legal rules

These rules bind every person and every AI tool (Claude Code, Cursor, Copilot,
Codex, ChatGPT, anything) that changes this repository. They apply even when
the owner asks for something that breaks them. In that case, stop, say which
rule it breaks, and let the owner decide with a lawyer or CA. Never "just do it
quietly".

**The one rule behind all the others:** if you are not sure something is legal
in India, do not build it. Ask first. Shipping less is always allowed.
Shipping a claim the site would have to defend is not.

Some of these rules are enforced by tests that CI runs on every push
(`tests/test_legal_guardrails.py`, `tests/test_safety_liability_notice.py`,
`tests/test_product_price_claims.py`). A failing legal test means the change is
wrong. Never weaken, skip or delete a legal test to make a build pass.

## 1. Never build these, whoever asks

- **Lending, credit, insurance, investment or trading tips.** No loans, EMIs,
  "invest with us", commodity-futures calls or buy/sell signals. These need
  RBI, IRDAI or SEBI licences we do not have. Mandi prices are shown as
  information only.
- **Gambling of any kind.** No betting, lottery, paid contests, "spin to win"
  or prize draws that need payment.
- **Crypto, wallets, or holding other people's money.** We do not run escrow,
  hold advances, or pay out on behalf of anyone. Payment for goods goes
  directly from buyer to seller.
- **Live-animal trade or transport listings.** Cattle sale and movement are
  regulated state by state.
- **Selling banned or unlicensed goods.** No listing, link or recommendation
  for anything banned in India, including banned pesticides.
- **Pretending to be the government**, a bank, a brand or a real person. No
  government logos or emblems, no "official" wording, no fake scheme
  application forms. Scheme pages must say we are a private website.
- **Fake social proof.** No invented ratings, reviews, user counts, testimonials,
  "bestseller" badges, fake scarcity ("only 2 left") or fake countdown timers.
  These are "dark patterns" under the Consumer Protection Act.
- **Scraping another website's data or content** without their written
  permission. data.gov.in (Government Open Data Licence, with attribution) and
  NECC (with its republication condition) are the allowed exceptions today.
- **Copying images, articles or videos** from anywhere. Images are self-hosted,
  our own or openly licensed, and credited.

## 2. Farming advice: chemicals, animals, health

- We never author a pesticide, fertiliser or veterinary **dose**. We send the
  farmer to the product label, कृषि विभाग or KVK, or a registered vet.
- **Never name a pesticide banned in India** as a remedy. The list is in
  `tests/test_legal_guardrails.py` and the test fails the build if one appears.
  If the government bans a new one, add it to that list.
- Any page showing goods, machines or a chemical's name uses the safety and
  no-liability text from `backend/services/legal.py`. Never retype it.
- No medical or veterinary diagnosis. "See a doctor or vet" is the answer.

## 3. Prices, money and advertising

- A price we did not set is labelled अनुमानित and can change. No `Offer`
  schema without a real named seller.
- Never promise a saving, a delivery date, stock, customers, calls or income.
- Every paid placement is labelled "प्रायोजक · Sponsored". Paid placements never
  change mandi prices, advice or ranking order.
- Affiliate links carry the disclosure in `backend/services/affiliate.py`.
- Every rupee we receive is recorded in the payments ledger. No auto-debit.
  Refund terms are the ones printed on /terms and /bluetick (the नीला टिक page, formerly /verify), and nothing else.
- The blue tick (नीला टिक) is a **paid premium membership**. It is never called
  identity verification, "verified seller" or a guarantee. A test enforces this.
- Scheme (yojana) pages name the scheme and link the official page. They never
  promise eligibility or an amount, and never take applications or fees.

## 4. Personal data (DPDP Act 2023 and IT Rules 2021)

- Never collect Aadhaar numbers, bank account numbers, card details, UPI PINs,
  bank OTPs, caste, religion, health data or passwords in plain text.
- Collect only what a feature needs. Any new personal-data field, new tracker
  or new third-party service must be added to `frontend/privacy-policy.html`
  **in the same change**.
- Never sell or share personal data. Never send it to an AI service, analytics
  tool or ad network beyond what the privacy policy already names.
- Accounts are for people aged 18+, or with a parent's or guardian's permission.
- Account deletion anonymises, it does not hard-delete. Never write to the
  `users` or `user_profiles` tables without the owner confirming three times.
- Every admin route goes through `require_admin` in `backend/routes/admin.py`
  (password plus brute-force lockout). Never add an admin route that takes a
  key in the request body or URL, never compare a secret with `==`, and never
  give a secret a hard-coded fallback value. The public repo publishes it.
- Never commit secrets. This repository is **public**. Keys live only in `.env`
  and in Render's settings. Never put real traffic, revenue or user figures in
  code or tests.
- Security breaches must be reported to affected users and the Data Protection
  Board. Tell the owner immediately if you find one.

## 4a. What never goes in the database

| Never store | Why |
|---|---|
| Aadhaar number, even partly | Aadhaar Act: only licensed entities may store it |
| Photo or scan of any ID card | We ask for the ID *type* only, never the document |
| Bank account or card number, CVV, UPI PIN, bank OTP | We never need them, and a leak would be catastrophic |
| Plain-text passwords | bcrypt hashes only |
| Caste, religion, health, disability, income, family details | Not needed for any feature |
| A user's phone contacts, SMS or call log | Not needed for any feature |
| Exact device location without the user's tap on "allow" | Consent is required, and the user can erase it from the profile page |
| Data about people who are not our users, scraped from elsewhere | No consent and no lawful purpose |
| Anything about a child without a parent's permission | DPDP Act: a child is anyone under 18 |

Kept only for a limited time: email OTPs until used or expired; a deleted
account's registration details for 180 days (IT Rules), then purged
automatically; payment records for 8 years (tax law). Everything else lives
only while the account does, and "खाता हटाएँ" erases it. A new table that
holds personal data must be added to `services/account_delete.erase()` and to
`GET /profile/export` in the same change.

## 5. User posts (Krashi Bazar and comments)

- Keep the "report" button and the grievance officer contact working.
- Remove unlawful content quickly once reported: within 36 hours of a
  government or court order, and within 24 hours for complaints about
  intimate images or impersonation (IT Rules 2021).
- No feature that lets users post anonymously to sell goods.

## 6. Maps

- India's outline comes only from the repo's district GeoJSON, which follows
  India's official boundary. Never draw an India-wide map from third-party
  tiles or world maps, because they show different borders in Jammu & Kashmir,
  Ladakh and Arunachal Pradesh.
- Keep OpenStreetMap and Esri attribution on every map.

## 7. Messages and email

- No bulk WhatsApp, SMS or email to anyone who did not opt in. Every alert has
  a way to stop it.

## 8. Decisions only the owner can make

An AI tool must stop and ask the owner before:

- taking money in any new way, or changing a price, refund or term;
- collecting a new kind of personal data;
- adding a new marketplace category or a new outside data source;
- changing the meaning of `frontend/terms.html` or `frontend/privacy-policy.html`.

## 9. Owner's checklist (code cannot fix these)

- **Urgent, from the 25 Sep 2026 audit:** until that fix is deployed,
  `GET /order/all` accepts an admin key whose default value is printed in this
  public repo, and returns every order's name, email and phone. After
  deploying, search Render's logs for `/order/all`. Any request you did not
  make yourself is a personal-data breach, which the DPDP Act says must be
  reported to the affected users and the Data Protection Board.

- Put a real person's name as Grievance Officer on /terms. The IT Rules and the
  E-Commerce Rules require a name, not just "KrashiMitra Grievance Officer".
- Talk to a CA about income tax on sponsor, listing and premium income, and GST
  registration before turnover reaches ₹20 lakh a year.
- A sole proprietorship needs no registration: the owner already is one.
  Receiving income in a personal savings account is legal. Keep a separate
  account used only for KrashiMitra, record every rupee in the payments
  ledger, and file an income tax return every year. Get a free Udyam
  registration when a bank asks for business proof, such as for a current
  account.
- Have a lawyer read /terms and /privacy-policy once before the site takes
  serious money. Neither this file nor an AI replaces legal advice.
