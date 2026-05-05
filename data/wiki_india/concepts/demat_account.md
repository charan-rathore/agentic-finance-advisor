---
page_type: concept
market: india
topic: account_setup
language: en
last_updated: 2026-04-30
source: curated_seed
data_sources: [SEBI, NSDL, CDSL]
stale: false
confidence_factors: ["regulator-cited"]
version: 1
---

# Demat Account: What It Is and When You Actually Need One

A Demat account holds your shares and ETFs in dematerialised (electronic) form,
just as your bank account holds rupees. Without a Demat account you cannot buy
or sell stocks listed on NSE or BSE, but you do **not** need one to invest in
mutual funds.

## What sits where

| Asset | Where held |
|---|---|
| Listed stocks | Demat account |
| ETFs (including index ETFs) | Demat account |
| Mutual fund units | Statement of Account at the RTA (CAMS / KFin), no Demat needed |
| Sovereign Gold Bonds | Demat account or RBI ledger |
| Government bonds via RBI Retail Direct | RBI Retail Direct, no Demat needed |

If your only goal is SIP into mutual funds, **you do not need a Demat account**.
Platforms like Coin, Groww, Kuvera, MF Central, or AMC websites work fine.

## Three accounts, one stack

Trading on Indian exchanges requires three linked accounts:

1. **Bank account.** Source and destination of funds
2. **Trading account.** Opened with a SEBI-registered broker (Zerodha, Upstox,
   Groww Stocks, ICICI Direct, HDFC Securities, etc.)
3. **Demat account.** Opened with a Depository Participant linked to either
   **NSDL** or **CDSL**, the two SEBI-regulated depositories

In practice, the broker bundles the trading and Demat account opening together.

## Costs to know about

| Charge | Range |
|---|---|
| Account opening | Often INR 0 with discount brokers, INR 200 to 500 with bank brokers |
| Annual Maintenance Charge (AMC) | INR 0 to 750, varies by broker |
| Brokerage on equity delivery | INR 0 (Zerodha, Groww) to 0.5 percent (full-service) |
| STT, exchange fees, GST, SEBI fee, stamp duty | Statutory, same across brokers |
| DP charges on sell trades | About INR 13 to 20 per scrip per day, charged by the depository |

## What SEBI rules guarantee you

* Two-factor authentication on every login (TOTP, biometrics, or device-bound
  PIN)
* T+1 settlement on equity trades
* Direct Pay-out of securities to your Demat account, not pooled at the broker
  (since 2024, mandatory)
* Right to nominate up to three nominees per Demat account

## Account safety hygiene

* Never share your TOTP or login PIN with anyone
* Verify that your contract notes match your console statements daily during
  active trading periods
* Pledge or unpledge securities yourself; do not give a Power of Attorney to
  the broker for any operational use
* Reconcile holdings against your CDSL or NSDL CAS statement (sent by email
  monthly, free)

## Source

* SEBI investor charter for brokers: https://www.sebi.gov.in/legal/circulars/
* NSDL: https://nsdl.co.in/
* CDSL: https://www.cdslindia.com/
