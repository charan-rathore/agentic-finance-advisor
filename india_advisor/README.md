# Finsight India

**Your AI-powered investment companion for Indian retail investors.**

Finsight India is a standalone, production-ready application that provides personalized investment guidance grounded in SEBI, AMFI, and RBI data.

## Features

- **Smart Onboarding**: Income-aware SIP recommendations (never suggests investing more than you earn)
- **AI-Powered Q&A**: Ask anything about SIP, ELSS, PPF, NPS, mutual funds, and tax saving
- **Hindi Support**: Toggle to get responses in Devanagari script
- **Live Market Data**: Real-time NSE stock prices
- **Instant Calculators**: SIP growth, ELSS tax savings, goal planning
- **FAQ Fast-Path**: Common questions answered instantly without LLM calls
- **Confidence Scoring**: Every answer shows how well-grounded it is

## Quick Start

```bash
# From the project root
cd starter-project

# Install dependencies
pip install -r requirements.txt

# Run the India Advisor
streamlit run india_advisor/app.py
```

Opens at http://localhost:8501

## How It Works

1. **Onboarding**: Answer 5 quick questions to set up your investor profile
2. **Get Insights**: Ask questions in English or Hinglish
3. **Use Calculators**: Plan your SIP, estimate tax savings, set goals
4. **Track Markets**: View live NSE prices for top stocks

## Tech Stack

- **Frontend**: Streamlit with custom CSS
- **AI**: Google Gemini 2.5 Flash (free tier)
- **Data**: yfinance (NSE), AMFI API (mutual funds), RBI endpoints
- **Database**: SQLite with SQLAlchemy ORM
- **Knowledge Base**: LLM-maintained markdown wiki

## Key Differentiators

1. **Income-Aware**: SIP options are filtered based on your income - we never suggest investing more than you can afford
2. **Grounded**: Every answer cites SEBI, AMFI, or RBI sources
3. **Transparent**: Confidence scores show how well-supported each answer is
4. **Free**: Runs entirely on free-tier APIs

## Disclaimer

Finsight India is for educational purposes only and does not constitute financial advice. Always consult a SEBI-registered investment advisor before making investment decisions.

---

Built with care for the next 100 million Indian investors.
