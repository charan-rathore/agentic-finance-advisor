"""
core/company_intelligence.py

Company-specific intelligence for better risk analysis and cross-references.
This provides context that helps the LLM generate more accurate, sophisticated wiki pages.
"""

# Company-specific risk profiles and intelligent cross-references
COMPANY_INTELLIGENCE = {
    "NVDA": {
        "key_risks": [
            "AI bubble/valuation concerns",
            "China export restrictions", 
            "Cryptocurrency mining demand volatility",
            "Competition from AMD, Intel, custom chips",
            "Data center capex cycle dependency"
        ],
        "cross_references": [
            "[[AI Chip Wars]]",
            "[[Semiconductor Cycle]]", 
            "[[Data Center Investment]]",
            "[[Geopolitical Tech Risk]]",
            "[[Valuation Multiples]]"
        ],
        "sector": "Semiconductors",
        "defensive_rating": "Growth/Cyclical"
    },
    
    "AAPL": {
        "key_risks": [
            "iPhone demand saturation",
            "China market regulatory pressure",
            "Services growth deceleration", 
            "Supply chain concentration",
            "EU regulatory compliance costs"
        ],
        "cross_references": [
            "[[Consumer Electronics Cycle]]",
            "[[China Market Risk]]",
            "[[Services Transition]]",
            "[[Supply Chain Resilience]]",
            "[[Regulatory Compliance]]"
        ],
        "sector": "Consumer Technology",
        "defensive_rating": "Moderate Defensive"
    },
    
    "JNJ": {
        "key_risks": [
            "Talc litigation liability",
            "Patent cliff on key drugs",
            "Biosimilar competition",
            "FDA approval delays",
            "Healthcare pricing pressure"
        ],
        "cross_references": [
            "[[Healthcare Litigation]]",
            "[[Patent Cliff Risk]]", 
            "[[Biosimilar Competition]]",
            "[[Dividend Aristocrats]]",
            "[[Defensive Healthcare]]"
        ],
        "sector": "Healthcare",
        "defensive_rating": "Highly Defensive"
    },
    
    "GOOGL": {
        "key_risks": [
            "Antitrust regulatory action",
            "AI search disruption threat",
            "Digital advertising cyclicality",
            "Cloud competition from AWS/Azure",
            "Privacy regulation compliance"
        ],
        "cross_references": [
            "[[Big Tech Antitrust]]",
            "[[AI Search Revolution]]",
            "[[Digital Advertising]]",
            "[[Cloud Wars]]",
            "[[Privacy Regulation]]"
        ],
        "sector": "Internet/Software",
        "defensive_rating": "Growth/Cyclical"
    },
    
    "MSFT": {
        "key_risks": [
            "Cloud growth deceleration",
            "AI investment ROI uncertainty",
            "Enterprise spending cyclicality",
            "Cybersecurity liability",
            "Regulatory scrutiny on acquisitions"
        ],
        "cross_references": [
            "[[Cloud Computing Growth]]",
            "[[Enterprise Software]]",
            "[[AI Investment Cycle]]",
            "[[Cybersecurity Risk]]",
            "[[Tech M&A Regulation]]"
        ],
        "sector": "Enterprise Software",
        "defensive_rating": "Moderate Defensive"
    },
    
    "AMZN": {
        "key_risks": [
            "E-commerce margin pressure",
            "AWS competition intensification",
            "Labor cost inflation",
            "Antitrust breakup risk",
            "International market losses"
        ],
        "cross_references": [
            "[[E-commerce Maturation]]",
            "[[Cloud Infrastructure]]",
            "[[Labor Cost Inflation]]",
            "[[Big Tech Breakup]]",
            "[[International Expansion]]"
        ],
        "sector": "E-commerce/Cloud",
        "defensive_rating": "Growth/Cyclical"
    },
    
    "TSLA": {
        "key_risks": [
            "EV competition acceleration",
            "Autonomous driving delays",
            "China market dependency",
            "Production scaling challenges",
            "CEO key person risk"
        ],
        "cross_references": [
            "[[EV Market Competition]]",
            "[[Autonomous Driving]]",
            "[[China Auto Market]]",
            "[[Manufacturing Scale]]",
            "[[Key Person Risk]]"
        ],
        "sector": "Electric Vehicles",
        "defensive_rating": "High Growth/Volatile"
    },
    
    "META": {
        "key_risks": [
            "Metaverse investment uncertainty",
            "TikTok user engagement threat",
            "Apple iOS privacy changes",
            "Regulatory content moderation",
            "Advertising market cyclicality"
        ],
        "cross_references": [
            "[[Metaverse Investment]]",
            "[[Social Media Competition]]",
            "[[Privacy Changes Impact]]",
            "[[Content Moderation]]",
            "[[Digital Advertising]]"
        ],
        "sector": "Social Media",
        "defensive_rating": "Growth/Cyclical"
    },
    
    "V": {
        "key_risks": [
            "Central bank digital currencies",
            "Fintech payment disruption",
            "Interchange fee regulation",
            "Economic recession impact",
            "Cryptocurrency adoption"
        ],
        "cross_references": [
            "[[Digital Payment Evolution]]",
            "[[Fintech Disruption]]",
            "[[Payment Network Moats]]",
            "[[Regulatory Fee Pressure]]",
            "[[Economic Cycle Impact]]"
        ],
        "sector": "Payment Processing",
        "defensive_rating": "Moderate Defensive"
    },
    
    "MA": {
        "key_risks": [
            "CBDC payment rail threat",
            "Buy-now-pay-later competition",
            "Cross-border fee pressure",
            "Economic downturn sensitivity",
            "Regulatory interchange limits"
        ],
        "cross_references": [
            "[[Payment Network Duopoly]]",
            "[[BNPL Competition]]",
            "[[Cross-border Payments]]",
            "[[Economic Sensitivity]]",
            "[[Fee Regulation Risk]]"
        ],
        "sector": "Payment Processing", 
        "defensive_rating": "Moderate Defensive"
    },
    
    "JPM": {
        "key_risks": [
            "Interest rate cycle dependency",
            "Credit loss provisioning",
            "Trading revenue volatility",
            "Regulatory capital requirements",
            "Fintech banking disruption"
        ],
        "cross_references": [
            "[[Interest Rate Cycle]]",
            "[[Credit Cycle Risk]]",
            "[[Banking Regulation]]",
            "[[Fintech Banking]]",
            "[[Systematic Risk]]"
        ],
        "sector": "Banking",
        "defensive_rating": "Cyclical/Financial"
    }
}

def get_company_intelligence(symbol: str) -> dict:
    """Get intelligence data for a company symbol."""
    return COMPANY_INTELLIGENCE.get(symbol, {
        "key_risks": ["Market volatility", "Competitive pressure", "Regulatory changes"],
        "cross_references": ["[[Market Risk]]", "[[Sector Analysis]]", "[[Competitive Landscape]]"],
        "sector": "General",
        "defensive_rating": "Market Average"
    })

def get_enhanced_context_for_symbol(symbol: str) -> str:
    """Get enhanced context string for wiki generation."""
    intel = get_company_intelligence(symbol)
    
    context = f"""
COMPANY INTELLIGENCE FOR {symbol}:
Sector: {intel['sector']}
Defensive Rating: {intel['defensive_rating']}

Key Material Risks to Address:
{chr(10).join(f"- {risk}" for risk in intel['key_risks'])}

Sophisticated Cross-References to Use:
{chr(10).join(intel['cross_references'])}
"""
    return context