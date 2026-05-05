"""
scripts/build_demo_cache.py

Pre-rendered answers for the demo questions, so a public demo never depends on
Gemini being reachable in the moment.

Why static, not live:
* The Gemini free tier is rate-limited. A meetup demo over hotel WiFi after a
  peer demoed should not be the moment we discover that
* Demo cache content is deliberately illustrative, hand-written, and
  short-by-design so the cache is auditable and won't drift with prompt
  engineering changes

The UI checks data/demo_cache/<slug>.md when the env var DEMO_REPLAY_MODE=1.
This script writes those files. Idempotent.

    python scripts/build_demo_cache.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "demo_cache"


def _slug(question: str) -> str:
    s = question.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")[:60]


DEMO_ANSWERS: list[tuple[str, list[str], str]] = [
    (
        "I earn INR 40k a month, where should I start investing?",
        [
            "data/wiki_india/concepts/sip.md",
            "data/wiki_india/concepts/emergency_fund.md",
            "data/wiki_india/concepts/direct_vs_regular.md",
        ],
        """A clean four-step starter framework on INR 40,000 monthly take-home:

1. **Emergency fund first.** Build INR 1.2 to 1.8 lakh (3 to 6 months of essential
   expenses) in a liquid mutual fund or sweep-in FD. Until this is funded, do
   not start any equity SIP.

2. **Insurance.** A pure term life cover and a family health policy. Without
   these, one bad year derails everything else.

3. **Open a Direct plan mutual fund account.** Free options: MF Central, Coin,
   Groww, Kuvera, AMC websites. You do not need a Demat for SIPs.

4. **Start two SIPs.** A reasonable split:
   - INR 5,000 in a Nifty 50 index fund (HDFC Index Nifty 50 Direct Growth or
     UTI Nifty 50 Direct Growth)
   - INR 2,000 to 3,000 in an ELSS fund if you file under the old tax regime
     (Mirae Asset ELSS Tax Saver Direct Growth or Axis ELSS Direct Growth)

Total INR 7,000 to 8,000, about 18 to 20 percent of your take-home, which is
exactly the saving rate India's personal-finance literature recommends.

*Educational only. Verify with a SEBI-registered investment adviser.*
""",
    ),
    (
        "ELSS vs PPF, which one for me?",
        [
            "data/wiki_india/concepts/elss_vs_ppf_vs_nps.md",
            "data/wiki_india/basics/tax_india.md",
        ],
        """Both qualify for Section 80C in the **old tax regime** (limit INR 1.5 lakh
per year). They serve very different purposes.

| Attribute | ELSS | PPF |
|---|---|---|
| Asset class | Equity | Sovereign |
| Lock-in | 3 years per SIP instalment | 15 years |
| Indicative return | 10 to 14 percent CAGR (historical) | 7.1 percent (Q1 FY26) |
| Maturity tax | 12.5 percent on LTCG above INR 1.25 lakh | Tax-free (EEE) |

**The honest answer is "both", in different proportions.**

- If your horizon is 5 plus years and you can stomach equity drawdowns, ELSS
  has historically delivered the highest post-tax return in the 80C bucket
- PPF is the safe, sovereign sleeve that everyone should also have, especially
  for retirement and child-education goals

A common split for a 30 percent bracket investor: PPF INR 50k to 70k per year
plus ELSS the rest of the 80C limit.

*Important.* The new tax regime (default since FY 2024) does not allow 80C.
Compare both regimes before investing primarily for tax savings.

*Educational only.*
""",
    ),
    (
        "Mujhe 5 saal mein ghar ke liye paise jodne hain",
        [
            "data/wiki_india/concepts/sip.md",
            "data/wiki_india/concepts/sip_vs_lumpsum.md",
            "data/wiki_india/concepts/market_cap_categories.md",
        ],
        """5 saal ka horizon equity ke liye **borderline** hai. Equity asset class ko
apni statistical edge dikhane ke liye 7 plus saal chahiye. 5 saal mein agar
market crash ho gaya last year, toh aap goal se peeche reh sakte hain.

Suggested approach for a house down-payment in 5 years:

1. **Aggressive hybrid** ya balanced advantage fund (60 to 70 percent equity,
   rest debt). Drawdowns shorter aur shallow hote hain pure equity ke
   compared mein.
2. **Yearly de-risking.** Saal 4 mein gradually move to debt funds; saal 5
   mein 80 percent debt mein hona chahiye. Down payment ke 12 mahine pehle,
   sab kuch liquid fund ya FD mein.
3. **SIP amount?** Agar target INR 20 lakh hai 5 saal mein, 10 percent
   blended return ke saath, monthly SIP roughly INR 25,000 hoga. Aap is amount
   ko goal calculator card mein dekh sakte hain.
4. **What NOT to do.** Pure small-cap ya sectoral funds ka use 5-saal goal ke
   liye mat karo. Volatility itni hai ki aap 12 mahine pehle 30 percent loss
   mein ho sakte ho.

*Educational only. Verify with a SEBI-registered investment adviser before
acting on a specific fund recommendation.*
""",
    ),
    (
        "Market gir gaya, SIP band karu?",
        [
            "data/wiki_india/faq/should_i_stop_sip.md",
            "data/wiki_india/concepts/sip.md",
        ],
        """**Bilkul mat karo.** SIP ka asli kaam tabhi hota hai jab market gira hua
hai. Aapka fixed monthly amount tab zyada units kharidta hai jab NAV kam hai.
Yeh mathematics aapke favour mein hai, agar aap discipline rakho.

Numbers:

- INR 5,000 monthly SIP, 12 percent gross return, 10 saal: roughly **INR 11.6 lakh**
  final corpus
- 12 mahine ki pause beech mein: long-run growth se roughly **INR 1 to 2 lakh
  ka loss**

Past crashes mein kya hua:

- 2008-09 GFC ke through SIP chalane wale, 5 saal baad bahut aage the un logon
  se jinhone 6 to 12 mahine pause kiya
- March 2020 covid crash mein bhi yahi pattern. Pause karne wale fastest
  recovery miss kar gaye

Pause genuinely justified hota hai sirf ek case mein: aapki **job chali gayi**
aur aapko emergency fund preserve karna hai. Tab bhi: existing units sell mat
karo. Sirf naye contributions pause karo, aur job lagne ke baad turant resume.

Behavioural rule: agar 30 to 40 percent paper drawdown se panic ho raha hai,
toh aapka equity allocation aapki risk tolerance se zyada hai. Drawdown
khatam hone ke baad **rebalance** karna chahiye, drawdown ke beech mein nahi.

*Educational only.*
""",
    ),
]


def main(refresh: bool = False) -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    for question, sources, body in DEMO_ANSWERS:
        slug = _slug(question)
        path = CACHE_DIR / f"{slug}.md"
        if path.exists() and not refresh:
            skipped += 1
            continue
        sources_yaml = "\n".join(f"  - {s}" for s in sources)
        content = f"""---
question: {question!r}
slug: {slug}
sources:
{sources_yaml}
confidence: 0.85
fast_path: demo_cache
---

{body.strip()}
"""
        path.write_text(content, encoding="utf-8")
        written += 1

    print(f"Demo cache: {written} written, {skipped} skipped (already present).")
    print(f"Location: {CACHE_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    refresh = "--refresh" in sys.argv
    raise SystemExit(main(refresh=refresh))
