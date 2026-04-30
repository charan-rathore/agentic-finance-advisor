# PROJECT_TODO_MASTER.md
# Paisa Pal / Niveshak AI — Strategic Master Plan
**Audit date:** 2026-04-30 (second-pass, deep strategic review)
**Repo state:** `main` @ 4c0ff63 — 1,160-line `wiki_india.py`, 655-line `ui/app.py`, 159 tests passing
**Author profile:** Solo builder, free-tier-only, local-first, India-first product thesis

> This document supersedes `PROJECT_TODO.md` (archived).
> It is the single source of truth for what to build, what to cut, and how to demo.

---

## 0. Executive Summary

You have built a **technically credible AI agent system** with sound architecture (3 agents, queues, SQLite, LLM Wiki pattern, Trust Layer scaffolding) and a working Streamlit dashboard. The infrastructure quality is genuinely above the bar for a solo MVP.

**But the product is not yet demo-ready.** Three load-bearing claims silently fail:

1. **The India knowledge base is empty** — `equities/`, `mutual_funds/`, `macro/` contain only `.gitkeep`. The "ask about Reliance / HDFC Flexi Cap / repo rate" pitch collapses on the first real question.
2. **The Trust Layer never fires** — `record_wiki_version()` is defined but not called from `wiki_india.py`. The "Sources & History" tab is built but always empty.
3. **The free-tier cost story is fragile** — current ingest cadence makes 100–600 Gemini calls/day; you'll hit Gemini Flash rate limits before you have one user.

**Six upgrades, in order, take the demo from 3/10 to 8/10:**

1. **Pre-seed both wikis** — 25 India pages + 8 US pages (~1 day). India is the demo's primary surface; US stays visible as proof the engine is market-agnostic.
2. **Add a Reflection critic pass** to every Gemini answer (2 hours). Single biggest hallucination-reduction lever; +1 Gemini call per query, paid back in trust.
3. **Replace `text_area` + button with `st.chat_input` + streaming Gemini** (3 hours).
4. **Deterministic SIP / Goal / ELSS calculator** in pure Python — zero hallucination risk, instant (3 hours).
5. **Wire the Trust Layer end-to-end** for both India and US writes (2 hours).
6. **Add a ReAct loop for multi-step queries** ("ELSS vs PPF for me?") behind an intent classifier (4 hours).

**Architectural stance fixed in this revision:**

- **Gemini-only, single provider.** No Groq, no multi-LLM abstraction. Hindi/Hinglish quality and a single mental model for the demo trump vendor diversification at this stage.
- **Quality over call-count on the reasoning hot path.** Each user query may make **3–6 Gemini calls** (intent classify → retrieval-grounded synthesis → reflection critic → optional ReAct iterations → optional regeneration on critique). We *want* this — fewer calls = more hallucination.
- **Cost is controlled by aggressive caching of the common case**, not by trimming calls on the actual reasoning. FAQ cache covers ~80% of beginner traffic at zero LLM cost, demo cache covers the rehearsed 4 questions, 60s page cache eliminates redundant disk reads, embedding-based routing replaces the routing LLM call. The remaining 20% gets the full 3–6 call quality pipeline.
- **India and US both stay visible.** India is the demo lead (4 minutes); US is the 30-second "and the same engine works on US tickers" proof. The US codepath is a pitch asset, not technical debt.

Everything else in this document is supporting work for those six.

---

## 1. Brutal Truth Section

### What is genuinely impressive
- **The agent architecture is real.** Three-agent split (ingest / analysis / storage), asyncio queues, retry decorators, source registry, SQLAlchemy ORM with proper migrations-readiness — this is staff-engineer-grade for a solo project.
- **The LLM-Wiki pattern over markdown** (no vector DB, no LangChain) is the right call. It's interpretable, debuggable, version-controllable, and free. This will hold up in a senior technical interview.
- **The horizon-aware India advisor** (`short_term_india_answer`, `intermediate_india_answer`, `long_term_india_answer` in `wiki_india.py`) is genuine product thinking. Most Gen-AI investing demos don't have this.
- **The confidence rubric is honest.** Hardcoded penalties on YAML metadata is not magic but it's defensible — every signal is observable, the rubric is shown to the user, and there's a 0.30 floor. This is more trustworthy than a learned score nobody can audit.

### What is fake complexity (refactor, don't delete)
- **`wiki_ingest.py` has 8 near-identical `process_*` functions** (SEC, FRED, Reddit, Alpha Vantage, Finnhub, earnings, sentiment, company facts) each making per-file Gemini calls with 80% duplicated boilerplate. **The complaint is duplication, not that the work is unnecessary** — these processors feed the US wiki, which is a pitch asset. Refactor into one parameterised function `process_raw_file(file, processor_spec)` driven by a small registry. Same behaviour, ~250 fewer lines.
- **`lint_wiki()` does two jobs and we should split them.**
  - **Keep deterministic staleness detection** (Python only): page `last_updated` > TTL → set `stale: true`. This is load-bearing for the confidence score (`-0.15` per stale page) and must run every cycle. Move it out of the Gemini-powered lint path into a 10-line module-level function called from analysis loop.
  - **Keep Gemini contradiction detection but earn it:** today the output writes to `lint_*.md` and is never surfaced. Either (a) render contradiction findings as a "⚠️ This page conflicts with `<page>`" badge in the UI and the "Sources & History" tab, or (b) replace with a deterministic field-level diff (regex-extract numeric claims like `repo rate \d+\.\d+%`, compare across pages with the same `subject` frontmatter). Both are valid; (b) is cheaper, (a) is more impressive in a demo.
- **The "Auto / Beginner / Expert" experience radio** in the sidebar duplicates `detect_beginner_intent_india()`. Pick one — keep the auto-detector, drop the radio.
- **`core/wiki.py` and `core/wiki_india.py` are near-duplicates** (1,090 + 1,161 = 2,250 lines for what is one logical module with two parameter sets). For the demo, leave them; long-term, refactor to one parameterised module.

### What I previously got wrong (corrected here)
- **"Combine routing + synthesis into one Gemini call" — withdrawn.** The 2-call structure is load-bearing: the system loads page contents from disk *between* the routing and synthesis calls. A single combined call would force the model to write the answer without ever seeing the page bodies, exactly the hallucination mode we are trying to prevent. The correct optimisation is **embedding-based routing** (replace the LLM routing call with sentence-transformers similarity over the index — deterministic, free after the 23MB model download, runs on CPU in <50ms). Synthesis stays a separate, page-content-grounded LLM call. See §15.5 (rewritten).
- **"Hide US tabs / move `wiki_ingest` processors behind a feature flag" — withdrawn.** The US codepath is the architectural-portability proof. India leads the demo; US stays visible. See §1.3 (revised) and §6 (revised).

### What is weak
- **Cold start: 5–10 minutes to first answer**, and the answer is shallow because the wiki is empty. A first-time visitor will leave.
- **Streamlit blocks for 10s during Gemini calls.** The "Consulting the India wiki…" spinner is exactly what users perceive as broken.
- **The Hindi toggle silently drops** for the most common (beginner) path — `ui/app.py:393` calls `beginner_answer_india(india_q.strip())` with no `hindi=` and no profile. Both bugs invisible in tests.
- **Hardcoded EDT (–4h)** in `ingest_agent.py:131` and `storage_agent.py:158` will be wrong Nov–Mar. A reviewer will flag in 30 seconds.
- **Empty `KnowledgeVersion` table.** "Audit trail" with zero rows is a negative signal, not a neutral one.
- **README claims 184 tests; `grep` says 159.** Small precision issue but it matters when pitching.

### What actually matters for the demo
- A new user reaching "I started a SIP and understand why" in **under 5 minutes**.
- The chat feeling **fast** (streaming) and **trustworthy** (sources cited inline, not buried).
- A **deterministic SIP calculator** that never hallucinates.
- A **Hinglish** answer that reads like a savvy friend, not a bank brochure.
- The pre-rehearsed demo not breaking when Gemini rate-limits at the worst moment.

---

## 2. Current State Diagnosis

| Dimension | State | Demo impact |
|---|---|---|
| Backend pipeline (3 agents) | ✅ Solid | Foundation for the pitch |
| US data ingest | ✅ Works | **Pitch asset** — proves the engine is market-agnostic. Keep visible. |
| Hallucination guardrails | ❌ None — single synthesis call, no critic | Reflection layer needed for trust |
| Multi-step / comparative reasoning | ⚠️ Single-shot synthesis — fine for "what is SIP", weak for "ELSS vs PPF for me" | ReAct loop closes this gap |
| **India wiki content** | ❌ **Empty (`.gitkeep` only)** | **Catastrophic — pitch fails on first question** |
| **Trust Layer wired** | ❌ **Never called from `wiki_india.py`** | **Empty audit tab = anti-trust signal** |
| **SIP / ELSS calculator** | ❌ **Missing** | The #1 thing Indians Google for finance |
| **Chat UI / streaming** | ❌ **`text_area` + button** | Feels like a 2015 dashboard |
| Hindi support | ⚠️ Half-wired (broken on beginner path) | Top differentiator partially broken |
| Onboarding | ⚠️ Buried inside India tab; jarring rerun | High-friction first impression |
| Confidence scoring | ✅ Implemented, deterministic | Good story, but UX exposes raw float |
| Test suite | ✅ 159 tests, all green, mostly mocked | Strong; minor precision claim issue |
| Linting / mypy | ✅ Passes | Pro signal |
| Cost / free tier | ⚠️ 100–600 Gemini calls/day | Fragile under any real usage |
| Cold-start time | ❌ 5–10 min to first answer | Demo-killer without seed script |
| Mobile UX | ❌ Untested | 100M Indians use phones |
| Distribution path | ❌ Streamlit only | Must acknowledge in pitch deck |

---

## 3. Product Thesis

### One-line pitch

> **Paisa Pal — an AI investing companion for first-time Indian savers, in your language, that shows you the receipts.**

### Three name options

1. **Paisa Pal** — Hinglish, warm, instantly intelligible. Strongest for consumer pitch & Bharat use case.
2. **Niveshak AI** — "investor" in Hindi. Credible, premium-coded, India-only by design. Strong for VC deck.
3. **Mintra** — *min* (small) + *mitra* (friend). Brand-able like Zerodha; works globally if you ever extend.

**Recommendation:** lead with **Paisa Pal** in product copy and **Niveshak AI** in the VC deck title slide.

### Who exactly it is for

The "next 100M": salaried Indians 22–35, post-tax income ₹25k–₹1.5L/month, who have:
- A savings account or FD habit but no SIP started yet,
- A real goal (down payment, marriage, child's education, tax-saving) within 1–7 years,
- Comfort in **Hinglish or regional-flavoured English**,
- Phone-first usage,
- Distrust of WhatsApp tipsters and YouTube finfluencers.

This excludes both the F&O day-trader (Zerodha owns them) and the HNI (wealth managers own them).

### Why now

- **UPI made Indians comfortable with finance apps.** 350M+ active UPI users; the on-ramp is solved.
- **SEBI 2024 rule changes** (LTCG on equity 12.5% > ₹1.25L, finfluencer crackdown) made unbiased explanation a regulatory tailwind.
- **Gemini Flash & Llama free tiers** make a quality multilingual advisor economically viable for the first time.
- **AMFI, RBI, SEBI all publish free APIs** — the data backbone is open.
- **Hindi/regional LLM quality crossed the threshold in 2024–25** for confident retail use.

### Why AI-native (not a wrapper)

- Personalised explanations (income, age, risk, goal) at zero marginal cost.
- Multilingual at zero marginal cost.
- Behavioural nudges that adapt to each user's question history.
- Automated grounding in regulator data (RBI repo, AMFI NAVs, SEBI definitions).
- Confidence scoring on every answer — *no static UI can do this.*

### Why India first, globally extensible

- 100M+ first-time-investor TAM in India alone (CRISIL/AMFI estimates).
- The same engine (LLM Wiki + horizon-aware advisor + Trust Layer) works for any market by swapping the data fetchers and seed pages — already proven by the parallel US codepath.
- Pitching India-first signals user empathy and Bharat focus; mentioning global extensibility neutralises the "small market" VC objection.

### Why incumbents are weak here

| Incumbent | Strength | Weakness Paisa Pal exploits |
|---|---|---|
| **Zerodha (Varsity / Coin)** | Rails, pricing, brand | Education is static articles; no personalisation, no chat |
| **Groww** | Onboarding to buy | Recommendations are list-based, no "why for *you*", no Hinglish |
| **ET Money** | Clean MF UX | Generic "best fund" ranks; opaque "advisor" upsell |
| **INDmoney / Jar / Niyo** | Specific niches (US stocks / micro-savings) | None do explanation in Hinglish + grounding + behavioural |
| **Cred** | Affluent UX | Doesn't serve the "next 100M"; non-investor-first |
| **WhatsApp finfluencers** | Trust + Hindi | No grounding, often illegal post-2024, lose money |
| **ChatGPT / Gemini direct** | Capability | No India data freshness, no AMFI/RBI grounding, no confidence signal, no profile memory |

**The single defensible wedge: explanation + grounding + Hinglish + personalisation, all four together.** No incumbent does all four.

### Right-to-win

1. **Free-tier-honest architecture.** Most "AI advisor" startups burn money on per-query LLM cost; you can show unit economics that work at $0/user/month at small scale.
2. **Verifiable grounding.** Every answer cites SEBI / AMFI / RBI source files — defensible against the post-2024 finfluencer crackdown.
3. **Multilingual and personalised at zero marginal cost** — incumbents would need to rebuild content per language.
4. **Compounding wiki.** Each user's question becomes a versioned insight page — the system literally gets better with use.

### Core moat over time

- **Data moat:** A growing, version-controlled wiki of India-specific Q&A becomes a proprietary corpus.
- **Trust moat:** Public confidence score + audit log creates a regulatory-friendly product distinct from black-box advisors.
- **Distribution moat (later):** When Telegram / WhatsApp bot launches, the channel becomes the moat (network effects via shareable answers).
- **Linguistic moat:** Each new Indian language (Marathi, Tamil, Bengali) is a few hundred dollars of LLM tokens; for an incumbent it's a content team.

### TAM / Adoption / Monetisation / Risk

| Question | Answer |
|---|---|
| **TAM realism** | ~100–150M salaried Indians without active SIPs (AMFI: ~9 cr unique MF investors as of FY25, demographic ceiling much higher). Conservative beachhead: 1M users in 24 months. |
| **Will they adopt? Why?** | Yes if it shows up where they already are (Telegram / WhatsApp / SEO landing pages) and answers their first question better than Google. Trigger: *"SIP calculator"*, *"ELSS vs PPF"*, *"emergency fund kya hai"* searches. |
| **Will they adopt? Why not?** | Distrust of any non-bank financial brand. Mitigation: regulator citations on every answer, no transactions (you're an explanation layer, not a broker), shareable receipts. |
| **Monetisation v1 (year 1)** | Pure free product. Goal: usage, retention, language coverage. No monetisation pressure. |
| **Monetisation v2 (year 2)** | (a) Affiliate from Coin / Groww / Kuvera when user is *ready* and asks ("where do I open my Demat?"). Disclosed upfront. (b) **Premium "deep portfolio review"** — user pastes their MF holdings, gets a multi-page AI-grounded review, ₹99/year. Defensible because it's not advisory, it's analysis. |
| **Monetisation v3 (year 3)** | B2B2C: white-label the engine to small co-operative banks / payroll providers serving Tier-2/3. ₹3–10/MAU. Strong margin if engine is mature. |
| **12-month failure risks** | (1) Gemini free tier policy change; (2) SEBI ruling that even education needs registration; (3) Hindi/Hinglish quality regression at the model level; (4) Zerodha or Groww launches a copycat AI advisor with their distribution; (5) Solo-builder bandwidth — burnout; (6) Hallucination-driven user harm (wrong fund cited, wrong tax rate). |
| **Mitigation** | (1) Aggressive caching reduces Gemini volume by ~20× (FAQ + demo cache + page cache + embedding routing); free-tier survives 10K daily queries at that ratio. Stay Gemini-only for the demo — Hinglish quality matters more than vendor diversification. (2) Strict "educational, not advisory" framing + SEBI disclaimer on every answer. (3) Pre-cache top 100 answers as plain markdown — the FAQ system serves these without an LLM call at all. (4) Move first; ship distribution (Telegram bot) before incumbents notice. (5) Aggressive scope cuts in this document. (6) **Reflection critic on every Gemini answer + ReAct on multi-step queries** (this revision) — the single highest-leverage hallucination control we can ship. |

---

## 4. Demo Narrative (5 minutes)

**Persona — Priya, 26, software QA in Bengaluru.** Take-home ₹52k/month. ₹3L parked in savings. Watched a relative lose money in F&O — fears markets. Knows "SIP" but doesn't know what it means. Comfortable in Hinglish.

| Beat | Time | What happens | Wow moment |
|---|---|---|---|
| 1. Meet Priya | 0:00–1:00 | No tabs visible. Onboarding chat: *"Hi, I'm Paisa Pal. Aapka naam?"* → 4 questions with progress bar → "Investment DNA" card slides up: *"Conservative starter, ₹5k/month, 5-year goal, tax-saver priority."* | Emotional payoff card |
| 2. Where do I start? | 1:00–2:15 | Priya types: *"Mujhe 5 saal mein ghar ke liye paise jodne hain"* → streaming Hinglish reply explains the goal-SIP gap, recommends 2 funds (Parag Parikh Flexi Cap + HDFC Index), rejects equity for short term. **Goal Plan card** auto-renders below: ₹X/month at 12% → ₹Y in 60 months. Sources: AMFI, SEBI, RBI cited inline. | Streaming + grounded sources |
| 3. Tax kaise bachaye? | 2:15–3:15 | Calculator card (pure Python, instant): ELSS ₹1.5L → ₹46,800 saved at her bracket. Side-by-side ELSS vs PPF vs NPS. *"ELSS lock-in 3 years vs PPF 15 — for your goal, ELSS wins."* | Instant deterministic math |
| 4. Market gir gaya, SIP band karu? | 3:15–4:00 | Pre-loaded scenario. **Behavioural nudge** card fires: *"In the 2020 crash, SIPs that didn't stop ended 2024 +47% richer than ones that paused 6 months."* | Moat moment |
| 5. Show me the receipts | 4:00–4:30 | Click "Sources & History". Real `KnowledgeVersion` entries: AMFI NAV, RBI repo, SEBI definitions. Confidence: 🟢 Grounded. *"This is what no other Indian app shows you."* | Trust as a feature |
| 6. Globally extensible | 4:30–5:00 | Click the "📊 Global Markets" tab (visible since step 1, just unused). Same engine, US tickers, SEC + FRED grounding, same Trust Layer entries. *"India-first by product choice; market-agnostic by architecture. The US codepath has been running in parallel the whole demo."* | Closes the "small market" objection without feeling staged |

This narrative is **buildable with current code + the P0/P1 work below**. No new infra needed.

---

## 5. Prioritised Roadmap

> Conventions: **P0** = must fix now (demo blockers + bugs). **P1** = highest demo impact. **P2** = polish. **P3** = post-pitch.

### P0 — Demo Blockers & Bug Fixes (do first, all are 1-file changes)

| # | Task | File | Effort | Demo impact |
|---|---|---|---|---|
| 0.1 | Add `hindi: bool = False` to `beginner_answer_india()`; pass `hindi` and `profile` from `ui/app.py:393` | `core/wiki_india.py:987`, `ui/app.py:393` | 15 min | Fixes Hindi on the most common path |
| 0.2 | Fix `minutes_old` always-zero bug (compare to last-trade timestamp, not `fetched_at`) | `core/fetchers_india.py:184,199` | 30 min | "Delayed" label actually fires |
| 0.3 | Replace `timezone(timedelta(hours=-4))` with `ZoneInfo("America/New_York")` | `agents/ingest_agent.py:131`, `agents/storage_agent.py:158` | 15 min | Correct EST/EDT 12 months/yr |
| 0.4 | Wire `record_wiki_version()` for US wiki writes (thread `engine` through `ingest_to_wiki`) | `core/wiki.py:271,298,317`, `agents/analysis_agent.py` | 45 min | Trust tab populates |
| 0.5 | Wire `record_wiki_version()` for India wiki writes (`_iwrite()`) | `core/wiki_india.py:81–87`, `agents/analysis_agent.py:181` | 30 min | India audit trail exists |
| 0.6 | Replace per-row DB sessions with batched `session.add_all()` + single commit | `agents/ingest_agent.py:179–185, 243–251` | 30 min | 200×+ throughput; less log noise |
| 0.7 | Make `_get_engine()` a module-level singleton in `fetchers_india.py` | `core/fetchers_india.py:56–58` | 10 min | Removes engine churn |
| 0.8 | Replace `datetime.utcnow()` with `lambda: datetime.now(timezone.utc)` in models | `core/models.py:30,43,55,75,105,106,128` | 15 min | 3.13-ready |
| 0.9 | Stop using `_STALE_THRESHOLD_MINUTES` dead constant in `ingest_agent.py:52`; document where the live one lives | `agents/ingest_agent.py` | 5 min | Code hygiene |
| 0.10 | Add `data/wiki/insights/` and `data/wiki_india/insights/` to `.gitignore` (except `.gitkeep`) | `.gitignore` | 5 min | Stop polluting `git status` |

**Total P0 time:** ~3 hours. **Do this first.** None of P1+ matters if these are still broken on the day of the demo.

### P1 — Highest Demo Impact (do next, in this order)

#### 1.1 — Pre-seed both wikis (25 India + 8 US, ~70/30 split)
**Why:** The cold-start crisis on both sides. India `equities/`, `mutual_funds/`, `macro/` are empty `.gitkeep` placeholders. The US side has 5 stock pages but no concepts/macro coverage — a global-tab demo asking "what's a 401(k)?" falls through to Gemini training data. **The grounding pitch must hold on both surfaces, or the global-extensibility argument is hollow.**
**India seed (25 pages):**
- `equities/` (5): NIFTY_50.md, NIFTY_BANK.md, NIFTY_NEXT_50.md, RELIANCE.md, TCS.md
- `mutual_funds/` (8): Parag_Parikh_Flexi_Cap.md, HDFC_Index_Nifty_50.md, ICICI_Prudential_Bluechip.md, Axis_ELSS.md, Mirae_Asset_ELSS.md, SBI_Small_Cap.md, Quant_Active.md, Nippon_India_Multi_Asset.md
- `macro/` (3): rbi_rates.md, inflation_cpi.md, fiscal_calendar.md
- `concepts/` (new dir, 9): sip.md, elss_vs_ppf_vs_nps.md, emergency_fund.md, sip_vs_lumpsum.md, ltcg_stcg_2024.md, demat_account.md, direct_vs_regular.md, expense_ratio.md, market_cap_categories.md
- Frontmatter: `last_updated`, `data_sources: [SEBI, AMFI, RBI]` (mix), `stale: false`, `confidence_factors: ["regulator-cited"]`.

**US seed expansion (8 new pages on top of the existing 5):**
- `stocks/` (5 new on top of AAPL/GOOGL/JNJ/MSFT/NVDA): AMZN.md, META.md, TSLA.md, BRK_B.md, JPM.md
- `concepts/` (3 new on top of `finance_basics.md`): 401k_basics.md, etf_vs_mutual_fund_us.md, roth_vs_traditional_ira.md
- Frontmatter: `data_sources: [SEC, FRED]` (mix), regulator-cited.

**Why both:** Beat 6 of the demo ("Globally extensible") collapses without US concepts. Asking "what's a Roth IRA?" on the US tab and getting a grounded, sourced answer is what makes the architecture-portability claim real.

**Effort:** 8–10 hours total writing (or ~3 hours with Gemini bootstrap + manual fact-check pass).
**Files impacted:** `data/wiki_india/**`, `data/wiki/stocks/`, `data/wiki/concepts/`.
**Simpler alternative:** Two scripts — `scripts/seed_india_wiki.py` and `scripts/seed_us_wiki.py` — generate Gemini drafts, you hand-edit, commit final markdown to the repo so it ships with `git clone`.
**Demo impact:** ⭐⭐⭐⭐⭐ — biggest single change. Both surfaces go from "vague generic" to "specific, grounded, regulator-cited."

#### 1.2 — Replace `text_area` + button with `st.chat_input` + streaming
**Why:** A 10s spinner feels broken. Streaming feels alive. Same Gemini cost.
**What to change:**
- In `ui/app.py:376–411`: replace `st.text_area` + `st.button` with `st.chat_input()` and `st.chat_message()`.
- Persist `st.session_state.india_messages` as `list[{"role", "content", "sources", "confidence"}]`.
- Use Gemini `stream=True` and yield via `st.write_stream()`.
- On cold-start (empty chat), show 4 clickable suggestion chips (the demo-rehearsed questions).
- Always end assistant turn with the SEBI disclaimer.
**Effort:** 3 hours.
**Files:** `ui/app.py`, possibly a small `core/streaming.py` helper.
**Demo impact:** ⭐⭐⭐⭐⭐ — single biggest perceived-quality jump.

#### 1.3 — Make India Advisor the default landing tab; rename US tab to "Global Markets" (keep visible)
**Why:** India-first, not India-only. US tab stays in the tab bar — visible, working, populated — so beat 6 of the demo lands as "the engine you've been watching also runs on US tickers" rather than a magic toggle.
**What:** Reorder tabs in `ui/app.py:173`:
```python
india_tab, global_tab, sources_tab, health_tab = st.tabs(
    ["🇮🇳 India Advisor", "🌍 Global Markets", "🔍 Sources & History", "⚙️ System Health"]
)
```
- Rename internal variable `dashboard_tab` → `global_tab` for clarity.
- The Global Markets tab continues to render US prices, SEC headlines, and the existing US wiki — no functional change beyond the rename.
- Add a one-line caption under the tab title: *"Same engine, US tickers — proof the architecture is market-agnostic."*
**Effort:** 30 minutes.
**Demo impact:** ⭐⭐⭐⭐

#### 1.4 — Conversational onboarding wizard (gate the app behind it)
**Why:** Current onboarding is a dense 2-column form buried inside the India tab. First impression should be a 60-second conversation that ends with an "Investment DNA" card.
**What:**
- When `UserProfile` is missing, render only the wizard — no tabs visible.
- Use `st.chat_message` to ask 4 questions one at a time with `st.session_state.onboarding_step`.
- Show `st.progress(step/4)`.
- After completion, render an "Investment DNA" summary card with the user's name, monthly SIP budget, risk profile, primary goal — visually distinct, screenshot-worthy.
- Store everything in `UserProfile`.
**Effort:** 4 hours.
**Files:** `ui/app.py:261–354`, possibly a new `ui/onboarding.py`.
**Demo impact:** ⭐⭐⭐⭐⭐ — emotional anchor of the demo.

#### 1.5 — Build `core/calculators.py` (deterministic Python, no LLM)
**Why:** Every Indian who ever Googles "SIP calculator" wants this. It's instant, free, never hallucinates, and visually compelling.
**What:**
```python
def sip_future_value(monthly: float, annual_return_pct: float, years: int) -> dict
def sip_needed_for_goal(target: float, annual_return_pct: float, years: int) -> dict
def elss_tax_savings(annual_invested: float, tax_bracket_pct: float) -> dict
def step_up_sip(monthly: float, step_up_pct: float, annual_return_pct: float, years: int) -> dict
def emergency_fund_target(monthly_expenses: float, months: int = 6) -> dict
def lumpsum_vs_sip(amount: float, annual_return_pct: float, years: int) -> dict
```
- Each returns a dict with `total_invested`, `estimated_returns`, `future_value`, plus an optional `monthly_series` for charting.
- Add `tests/test_calculators.py` with golden values (₹5k/mo, 12%, 10y → ₹11.6L FV).
**Then in `ui/app.py`:** Add a "🧮 Quick Tools" expander inside the chat. Auto-detect calculator intent in the chat (regex on "SIP", "kitna", "calculator", "goal") and emit a card alongside the chat answer.
**Effort:** 4 hours.
**Files:** `core/calculators.py` (new), `tests/test_calculators.py` (new), `ui/app.py`.
**Demo impact:** ⭐⭐⭐⭐⭐ — instant gratification, no Gemini latency, no hallucination risk.

#### 1.6 — Reflection critic on every Gemini answer (the hallucination guardrail)
**Why:** A single synthesis call is one prompt away from a confident wrong answer. A self-critique pass catches: unsupported numeric claims, hallucinated fund names, missing SEBI disclaimer, tone mismatch (too technical for beginners), and contradictions with cited sources. **This is the single highest-leverage trust-quality lever in the entire pipeline.**
**Pipeline shape:**
```
Question
  → [LLM call 1] retrieval-grounded synthesis (existing path)
  → [LLM call 2] reflection critic with structured rubric
  → if critic flags issues:
      → [LLM call 3] regenerate with critique injected as additional context
  → return answer + sources + confidence + critic_log (saved to insight page)
```
**Critic prompt structure (strict, machine-parseable output):**
```
You are a strict fact-checker for an Indian investing advisor.
Review the ANSWER below against the SOURCE_PAGES.

Score each (PASS / WARN / FAIL) and explain in ≤ 1 line:
  1. GROUNDED — every numeric claim, fund name, scheme code, and rate appears in SOURCE_PAGES
  2. SCOPED — answer stays educational (no "buy now", no "I recommend stock X" for a single name)
  3. DISCLAIMED — ends with the SEBI disclaimer
  4. TONE — matches the user's apparent level (beginner / intermediate / advanced)
  5. CONSISTENT — no internal contradictions, no claims that conflict with SOURCE_PAGES
  6. PROFILE-FIT — uses the user's profile (income, goal, horizon) where given

Output strictly:
  GROUNDED: <PASS|WARN|FAIL> — <reason>
  SCOPED: <PASS|WARN|FAIL> — <reason>
  ...
  VERDICT: <ACCEPT|REGENERATE>
  REGENERATE_GUIDANCE: <one paragraph or empty>
```
- If `VERDICT: REGENERATE`, run one regeneration with `REGENERATE_GUIDANCE` appended to the original synthesis prompt. Hard cap: one regen per query.
- Save the full critic log to the insight page YAML frontmatter (`reflection: {grounded: PASS, scoped: PASS, ...}`) — this becomes a Trust Layer asset.
- Surface in UI as a small badge next to the confidence pill: 🟢 *"Fact-checked"* on accept, 🟡 *"Refined after self-review"* on regen.
**Effort:** 3 hours (prompt engineering + parser + UI badge + tests).
**Files:** `core/reflection.py` (new), `core/wiki_india.py` (call site), `core/wiki.py` (call site), `ui/app.py` (badge), `tests/test_reflection.py` (new).
**Cost impact:** +1 Gemini call per query baseline, +2 if regen fires (~10% of queries). Net cost is small after FAQ cache + demo cache absorb the high-frequency questions.
**Demo impact:** ⭐⭐⭐⭐⭐ — the difference between "AI assistant" and "trustworthy AI assistant."

#### 1.6b — Replace LLM routing call with embedding similarity (deterministic, free, faster)
**Why:** The 2-call grounded pattern (route → synthesise) is correct (an earlier recommendation to combine them was withdrawn — see §1 "What I previously got wrong"). What we *can* safely cut is the LLM-powered routing call: choosing 3–5 relevant pages is a similarity problem, not a reasoning problem. Deterministic embeddings nail it for free.
**What:**
- Add `sentence-transformers` (free, ~23MB, CPU-only model `all-MiniLM-L6-v2`) to `requirements.txt`.
- New `core/retrieval.py`: build embeddings for every wiki page once on startup; cache to `data/embeddings_india.npy` and `data/embeddings_us.npy`. Re-embed only changed pages on each ingest cycle.
- New function `route_pages(question: str, wiki: Literal["india","us"], k: int = 5) -> list[str]` returning top-k page filenames by cosine similarity.
- In `query_india()` (`wiki_india.py:879`) and `query_wiki()` (`wiki.py:458`), replace the routing Gemini call with `route_pages(...)`. Synthesis call is unchanged — it still receives full page contents.
**Effort:** 4 hours (incl. tests with golden questions and re-embed-on-write logic).
**Files:** `core/retrieval.py` (new), `core/wiki.py`, `core/wiki_india.py`, `requirements.txt`, `tests/test_retrieval.py` (new).
**Net effect on the per-query LLM call budget:** routing call removed (−1), reflection call added (+1), conditional regen call (+0.1 amortised). Net: ~+0.1 calls vs today, with much higher quality.
**Demo impact:** ⭐⭐⭐⭐ — the chat feels noticeably faster (routing was 2–3s, embedding lookup is <50ms) and the freed token budget pays for the reflection critic.

#### 1.7 — Pre-cache the 4 demo-rehearsed questions
**Why:** Gemini free tier has 15 RPM. If you demo at a meetup over WiFi after a peer demoed, you may be rate-limited at the worst moment.
**What:**
- Run the 4 demo questions ahead of time, capture the streamed responses verbatim, save to `data/demo_cache/{question_hash}.md`.
- In `ui/app.py`, before calling Gemini, check `data/demo_cache/`; if hit, replay with a small `time.sleep(0.02)` between chunks to mimic streaming. (Not for production, but explicit in code as `DEMO_REPLAY_MODE`.)
**Effort:** 2 hours.
**Files:** `scripts/build_demo_cache.py` (new), small block in `ui/app.py`.
**Demo impact:** ⭐⭐⭐⭐ — saves your live demo from infrastructure failure.

#### 1.8 — Replace NSE price dataframe with metric cards + market summary banner
**Why:** Tables read as developer dashboards; metric cards read as consumer products.
**What:** `ui/app.py:184–218` → 5-column `st.metric` grid; one-liner above ("🟢 Markets are up today" / "⏸️ Markets closed; showing last prices").
**Effort:** 1 hour.
**Demo impact:** ⭐⭐⭐ — small but cumulative polish.

#### 1.9 — Intent classifier + ReAct loop for multi-step queries
**Why:** Single-shot synthesis works for "what is SIP?" — it fails on "should I move my PPF money to ELSS given that I'm 28 and want to buy a house in 5 years?" That requires reading the PPF page, the ELSS page, the tax-comparison page, applying the user's profile, computing the trade-off, and reasoning about the lock-in. A single prompt either skips steps or hallucinates them. **ReAct (Thought → Action → Observation) makes the reasoning auditable and grounded.**

**Pipeline shape:**
```
Question
  → [LLM call 1] intent classifier (cheap):
       returns one of {factual_simple, comparative, calculator, emotional, eligibility, multi_step}
  → branch:
      factual_simple → existing horizon path (1 call) → reflection (1 call) = 2 calls
      calculator     → pure Python card, optional 1 explanation call = 0–1 calls
      comparative
        OR
      multi_step     → ReAct loop (1–4 calls) → reflection (1 call) = 2–5 calls
      emotional      → empathetic horizon path (1 call) → reflection (1 call) = 2 calls
      eligibility    → ReAct loop with stricter rubric (2–3 calls) → reflection (1 call) = 3–4 calls
```

**Intent classifier prompt:** small, structured output. ~200 tokens in, ~30 tokens out. Cheap.
```
Classify the user question into ONE of:
  factual_simple   — single-concept "what is X" / "explain X"
  comparative      — "X vs Y" / "should I switch from X to Y"
  calculator       — explicit number calculation ("how much will ₹5000 SIP grow in 10 years")
  emotional        — fear / panic / regret framing ("market gir gaya, kya karu")
  eligibility      — rule-based question ("can I claim 80C if I'm NRI")
  multi_step       — anything requiring 3+ pages of context to answer well

Output strictly: INTENT: <one_value>
Reasoning: <≤ 1 line>
```

**ReAct action set (small, well-typed, no free-form tool use):**
```python
class Action(TypedDict):
    type: Literal["read_page", "compute", "consult_profile", "final_answer"]
    args: dict

# read_page(filename)        → returns page content (already loaded via embedding routing top-K)
# compute(formula, kwargs)   → calls core.calculators.* deterministic functions
# consult_profile(field)     → returns one field from UserProfile
# final_answer(text, sources)→ terminates the loop
```

**ReAct prompt template:**
```
You are an Indian investing advisor reasoning step-by-step.
You may emit ONE action per turn from the set:
  read_page("<filename>")
  compute("<calculator_name>", {<args>})
  consult_profile("<field>")
  final_answer("<markdown>", [<source_filenames>])

USER QUESTION: {question}
USER PROFILE: {profile_block}
INDEX (top-K pages selected by retrieval): {top_k_titles}
RECENT OBSERVATIONS: {scratchpad}

Output strictly:
  THOUGHT: <one paragraph>
  ACTION: <one action call>
```

- Hard cap: **4 iterations**. If no `final_answer` by iteration 4, force termination with a synthesis call over the scratchpad.
- Each iteration is one Gemini call.
- The full thought→action→observation trace is saved to the insight page YAML (`react_trace: [...]`) — *this is a Trust Layer asset and a powerful demo prop* ("here's exactly how the AI reasoned").
- Reflection critic (§1.6) runs on the final answer, same as the simple path.

**Effort:** 6 hours (intent classifier + action dispatch + scratchpad + trace logging + tests + UI "🧠 Reasoning trace" expander).
**Files:** `core/react.py` (new), `core/intent.py` (new), `core/wiki_india.py` (router), `ui/app.py` (reasoning trace expander), `tests/test_react.py` (new), `tests/test_intent.py` (new).
**Demo impact:** ⭐⭐⭐⭐⭐ — the "🧠 Reasoning trace" expander on a comparative question is *the* moment that separates this from "another ChatGPT wrapper" in a VC's mind. Add it as an explicit beat to the demo if you have 30 extra seconds.

#### 1.10 — Refactor `wiki_ingest.py` 8 processors into one parameterised function
**Why:** The duplication is real, but the work isn't optional — these processors feed the US wiki, which is a pitch asset. Refactor, don't hide.
**What:**
- New `core/wiki_ingest.py` shape: a single `process_raw_file(path: Path, spec: ProcessorSpec) -> None` driven by a `PROCESSOR_REGISTRY: dict[str, ProcessorSpec]` keyed on the raw-file directory name (`sec/`, `fred/`, `alpha_vantage/`, …).
- `ProcessorSpec` is a small dataclass: `target_wiki_section`, `extraction_prompt_template`, `required_fields`, `output_section_marker`.
- Reflection critic (§1.6) runs on the Gemini extraction output before it's written to the wiki page — same hallucination guardrail applied to ingest, not just user queries.
**Effort:** 4 hours.
**Files:** `core/wiki_ingest.py` (rewrite), `tests/test_wiki_ingest.py` (extend existing).
**Net effect:** ~250 fewer lines, same behaviour, all 8 processors now benefit from reflection.
**Demo impact:** ⭐⭐ — invisible to the user, but a senior reviewer reading the codebase notices immediately.

### P2 — Polish (after P1 is stable)

#### 2.1 — Hinglish detection + language radio (English / हिंदी / Hinglish)
**Why:** Hindi-only is a binary; Hinglish is the lingua franca for the target user.
**What:** Replace `hindi: bool` with `language: Literal["english","hindi","hinglish"]` (keep backward-compat shim for one release). Inject one of three system instructions into the Gemini prompt. Detect Hinglish in `_INDIA_BEGINNER_TRIGGERS` with patterns: `mujhe, kaise, kya hai, samjhao, paisa, nivesh, sip shuru, tax bachana, kaun sa fund, kitna return, share market, gir gaya, band karu`.
**Effort:** 2 hours.
**Files:** `core/wiki_india.py`, `ui/app.py`.

#### 2.2 — Custom CSS for visual polish
**Why:** Streamlit defaults read as "internal tool".
**What:** Add a `st.markdown` CSS block at the top of `ui/app.py`:
- Gradient header banner (saffron → deep blue → green tint, India-coded).
- Rounded chat bubble styling.
- Inter font import (Google Fonts).
- Mobile max-width (~480px on phones, 800px on desktop).
- Green/red metric tinting based on delta.
**Effort:** 2 hours.

#### 2.3 — Confidence as a single 🟢 / 🟡 / 🔴 badge with tooltip (don't expose raw float)
**Why:** A 0.85 number is for the engineer; a green dot is for the user.
**What:** Map `score` → `"🟢 Grounded" | "🟡 Partial" | "🔴 Limited"`. Show raw breakdown only inside the "Sources & History" tab.
**Effort:** 1 hour.

#### 2.4 — `core/nudges.py` — behavioural rules engine (no LLM, deterministic)
**What:**
```python
def generate_nudges(profile, recent_questions, market_data) -> list[str]
```
Rules: market drop > 3% today, user hasn't visited in 3+ days, Jan–Mar + tax goal, recent question contains "stop SIP" / "sell" / "crash". Render as a "Daily Tip" card above the chat.
**Effort:** 3 hours.

#### 2.5 — Smart FAQ system (`core/faq.py` + `data/wiki_india/faq/`)
**Why:** ~20 patterns cover 80% of beginner questions. Pre-computed answers = 0ms, 0 cost, never hallucinate, work offline.
**What:** 20 markdown files with YAML `question_patterns: [...]`. `faq_match(q) -> tuple[answer, sources] | None` does substring + simple regex matching. Check FAQ in `query_india()` *before* Gemini; show "⚡ Instant answer" badge with a "Get a personalised answer" button if user wants the full LLM treatment.
**Effort:** 4 hours (writing FAQs + matcher + tests).

#### 2.6 — Unified startup script `run.py` + seed-data script
**Why:** Two-terminal startup is friction for a recruiter or VC clone-and-run.
**What:**
- `run.py`: spawns `main.py` agents and Streamlit in one process, handles SIGTERM cleanly.
- `scripts/seed_india_demo.py`: one-shot fetch + wiki page creation so a fresh clone has demo-ready data in <60s.
- README: single command — `python scripts/seed_india_demo.py && python run.py`.
**Effort:** 3 hours combined.

### P3 — Future / Post-Pitch (don't build before demoing)

- **Telegram bot** (the real distribution channel for the next 100M).
- **What-If scenario simulator** (backtest SIP since 2018 vs FD).
- **Portfolio second-opinion** (paste your holdings → AI-grounded review). This is the v2 monetisation product.
- **Self-consistency mode for high-stakes queries** — generate the synthesis answer twice with different temperatures, run reflection on both, surface differences. Deeper hallucination control for "tax" and "eligibility" intents. Gemini-only; +1–2 calls.
- **Postgres migration** (when you outgrow SQLite — you won't for a year).
- **Marathi / Tamil / Bengali** language packs (Gemini handles all three competently — verify with seed page generation).
- **Analytics** (Plausible or PostHog free tier).
- **CI** (GitHub Actions matrix on `pytest + ruff + mypy`).
- **Refactor `wiki.py` and `wiki_india.py` into one parameterised module.**
- **Tool-use upgrade** — once the Gemini SDK exposes function calling cleanly, replace the manual ReAct loop with native tool-calling. Same pipeline, less prompt-parsing fragility.

**Explicitly NOT in P3:** multi-LLM abstraction. We are committed Gemini-only for the demo and the foreseeable post-pitch period. Hindi/Hinglish quality and a single mental model outweigh vendor diversification at this stage. Revisit only if Gemini's free-tier policy or quality regresses materially.

---

## 6. Technical Tasks (consolidated)

| Task | Why | File | Effort |
|---|---|---|---|
| Batch DB writes per cycle | 200× throughput, less noise | `agents/ingest_agent.py` | 30m |
| Engine singleton | Stop creating engines per fetch | `core/fetchers_india.py` | 10m |
| **Embedding-based routing** (replaces LLM routing call) | Free, deterministic, faster than 2–3s LLM call | `core/retrieval.py` (new), `core/wiki.py`, `core/wiki_india.py` | 4h |
| **Reflection critic** on every Gemini answer | Single biggest hallucination control | `core/reflection.py` (new), `core/wiki_india.py`, `core/wiki.py` | 3h |
| **Intent classifier** (cheap Gemini call) | Routes to ReAct vs simple synthesis | `core/intent.py` (new) | 1.5h |
| **ReAct loop** for `comparative` / `multi_step` / `eligibility` intents | Auditable multi-step reasoning, grounded each step | `core/react.py` (new) | 6h |
| **Refactor `wiki_ingest.py`** 8 processors → 1 parameterised function + registry | Same behaviour, ~250 fewer lines, all processors get reflection | `core/wiki_ingest.py` | 4h |
| Split `lint_wiki()`: keep deterministic staleness, surface contradiction findings in UI | Don't lose the staleness signal; make Gemini lint earn its keep | `core/wiki.py:1014–1050`, `ui/app.py` | 2h |
| In-memory wiki page cache (60s TTL) | Stop re-reading files per query | `core/wiki.py`, `core/wiki_india.py` | 1h |
| `@st.cache_resource` on engine factory in UI | Stop re-creating engine on rerun | `ui/app.py` | 15m |
| Per-fetcher `asyncio.wait_for(timeout=15)` | Prevent single-fetch stalls | `agents/ingest_agent.py`, `core/fetchers_india.py` | 1h |
| Reasoning-trace expander in UI (`🧠 How I reasoned`) | Surfaces ReAct trace as a Trust Layer asset | `ui/app.py` | 1h |

## 7. Product Tasks

| Task | Owner | Effort |
|---|---|---|
| Write 25 India + 8 US seed wiki pages | You + Gemini bootstrap | 8–10h |
| Onboarding wizard rebuild | You | 4h |
| Investment DNA card | You | 2h |
| Calculator suite | You | 4h |
| Reflection critic prompt + rubric | You | 2h |
| Intent classifier prompt + tests | You | 1.5h |
| ReAct prompt + action dispatcher | You | 4h |
| "🧠 Reasoning trace" UI expander | You | 1h |
| Demo cache (covers all 6 demo beats incl. ReAct trace) | You | 2h |
| Behavioural nudges | You | 3h |
| FAQ system | You | 4h |

## 8. UX Tasks

| Task | Effort |
|---|---|
| Chat input + streaming | 3h |
| Suggestion chips on cold-start | 1h |
| India tab default | 15m |
| Metric cards replacing dataframes | 1h |
| CSS polish + Indian palette | 2h |
| Confidence badge (🟢🟡🔴) | 1h |
| Mobile max-width / responsive tweaks | 1h |
| Hide system internals (env vars, paths) from UI captions | 30m |

## 9. Data Tasks

**India side (25 pages):**

| Task | Source | Effort |
|---|---|---|
| Seed `wiki_india/equities/` (5 pages) | NSE + AMFI | 1h |
| Seed `wiki_india/mutual_funds/` (8 pages) | AMFI scheme master + Value Research public data | 3h |
| Seed `wiki_india/macro/` (3 pages) | RBI DBIE | 1h |
| Seed `wiki_india/concepts/` (9 pages) | SEBI investor education + Zerodha Varsity (cite, don't copy) | 3h |

**US side (8 new pages on top of existing 5):**

| Task | Source | Effort |
|---|---|---|
| Seed `wiki/stocks/` (5 new: AMZN, META, TSLA, BRK_B, JPM) | SEC + company IR + FRED | 2h |
| Seed `wiki/concepts/` (3 new: 401k_basics, etf_vs_mutual_fund_us, roth_vs_traditional_ira) | IRS publications + SEC investor.gov | 1.5h |

**Cross-cutting:**

| Task | Effort |
|---|---|
| Verify `data_sources` frontmatter on every seed page (India + US) | 30m |
| Add NSE/BSE small-cap & midcap tickers to `core/settings.py:INDIA_SYMBOLS` | 15m |
| Build embeddings for both wikis on first run; cache to `data/embeddings_*.npy` | (covered by §1.6b) |

## 10. Trust Layer Tasks

| Task | Effort |
|---|---|
| Wire `record_wiki_version()` from `_iwrite()` (India) | 30m |
| Wire `record_wiki_version()` from `_write_wiki_file()` (US) | 45m |
| Show inline "🟢 Grounded" badge with first 3 source domains | 1h |
| **Show "🛡️ Fact-checked" badge** when reflection critic accepts on first pass; **"🟡 Refined after self-review"** when regen fired | 1h |
| **"🧠 Reasoning trace" expander** below ReAct answers — shows Thought / Action / Observation chain | 1h |
| "Sources & History" tab: real timeline, last 20 versions | 1h |
| **"Sources & History" tab: include reflection log** (which queries triggered regen, which checks failed) | 1h |
| **Surface Gemini contradiction findings** as a "⚠️ This page conflicts with `<other>`" badge inline on the conflicting page (was previously written to `lint_*.md` and never read) | 1.5h |
| Regulator-bonus on confidence (+0.05 if any source URL contains `rbi`, `sebi`, `amfi`, `nseindia`, `sec.gov`, `federalreserve`) | 30m |
| Show source-validation status (reachable / 4xx / 5xx) in UI | 1h |

## 11. Deployment Tasks

| Task | Why | Effort |
|---|---|---|
| `run.py` unified start | Single command demo | 30m |
| `scripts/seed_india_demo.py` | <60s cold-start | 2h |
| README rewrite for product audience | First impression | 2h |
| Streamlit Community Cloud deploy (`streamlit.app`) | Free, public URL for pitch | 1h |
| `.streamlit/secrets.toml` (gitignored) for cloud Gemini key | — | 15m |
| `Procfile` for Railway / Render fallback | Just in case | 30m |
| `Dockerfile` cleanup (currently works but bloated) | — | 1h |

## 12. Resume / Portfolio Tasks

| Task | Effort |
|---|---|
| GIF / 30s screen recording of the demo | 1h |
| Pinned GitHub repo with rewritten README | 30m |
| Architecture diagram (excalidraw, embed in README) | 1h |
| 1-page case study PDF (problem → approach → architecture → metrics) | 2h |
| LinkedIn post: 3 paragraphs + GIF | 30m |
| `docs/ARCHITECTURE.md` refresh with current state | 1h |

## 13. Pitch Deck Plan (10 slides)

| # | Slide | Content |
|---|---|---|
| 1 | **Title** | "Niveshak AI / Paisa Pal — An AI investing companion for the next 100M Indian savers." Logo, your name, date. |
| 2 | **The Problem** | Three barriers (complexity, trust, advice gap). One stat: 76% of Indian SIPs are stopped within 3 years (AMFI 2024). One persona: Priya. |
| 3 | **The Insight** | Incumbents do *one* of {grounding, Hinglish, personalisation, education}. **None does all four.** That's the wedge. |
| 4 | **Demo (live or 90s GIF)** | The 5-minute Priya narrative compressed. Onboarding → Hinglish answer → calculator → nudge → receipts. |
| 5 | **How It Works** | The 3-agent + LLM Wiki + Trust Layer architecture diagram, **plus the per-query reasoning pipeline** (intent classify → embedding-routed retrieval → ReAct loop on multi-step queries → reflection critic → regen-if-flagged → cited answer). One sentence: *"Every answer is grounded in versioned, cited, regulator-sourced markdown, reasoned through an auditable ReAct trace, and fact-checked by a Gemini critic before it reaches the user — no vector DB, no black box, no hallucination shipping silently."* |
| 6 | **Why Now** | UPI maturity (350M users), SEBI 2024 finfluencer crackdown, Gemini Flash economics, AMFI/RBI/SEBI open APIs, Hindi LLM quality threshold crossed. |
| 7 | **Market** | TAM 100–150M (AMFI demographic ceiling). Beachhead 1M users in 24 months. Compare CAGR of MF AUM (~20%) and demat accounts (~28% YoY FY24). |
| 8 | **Right-to-Win & Moat** | Free-tier-honest unit economics. Verifiable grounding (regulatory tailwind). Multilingual at zero marginal cost. Compounding wiki. **Architecture is market-agnostic — running today on US (SEC + FRED) and India (AMFI + RBI + SEBI) simultaneously, on day one. Most India fintechs are India-only by design; this one is by *choice*.** Hallucination-controlled by reflection critic + ReAct on every reasoning-heavy answer — auditable trust, not a black box. |
| 9 | **Monetisation** | Year 1 free. Year 2: ₹99/yr portfolio review + opt-in affiliate. Year 3: B2B2C white-label. *Never* a brokerage. |
| 10 | **Ask & Roadmap** | What you need (capital / mentorship / a design partner). 3-month / 12-month milestones. Risks + mitigations. Your contact. |

**Appendix slides** (have ready, don't show unless asked): cost economics per query, competitor matrix, technical architecture deep-dive, hiring plan, regulatory analysis (SEBI educational vs advisory line).

---

## 14. Final Demo Checklist (run through 30 minutes before)

- [ ] `git status` clean. No `untracked` files visible.
- [ ] `pytest tests/ -q` green. Test count matches README.
- [ ] `ruff check . && mypy core agents ui` clean.
- [ ] `python scripts/seed_india_demo.py` succeeded; `data/wiki_india/{equities,mutual_funds,macro,concepts}/` populated.
- [ ] `data/finance.db` exists; at least 1 `KnowledgeVersion` row exists (`SELECT count(*) FROM knowledge_versions;`).
- [ ] `python run.py` starts both agents and Streamlit, exits cleanly on Ctrl-C.
- [ ] Onboarding: 4 questions visible one at a time, "Investment DNA" card renders.
- [ ] Suggestion chips appear on cold-start chat.
- [ ] `st.chat_input` streams (not a 10s spinner).
- [ ] Hindi toggle works on **beginner** path (the previously-broken one).
- [ ] Calculator card appears for "SIP calculator" / "kitna" / "goal" intents.
- [ ] Behavioural nudge fires for "stop SIP" / "crash" / "gir gaya".
- [ ] "Sources & History" tab shows 10+ real entries with regulator domains.
- [ ] 🟢 Grounded badge visible on every demo question.
- [ ] 🛡️ Fact-checked badge visible — reflection critic ran and accepted (or 🟡 if regen fired).
- [ ] 🧠 Reasoning trace expander populated for the comparative demo question ("ELSS vs PPF").
- [ ] ReAct trace shows ≤4 iterations and a `final_answer` action — no cap exhaustions on demo queries.
- [ ] Intent classifier behaves: "what is SIP" → factual_simple (2 calls), "ELSS vs PPF for me" → multi_step/comparative (4–5 calls), "₹5000 SIP for 10 years" → calculator (0–1 calls).
- [ ] Embeddings cached on disk: `data/embeddings_india.npy` and `data/embeddings_us.npy` exist; `route_pages()` returns top-K in <50ms.
- [ ] Both wikis populated: `data/wiki_india/{equities,mutual_funds,macro,concepts}/` AND `data/wiki/{stocks,concepts}/` have seed pages.
- [ ] Global Markets tab works end-to-end (ask "what's a Roth IRA?" — get a grounded SEC/IRS-cited answer with reflection badge).
- [ ] Demo cache populated: all 6 demo beats (incl. ReAct-trace beat) return in <2s if Gemini rate-limits.
- [ ] Mobile (responsive view in DevTools) — text doesn't overflow, chat usable.
- [ ] Phone backup: Streamlit Cloud public URL (`*.streamlit.app`) reachable on cellular.
- [ ] README screenshot/GIF refreshed.
- [ ] `python scripts/build_demo_cache.py` executed, `data/demo_cache/*.md` exists.
- [ ] All API keys in `.env` valid; `.env.example` does not contain real keys (`grep -i "AIza"` returns nothing).
- [ ] Pre-rehearsed answers re-read for tone (any "As an AI language model…" leakage = re-prompt).
- [ ] Pitch deck PDF exported, on the laptop and on phone (offline).
- [ ] Hardware: charger, HDMI/USB-C dongle, water.

---

## 15. Cursor / Claude Execution Prompts

These are copy-paste-ready prompts to drop into a Cursor or Claude Code session. Each is constrained, specific, and references the actual files.

### 15.1 — Pre-seed the India wiki

```
You are working in /Users/charanrathore/Documents/starter-project. Generate 25 seed
markdown files for `data/wiki_india/` covering Indian equities (NIFTY_50, NIFTY_BANK,
NIFTY_NEXT_50, RELIANCE, TCS), top mutual funds (Parag Parikh Flexi Cap, HDFC Index
Nifty 50, ICICI Prudential Bluechip, Axis ELSS, Mirae Asset ELSS, SBI Small Cap, Quant
Active, Nippon India Multi Asset), macro (rbi_rates, inflation_cpi, fiscal_calendar),
and concepts (sip, elss_vs_ppf_vs_nps, emergency_fund, sip_vs_lumpsum, ltcg_stcg_2024,
demat_account, direct_vs_regular, expense_ratio, market_cap_categories).

Each file must have:
- YAML frontmatter: `title`, `last_updated: 2026-04-30`, `data_sources: [SEBI, AMFI, RBI]`
  (mix appropriately), `stale: false`, `confidence_factors: ["regulator-cited"]`.
- Body: 200–500 words, plain language, ₹ amounts, real fund codes where applicable
  (e.g., "Parag Parikh Flexi Cap — Direct Growth, AMFI Code 122639").
- A "Source" footer linking to the regulator URL.

Place into `data/wiki_india/equities/`, `data/wiki_india/mutual_funds/`,
`data/wiki_india/macro/`, `data/wiki_india/concepts/` (create the last directory).

Do not invent fund returns. Use ranges or "as per AMFI factsheet, see source." Tone:
"savvy older sibling explaining over chai." After writing, run `pytest tests/ -q` to
verify no test broke.
```

### 15.2 — Replace text_area with chat_input + streaming

```
In ui/app.py around lines 376–411, replace the `st.text_area` + `st.button("Ask India
Advisor")` pattern with:
1. `st.chat_input("Ask anything about Indian markets, SIP, ELSS, NPS, PPF…")`
2. Persist `st.session_state.india_messages` as a list of dicts
   `{"role": "user"|"assistant", "content": str, "sources": list[str], "confidence": float}`
3. Render via `st.chat_message(role)` in a for-loop above the input.
4. On a new user message, call `query_india()` or `beginner_answer_india()` with
   `stream=True` (use Google Gemini's `generate_content(..., stream=True)`) and pipe
   chunks via `st.write_stream()`.
5. On cold-start (empty messages), render 4 clickable suggestion chips in a 2×2 grid
   using `st.button` in `st.columns(2)`. Texts:
     - "I earn ₹40k/month. Where should I start investing?"
     - "Mujhe 5 saal mein ghar ke liye paise jodne hain"
     - "ELSS vs PPF vs NPS — which one for me?"
     - "Market gir gaya, SIP band karu?"
6. Always append the SEBI disclaimer to assistant content.

Do NOT touch the onboarding flow (lines 261–354) in this PR. Run `pytest -q` after.
```

### 15.3 — Build the deterministic calculator suite

```
Create `core/calculators.py` with these functions (pure Python, no LLM, no I/O):

  sip_future_value(monthly: float, annual_return_pct: float, years: int) -> dict
  sip_needed_for_goal(target: float, annual_return_pct: float, years: int) -> dict
  elss_tax_savings(annual_invested: float, tax_bracket_pct: float) -> dict
  step_up_sip(monthly: float, step_up_pct: float, annual_return_pct: float, years: int) -> dict
  emergency_fund_target(monthly_expenses: float, months: int = 6) -> dict
  lumpsum_vs_sip(amount: float, annual_return_pct: float, years: int) -> dict

Formula: SIP FV = P × [((1+r)^n − 1) / r] × (1+r), r = monthly rate, n = months.
ELSS: deduction min(annual_invested, 150000); tax_saved = deduction × (tax_bracket_pct/100).

Each function returns a dict with keys: total_invested, estimated_returns, future_value,
plus optional `monthly_series: list[float]` for charting.

Add `tests/test_calculators.py` with golden values:
  - sip_future_value(5000, 12, 10) → future_value ≈ 1_161_695 (within ±1%)
  - elss_tax_savings(200000, 30) → deduction == 150000, tax_saved == 45000
  - emergency_fund_target(40000, 6) → target_amount == 240000
  - sip_needed_for_goal(1_000_000, 12, 5) → monthly between 11_500 and 13_500

Then in `ui/app.py`, add a "🧮 Quick Tools" expander in the India tab below the chat
that exposes all six via Streamlit sliders. Numbers should update live without rerun.
```

### 15.4 — Wire the Trust Layer end-to-end

```
The Trust Layer (`core/trust.py`) defines `record_wiki_version()` but it's never
called. Wire it:

1. In `core/wiki.py`: change `_write_wiki_file(path, content, engine=None)` callers
   inside `ingest_to_wiki()` (lines ~271, 298, 317) to pass the engine. Add an
   `engine` parameter to `ingest_to_wiki()` defaulting to None; thread it from
   `agents/analysis_agent.py`.
2. In `core/wiki_india.py`: add `engine` parameter to `_iwrite()` (around line 81)
   and call `record_wiki_version(engine, page_path, content, sources, triggered_by)`
   inside it. Thread engine from `ingest_india()` callers in `agents/analysis_agent.py`.
3. In `agents/analysis_agent.py`: after `engine = init_db(settings.DATABASE_URL)`,
   pass `engine=engine` to every `ingest_to_wiki(...)` and `ingest_india(...)` call.
4. Add a test `tests/test_trust_wired.py` that runs an in-memory `:memory:` SQLite,
   triggers one wiki write through `ingest_india()` (mock Gemini), and asserts at
   least one row exists in `knowledge_versions`.
5. Update `ui/app.py` "Sources & History" tab to show a real timeline of last 20
   `KnowledgeVersion` rows (path, timestamp, word count, top 2 sources).

Run `pytest -q` and `mypy core agents ui` before finishing.
```

### 15.5 — Replace LLM routing with embedding-similarity routing (deterministic, free)

```
Goal: keep the 2-stage grounded pattern (route → load pages → synthesise) but replace
the LLM routing call with deterministic embedding similarity. The synthesis call stays
unchanged — it still receives full page contents loaded from disk between routing and
synthesis. (We previously considered combining routing + synthesis into one call;
that was wrong because it would force the model to write the answer without ever
seeing page contents.)

Steps:
1. Add `sentence-transformers==2.7.0` to requirements.txt. Pin the model to
   `sentence-transformers/all-MiniLM-L6-v2` (~23MB, CPU-only, free).
2. Create `core/retrieval.py` with:

      from sentence_transformers import SentenceTransformer
      import numpy as np
      from pathlib import Path

      _MODEL: SentenceTransformer | None = None
      _EMBED_CACHE: dict[str, np.ndarray] = {}  # filename -> vector

      def _model() -> SentenceTransformer:
          global _MODEL
          if _MODEL is None:
              _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
          return _MODEL

      def build_index(wiki_dir: Path, cache_path: Path) -> None:
          # Walk wiki_dir, embed each page (title + first 500 chars), save to .npy

      def route_pages(question: str, wiki: str, k: int = 5) -> list[str]:
          # Cosine-similarity over cached embeddings, return top-k filenames

3. In `core/wiki_india.py:879` (the routing Gemini call inside `query_india` fall-through
   path), replace with:
       consulted = route_pages(question, wiki="india", k=5)
   Same in `core/wiki.py:458` for `query_wiki()`.

4. Wire embedding rebuild into `_iwrite()` and `_write_wiki_file()` — when a page is
   written, mark its embedding stale and re-embed on the next routing call (lazy).

5. Add `tests/test_retrieval.py` with golden questions:
   - "what is SIP" → top-5 includes `concepts/sip.md`
   - "ELSS vs PPF" → top-5 includes both `elss_vs_ppf_vs_nps.md` and `tax_india.md`
   - "RBI repo rate" → top-5 includes `macro/rbi_rates.md`

6. The synthesis call (`call_gemini(answer_prompt)` further down in `query_india`) is
   UNCHANGED — it still receives the full content of the routed pages and grounds the
   answer in them. This is intentional: routing is similarity, synthesis is reasoning.

Run `pytest -q` after. First test run will download the 23MB model — that's expected.
```

### 15.6 — Onboarding wizard rebuild

```
Replace the form-based onboarding in `ui/app.py:261–354` with a conversational wizard.

Behaviour:
- When `UserProfile` row is missing, hide the tabs entirely. Render only the wizard.
- Use `st.session_state.onboarding_step` (0..4).
- Step 0: "Hi, I'm Paisa Pal. Aapka naam?" → `st.text_input`
- Step 1: "How much do you earn per month?" → `st.radio` over income brackets
- Step 2: "How much can you invest monthly?" → `st.radio` over SIP brackets
- Step 3: "Comfort with risk?" → `st.radio` with plain-language descriptions
- Step 4: "Main goal?" → `st.selectbox`: Tax-saving, House down-payment, Wedding,
  Child education, Retirement, Just learning
- Show `st.progress((step+1)/5)` and "Step {step+1} of 5".
- Render previous answers as `st.chat_message("assistant")` summary above current step.
- After step 4, build an "Investment DNA" card: a styled `st.container` with a colored
  border, the user's name, "Conservative starter / Balanced builder / Bold grower",
  monthly SIP budget, primary goal, time horizon. Add a "Let's go →" button that calls
  `db_save_user_profile(...)` and triggers `st.rerun()`.

Do NOT touch chat (1.2) or calculators (1.5) in this PR. Add `tests/test_onboarding.py`
with a happy-path test using `streamlit.testing.v1.AppTest`.
```

### 15.7 — Fix the Hindi-and-profile dropout on the beginner path

```
Bug: ui/app.py:393 calls `beginner_answer_india(india_q.strip())` with no `hindi=`
or profile. Hindi toggle is silently lost on the most common (beginner) path.

Fix:
1. In `core/wiki_india.py:987` (`beginner_answer_india`), add parameters
   `profile: dict | None = None, hindi: bool = False`. Inject `_profile_block(profile)`
   into the prompt the same way `short_term_india_answer` does.
   When `hindi=True`, append "\n\nPlease respond entirely in Hindi (Devanagari script)."
2. In `ui/app.py:393`, change to:
     ans, sources = asyncio.run(
         beginner_answer_india(india_q.strip(), profile=profile_dict, hindi=hindi_mode)
     )
3. Add a test `tests/test_beginner_hindi.py` mocking Gemini that asserts both the
   profile block and the Hindi instruction reach the prompt.
4. Run `pytest -q` and `mypy core agents ui`.
```

### 15.8 — Build the demo cache (rate-limit insurance)

```
Create `scripts/build_demo_cache.py`:
- Define DEMO_QUESTIONS = [4 strings — see PROJECT_TODO_MASTER.md §1.7].
- For each, call `query_india(q, profile=DEMO_PROFILE, hindi=False)` (and
  `language="hinglish"` for the Hinglish ones).
- Save the answer + sources + confidence to `data/demo_cache/{slug(q)}.md` with
  YAML frontmatter.
- Print "✅ Demo cache built: N answers." Idempotent — skip if file exists, unless
  --refresh.

In `ui/app.py`, before the Gemini call in the chat handler, add:
    if os.getenv("DEMO_REPLAY_MODE") == "1":
        cached = _load_demo_cache(question)
        if cached:
            for chunk in _stream_chunks(cached["answer"]):
                yield chunk
            return cached["sources"], cached["confidence"]

Add a small "Demo mode" badge in the sidebar when DEMO_REPLAY_MODE=1. Include a
README section explaining when to use it.
```

### 15.9 — README rewrite (product-audience)

```
Rewrite README.md from a developer-audience tech doc to a product-audience pitch.
Open with the problem (3 barriers: complexity, trust, advice gap) and the persona
(Priya). Then a 90-second GIF (placeholder — capture later). Then the wedge ("the
only product that does grounding + Hinglish + personalisation + education"). Then
"How it works" in 3 sentences with a single architecture diagram (ASCII or Mermaid).
Then "Quick start" — single command: `python scripts/seed_india_demo.py && python run.py`.
Then "For developers" — the existing tech section, demoted. Then disclaimer.

Constraints:
- Lead with user value, not architecture.
- Replace "agentic" / "Karpathy pattern" / "RAG" jargon with plain English.
- Update test count to actual `grep "^def test_" tests/*.py | wc -l` value.
- Keep the existing tech-stack table — that's a pro signal.
- Length: under 200 lines.
```

### 15.10 — Streamlit Cloud deploy (free, public URL)

```
Deploy to Streamlit Community Cloud:
1. Push current branch to GitHub (already on `main`).
2. Add `.streamlit/config.toml` with theme matching the India palette
   (primaryColor #FF9933, backgroundColor #FFFFFF, secondaryBackgroundColor #138808).
3. Create `.streamlit/secrets.toml.example` documenting required secrets
   (GEMINI_API_KEY). DO NOT commit the real `secrets.toml`. Add to `.gitignore`.
4. At https://streamlit.io/cloud, create a new app pointing at `ui/app.py` on `main`.
5. Add the GEMINI_API_KEY secret in the Streamlit dashboard.
6. Note: agents (`main.py`) will NOT run on Streamlit Cloud. The cloud demo must use
   the seeded wiki only — no live ingest. Update `ui/app.py` to detect cloud env
   (`os.getenv("STREAMLIT_SERVER_HEADLESS") == "1"`) and show a "Pre-seeded data
   demo — fully live with `python run.py` locally" banner.
7. Add the public URL to the README and pitch deck slide 4.
```

### 15.11 — Behavioural nudge engine

```
Create `core/nudges.py` with:

  generate_nudges(profile: dict, recent_questions: list[str], market: dict) -> list[dict]

Returns up to 3 nudges, each `{"icon": str, "title": str, "body": str, "priority": int}`.

Rules (deterministic, no LLM):
- If profile.goal == "tax_saving" AND month in (1, 2, 3): "₹{remaining} more in ELSS
  before March 31 saves you ~₹{tax_saved} at your bracket."
- If market["nifty_change_pct"] < -3: "Markets dipped 3%+. SIPs benefit from dips —
  you buy more units at lower prices. Stay the course."
- If any recent question contains ("stop sip", "band karu", "sell", "gir gaya"):
  "Before you stop: ₹5,000/mo for 10 years compounds to ~₹11.6L. Pausing 12 months
  costs you ~₹1.4L in long-run growth."
- If profile.created_at within last 7 days: rotate through 7 daily tips
  (sip_basics, why_index, emergency_fund, term_insurance, no_individual_stocks,
   compounding_magic, ignore_finfluencers).

Render nudges as a "Daily Tip" `st.container` above the chat. Add `tests/test_nudges.py`.
```

### 15.12 — Pitch deck draft (one prompt to scaffold)

```
Generate `docs/pitch_deck/draft.md` with 10 slides, each as an H2. For each slide,
include: (a) one-line title, (b) speaker notes (3 sentences), (c) 1–2 visuals/charts
to commission. Slides:

  1. Title — Niveshak AI / Paisa Pal
  2. The Problem — three barriers + Priya
  3. The Insight — the 4-corner wedge
  4. Demo (live or 90s GIF)
  5. How It Works — architecture
  6. Why Now — 5 enabling shifts
  7. Market — TAM, beachhead, adjacent expansion
  8. Right-to-Win & Moat
  9. Monetisation — y1/y2/y3
  10. Ask & Roadmap

Append an "Appendix" section with: cost economics per query (assume Gemini Flash:
$0.075/M input, $0.30/M output, average per-query cost across the new pipeline:
intent ~$0.0001 + synthesis ~$0.0006 + reflection ~$0.0002 + optional regen ~$0.0006
+ optional ReAct iters ~$0.0008 → median $0.0009/query, p95 $0.0023/query, even with
the quality-first pipeline it stays under $1 per 1000 queries), competitor matrix
(Zerodha / Groww / ET Money / INDmoney / ChatGPT direct × 4 wedge dimensions),
regulatory analysis (SEBI educational vs advisory line — cite IA Regulations 2013 §3).

Do not invent specific user counts or revenue projections. Use ranges.
```

### 15.13 — Reflection critic on every Gemini answer

```
Create `core/reflection.py` with:

  async def reflect(
      question: str,
      profile: dict | None,
      source_pages: dict[str, str],  # filename -> content
      candidate_answer: str,
      *,
      mode: Literal["india", "us"] = "india",
  ) -> ReflectionResult

  ReflectionResult is a dict:
    {
      "verdict": "ACCEPT" | "REGENERATE",
      "checks": {
        "grounded": "PASS" | "WARN" | "FAIL",
        "scoped": ...,
        "disclaimed": ...,
        "tone": ...,
        "consistent": ...,
        "profile_fit": ...,
      },
      "reasons": list[str],   # one short string per non-PASS check
      "regenerate_guidance": str,  # empty if verdict == ACCEPT
      "raw": str,             # full critic response, for the audit log
    }

Critic prompt (strict structured output — see §1.6 for the rubric). Use Gemini Flash
for the critic call; same model as synthesis.

Wire into `core/wiki_india.py`:
  - At the end of `short_term_india_answer`, `intermediate_india_answer`,
    `long_term_india_answer`, `beginner_answer_india`, and the fall-through `query_india`,
    after the synthesis call but before the insight is filed:
       result = await reflect(question, profile, page_contents, answer, mode="india")
       if result["verdict"] == "REGENERATE":
           answer = await call_gemini(synthesis_prompt + "\n\nCRITIC FEEDBACK:\n" + result["regenerate_guidance"])
       insight_frontmatter["reflection"] = result["checks"]
       insight_frontmatter["reflection_raw"] = result["raw"]

  - Mirror in `core/wiki.py` for the US flow.

UI:
  - In `ui/app.py`, render a small badge next to the existing confidence pill:
       🛡️ Fact-checked      (verdict == ACCEPT, all checks PASS)
       🟡 Refined            (regen fired and now PASSes)
       ⚠️ Use with care     (regen fired and still has WARN)
  - Add an "View self-check" expander showing the 6 checks with PASS/WARN/FAIL.

Tests (`tests/test_reflection.py`):
  - Mock Gemini to return rubric-shaped output.
  - Assert that an answer with an ungrounded numeric claim triggers REGENERATE.
  - Assert that a passing answer's checks all show PASS in the insight frontmatter.
  - Assert hard cap: regen fires at most once per query.
  - Run with `pytest tests/test_reflection.py -q`.
```

### 15.14 — Intent classifier + ReAct loop for multi-step queries

```
Create `core/intent.py`:

  async def classify_intent(question: str, profile: dict | None) -> IntentResult

  IntentResult: {"intent": Literal["factual_simple","comparative","calculator",
                                    "emotional","eligibility","multi_step"],
                 "reasoning": str}

  Prompt: ~200 tokens. Output strictly:
       INTENT: <one_value>
       REASONING: <≤ 1 line>
  Parse defensively; on parse failure default to "factual_simple".

Create `core/react.py`:

  Action = TypedDict("Action", {
      "type": Literal["read_page", "compute", "consult_profile", "final_answer"],
      "args": dict,
  })

  async def run_react(
      question: str,
      profile: dict | None,
      top_k_pages: list[str],     # from retrieval.route_pages
      max_iterations: int = 4,
  ) -> tuple[str, list[str], list[dict]]:
      # Returns: (final_answer, sources_consulted, trace)

  Trace is a list of {"thought": str, "action": Action, "observation": str | None}.

  Action dispatch:
    - read_page(filename): load from data/wiki_india/<filename> or data/wiki/<filename>;
      observation is the first 2000 chars of the page.
    - compute(name, kwargs): dispatch to core.calculators.<name>(**kwargs);
      observation is repr(result).
    - consult_profile(field): observation is profile.get(field) or "(not set)".
    - final_answer(text, sources): terminates the loop.

  If iteration cap reached without final_answer, do one synthesis call over the
  scratchpad to produce a forced final answer.

Wire into `core/wiki_india.py:query_india`:
  intent = await classify_intent(question, profile)
  match intent["intent"]:
      case "factual_simple" | "emotional":
          # existing horizon path → reflection
      case "calculator":
          # render calculator card; optional 1-call explanation
      case "comparative" | "multi_step" | "eligibility":
          top_k = route_pages(question, wiki="india", k=5)
          answer, sources, trace = await run_react(question, profile, top_k)
          reflection_result = await reflect(question, profile, ...)
          # save trace into insight frontmatter

Mirror in `core/wiki.py:query_wiki` for US.

UI:
  - "🧠 Reasoning trace" expander below answer when trace is non-empty.
  - Each iteration rendered as: "**Thought:** ... | **Action:** read_page('rbi_rates.md') | **Observation:** ..."

Tests (`tests/test_intent.py`, `tests/test_react.py`):
  - Mock Gemini to return scripted thought/action sequences.
  - Assert ReAct terminates within max_iterations on a comparative question.
  - Assert the trace serialises into insight frontmatter cleanly.
  - Assert action dispatch rejects unknown action types.
  - Run with `pytest tests/test_intent.py tests/test_react.py -q`.
```

### 15.15 — Refactor `wiki_ingest.py` 8 processors into one parameterised function

```
Goal: collapse the 8 near-identical `process_*` functions in core/wiki_ingest.py
into one parameterised function driven by a registry. Same behaviour, less code,
and reflection critic (§15.13) applied uniformly to all processors.

Steps:
1. Define `ProcessorSpec`:

      @dataclass
      class ProcessorSpec:
          source_dir: str                # "sec", "fred", "alpha_vantage", ...
          target_wiki_dir: str           # "data/wiki/stocks", "data/wiki/macro", ...
          target_section_marker: str     # "## SEC Filings", "## FRED Macro", ...
          extraction_prompt: str         # the per-processor Gemini prompt template
          required_fields: list[str]     # validate raw JSON before calling Gemini

2. Build PROCESSOR_REGISTRY: dict[str, ProcessorSpec] with the 8 entries currently
   inlined (sec, fred, reddit, alpha_vantage, finnhub, earnings, sentiment,
   company_facts).

3. Single function:

      async def process_raw_file(path: Path, spec: ProcessorSpec) -> None:
          raw = json.loads(path.read_text())
          if not all(k in raw for k in spec.required_fields):
              return  # skip malformed
          prompt = spec.extraction_prompt.format(**raw)
          extracted = await call_gemini(prompt)
          critique = await reflect(question="(ingest)", profile=None,
                                   source_pages={path.name: json.dumps(raw)},
                                   candidate_answer=extracted, mode="us")
          if critique["verdict"] == "REGENERATE":
              extracted = await call_gemini(prompt + "\n\nCRITIC: " + critique["regenerate_guidance"])
          _merge_section(spec.target_wiki_dir, spec.target_section_marker, extracted)

4. process_all_new_raw_files() loops over PROCESSOR_REGISTRY entries and dispatches
   to process_raw_file. No behaviour change beyond reflection-on-ingest.

5. Delete the 8 standalone functions (process_sec_filing, process_macro_data, etc.)
   after confirming all callers route through process_raw_file.

6. Update tests/test_wiki_ingest.py:
   - Existing test cases stay; add a parametrised test that runs the same fixture
     through all 8 processor specs.
   - Add a test asserting reflection fires on a fixture with an ungrounded numeric
     claim.

Run `pytest -q && ruff check . && mypy core agents ui` before finishing.
```

### 15.16 — US wiki seed expansion (8 new pages on top of existing 5)

```
Add 8 new markdown files to data/wiki/ to make the Global Markets tab demo-ready.

data/wiki/stocks/ (5 new on top of existing AAPL, GOOGL, JNJ, MSFT, NVDA):
  - AMZN.md, META.md, TSLA.md, BRK_B.md, JPM.md
  - Frontmatter: title, last_updated: 2026-04-30, data_sources: [SEC, FRED],
    stale: false, confidence_factors: ["regulator-cited"]
  - Body: 200–400 words. Sections: Business overview / Financial highlights from
    most recent 10-K (cite SEC EDGAR URL) / Risk factors (1-2 lines) / Source.
  - Do NOT invent share prices or percentages; cite from SEC filings or use ranges.

data/wiki/concepts/ (3 new on top of existing finance_basics.md):
  - 401k_basics.md       — what it is, contribution limits FY2025 ($23,500 employee +
                            $7,500 catch-up), employer match basics, vesting, source IRS Pub 560.
  - etf_vs_mutual_fund_us.md — structural differences, intraday trading, expense ratios,
                                tax efficiency, source SEC investor.gov.
  - roth_vs_traditional_ira.md — pre-tax vs post-tax, income limits FY2025
                                  ($7,000 contribution / $1,000 catch-up), withdrawal rules,
                                  source IRS Pub 590-A.

Tone: educational, beginner-friendly, US-context (in $, not ₹). Same structure as
the India seed pages so the engine treats them identically.

Generation approach:
  - Create scripts/seed_us_wiki.py that posts the 8 prompts to Gemini, hand-edit the
    drafts for factual accuracy (especially the 2025 IRS limits), commit final
    markdown to the repo so it ships with `git clone`.

After commit, run scripts/build_demo_cache.py with one US question (e.g., "What's a
Roth IRA?") so beat 6 of the demo can replay if Gemini rate-limits.
```

---

## 16. Execution Order (the only ordering that matters)

```
Day 1    : P0 (all 10 bug fixes — 3 hours total)
Day 2–3  : Pre-seed India wiki 25 pages (1.1 India side) + tab reorder (1.3) +
           onboarding wizard (1.4)
Day 4    : Chat input + streaming (1.2) + calculators (1.5)
Day 5    : Embedding-based routing (1.6b) + Reflection critic (1.6) +
           Trust wiring (P0 0.4/0.5 confirmed) + confidence + fact-checked badges (P2 2.3)
Day 6    : Intent classifier + ReAct loop (1.9) + Reasoning-trace UI expander
Day 7    : US wiki seed expansion (1.1 US side, 8 pages) + refactor wiki_ingest (1.10)
Day 8    : Demo cache covering all 6 beats incl. ReAct (1.7) + metric cards (1.8) +
           Hinglish radio (P2 2.1)
Day 9    : CSS polish (P2 2.2) + nudges (P2 2.4) + FAQ system (P2 2.5) + run.py (P2 2.6)
Day 10   : README rewrite + Streamlit Cloud deploy + GIF + LinkedIn post
Day 11–12: Pitch deck (15.12) + dry-run × 5 + final demo checklist (§14)
```

**If you have less time (4-day push):**
  Day 1 (P0) + Day 2 (India seed + tabs + onboarding) + Day 4 (chat + calculators) +
  Day 5 morning (reflection critic only — skip embedding routing and ReAct) + Day 9
  (demo cache + dry-runs).

  This skips ReAct and embedding routing — your comparative questions will be weaker
  but the demo is still credible. Reflection critic is the non-negotiable trust layer
  even in the compressed plan.

---

## 17. What NOT to change

- `core/queues.py` — simple `asyncio.Queue`, fine.
- `core/settings.py` — clean single source of truth.
- `core/sec_client.py`, `core/alpha_vantage_client.py`, `core/finnhub_client.py` — fine.
- `main.py` — simple and correct.
- The decision to use markdown wiki over a vector DB — keep it; it's a pitch asset.
- The 3-agent split — keep it.
- The horizon-aware advisor functions in `wiki_india.py` — they're a pitch asset.
- Existing tests — do not break; only add.
- `docker-compose.yml`, `Dockerfile` — leave until Streamlit Cloud demo is up.
- `legacy/` directory — leave; archived for reference.

**Locked architectural decisions for this revision (do NOT revisit before the demo):**

- **Gemini-only.** Do not introduce Groq, Llama, Claude, or any multi-LLM abstraction. The demo, the pitch, and the economics are built around Gemini Flash. Hindi/Hinglish quality and a single mental model trump vendor diversification.
- **US codepath stays live and visible.** Both wikis run, both tabs render, both flow through the same intent → retrieval → ReAct → reflection pipeline. The "Globally extensible" beat is non-negotiable for the pitch.
- **Routing call → embedding similarity, not combined-prompt.** The 2-stage grounded pattern (route → load page contents → synthesise) is load-bearing. Do not collapse into a single LLM call.
- **More LLM calls per query, not fewer.** The reasoning hot path is intent → synthesis → reflection (→ optional regen → optional ReAct). Cost is controlled at the cache layer, not the reasoning layer.
- **Deterministic staleness detection stays.** Even after splitting `lint_wiki()`, the Python staleness check runs every cycle and feeds the confidence rubric.

---

## 18. Single-line summary

> Pre-seed both wikis, ship a chat UI with streaming and a deterministic calculator,
> wire the Trust Layer, add the Reflection critic and ReAct loop on every Gemini
> answer so hallucination is auditable not invisible, frame everything around Priya's
> 5-minute story — and you have a demo that out-pitches every "AI advisor" wrapper
> a VC has seen this quarter.
