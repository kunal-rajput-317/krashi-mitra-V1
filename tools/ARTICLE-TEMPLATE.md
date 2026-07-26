# Writing a KrashiMitra article

Hand this file to whoever (or whatever) is writing the next article. It is the
whole spec: how to run the builder, how to pick a topic, and every rule this
site has learned the hard way.

**You write content. You never write the page.** The shell, the CSS, the three
JSON-LD blocks, the `/articles/` card and the `_redirects` rule are all derived
by `tools/article_builder.py`. An article is ~1,780 lines and only ~280 of them
are yours.

---

## How to run it

```bash
cp tools/articles/_TEMPLATE.py tools/articles/my_article.py
# …fill it in…
python tools/article_builder.py tools/articles/my_article.py
```

That one command:

1. renders `frontend/articles/<slug>.html`
2. generates the FAQPage JSON-LD **from the visible FAQ markup**
3. inserts (or refreshes) the card in `frontend/articles/index.html`
4. rebuilds the article 301 block in `frontend/_redirects`
5. validates the page and fails loudly instead of shipping something broken

Other modes:

```bash
python tools/article_builder.py --all      # re-emit every article
python tools/article_builder.py --check tools/articles/my_article.py   # validate only
```

`sitemap.xml`, `llms.txt` and `/articles/meta` enumerate the articles directory
at request time, so they pick the page up with no extra step.

The page shell and CSS are read from a real live article (`SHELL_SOURCE` in the
builder). Change the site design there, run `--all`, and every article follows.

---

## Picking the topic

Rank candidates on all four. A topic that only scores on one is not worth
2,500 words.

1. **Seasonal urgency.** What is a farmer searching *this month*? A pest article
   published at the start of its outbreak window earns for the whole season;
   the same article in February earns nothing.
2. **Site gap.** Check `frontend/articles/` first. Do not write a second article
   about something already covered — it cannibalises the page that already
   ranks. Prefer a crop or scheme with **zero** coverage.
3. **Cluster value.** A new crop opens internal links to `/bhav/<crop>` and to
   sibling articles. A one-off with nothing to link to is worth less.
4. **Evergreen vs seasonal.** Ship a mix. Government schemes (KCC, PMFBY,
   subsidies) keep earning year-round; pest and disease pages spike and fade.

Worked examples in `tools/articles/`:

| Module | Why it was chosen |
|---|---|
| `makka_fall_armyworm.py` | peak kharif season, `makka-guide-up` existed but had no pest page |
| `kapas_gulabi_sundi.py` | season starting, and the site had **zero** cotton content |
| `kisan_credit_card.py` | evergreen high volume, and only one scheme article existed |

---

## The title is the job

The site sits around position 6–7 with roughly 1% CTR. Visibility is not the
problem — the snippet losing the click is. So:

- **Put the searcher's literal question in the title.** Not "यूरिया गाइड" but
  "यूरिया का असर कितने दिन रहता है?".
- **Put the numeric answer in the description.** `30–45 दिन`, `4% ब्याज`,
  `0.4 मि.ली./लीटर`. A number in the description is the single biggest CTR
  lever available.
- Include the year when the answer changes year to year.
- Title 30–160 chars, description 70–350. The builder enforces both.
- `keywords` should carry three spellings of the same idea: Devanagari,
  romanised Hindi (`makka me sundi ki dawa`), and English (`fall armyworm`).
  Farmers type all three.

---

## Voice and structure

Written for a farmer on a phone, in simple Hindi. Short sentences. No English
paragraph with a Hindi sentence pasted on top.

**Section rhythm** (drop what doesn't apply, keep the order):

```
भूमिका → यह क्या है → पहचान → जीवन चक्र / यह कैसे काम करता है →
नुकसान (तुलना तालिका) → निगरानी / पात्रता → बिना पैसे की रोकथाम →
जैविक-देसी उपाय → रासायनिक / प्रक्रिया (डोज़ या दस्तावेज़ तालिका) →
ये गलतियाँ न करें → कैलेंडर तालिका → निष्कर्ष → FAQ
```

Rules that make the difference:

- **Free before paid.** Cultural and desi measures come *before* the chemical
  section, always. Sand-and-lime in the whorl before ₹800 of insecticide.
- **Every list item leads with a bold label.** `<li><strong>गहरी जुताई:</strong> …`
- **Two tables minimum** — one comparison (`स्वस्थ` vs `ग्रस्त`, using
  `td.healthy` / `td.diseased`) and one calendar or dose table. Tables are what
  get pulled into AI answers and featured snippets.
- **A "ये गलतियाँ न करें" section.** It is consistently the most useful part.
- 2,000+ words of visible text. The builder rejects anything under 1,200.
- Only use CSS classes that already exist (`tip-box info|tip|warning`,
  `article-table`, `article-section`, `section-heading`, `quick-facts`). Do not
  invent classes — there is no per-article stylesheet.

---

## FAQ

6–8 pairs, written as one Python list. The visible markup and the JSON-LD are
both generated from it, so they cannot drift.

- Phrase the question **exactly as a farmer types it**.
- **First sentence of the answer must contain the answer**, with the number.
  That sentence is what a snippet or an AI overview will quote.
- Inline `<strong>` only. No block tags inside an answer.

This matters more than it looks: hand-written FAQ schema had already drifted
from the visible page on eleven articles (one declared 3 FAQs while showing 8,
another had FAQ schema and no FAQ section at all). Google suppresses rich
results for mismatched FAQPage markup and can issue a manual action for it.

---

## Accuracy and honesty

- **Every dose, rate, price and deadline must be sourced.** Search first, write
  second. Prefer ICAR / KVK / PIB / RBI over content farms.
- **Any section with doses, money or deadlines gets a `tip-box warning`** telling
  the reader to confirm with their KVK, कृषि विभाग or bank branch, because
  state-level advice differs.
- **Do not flatten a nuance to make a headline cleaner.** KCC is not a flat 4%
  on the full ₹5 lakh — the ₹3–5 lakh slab works differently, and the article
  says so.
- Scheme articles get a closing disclaimer: rules change, KrashiMitra is not an
  agent and does not arrange loans.
- Never inflate the site's own numbers.

---

## Things that silently break here

Read these twice. Each one shipped broken at least once.

- **A missing static file returns 200 + HTML, never a 404.** Broken image paths
  fail silently in production. The builder asserts every `../` asset and the
  `og:image` exist on disk — do not point at an image you have not committed.
- **The slug must be lowercase.** `sitemap.py` serves every article at
  `f.stem.lower()`; a mixed-case filename makes the canonical and the sitemap
  disagree about which URL is real.
- **`_redirects` placeholders match whole path segments only.** Never
  "simplify" the per-article rules into `/articles/:slug.html` — it emits a
  literal `:slug` in production and loops.
- **An unclosed `<div>` inside the desktop-only `.top-utility-bar` blanks the
  whole page on mobile** while desktop still looks fine. The builder checks tag
  balance; also eyeball the page at 390px.
- **`/bhav/paddy` is a 404 but `/bhav/paddy-common` is not.** Verify every bhav
  slug before using it:
  `curl -o /dev/null -w "%{http_code}" https://krashimitra.in/bhav/<slug>`
- **Ads are placed by `frontend/ads.js`**, which is loaded by `drawer-menu.js`
  on every page. Drop `km-ad-slot` markers where you want units; never paste
  raw AdSense `<ins>` tags into an article.

---

## Still manual after the builder runs

The builder wires the page into `/articles/`. It does **not** give the article
inbound links from pages that already rank, and those matter — a page with only
one internal link took months to index here. After building, consider adding:

- a card on `frontend/index.html` (the homepage set is curated by hand)
- a contextual link from the closest sibling article
  (e.g. `makka-guide-up.html` → the maize pest article)
- a per-crop link from the `/bhav` pages (`backend/routes/bhav.py` currently
  links only to `/articles/`, the hub)

Also still manual: a real per-article hero image. Without one the card falls
back to an emoji and the SERP thumbnail is the generic banner. `_hero_image()`
in `backend/routes/articles.py` deliberately ignores `og-banner.jpg`, so
committing a real image under `frontend/images/` and pointing `og_image` at it
is all it takes.

---

## Ship checklist

- [ ] `python tools/article_builder.py tools/articles/<name>.py` → all checks pass
- [ ] Every dose / rate / date traced to a real source
- [ ] Caveat box present wherever the article gives doses, money or deadlines
- [ ] `cat_query` is a real filter chip: `khad keet mausam ganna sabji fruit anaaj jankari karnataka`
- [ ] Every `bhav_links` slug returns 200
- [ ] Page eyeballed at 390px
- [ ] Inbound links added from at least one page that already ranks
- [ ] Pushed to **`main`** — Netlify and Render deploy from `main`, not `null99`.
      `git push origin null99 && git push origin null99:main`
