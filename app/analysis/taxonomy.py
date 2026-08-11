from __future__ import annotations


import re
CATEGORIES = (
    "Foundation Model",
    "AI Agent",
    "AI Coding",
    "Multimodal / AIGC",
    "AI Product",
    "Enterprise Adoption",
    "Research",
    "Open Source",
    "AI Safety",
    "Cybersecurity",
    "Policy / Regulation",
    "Funding / Business",
    "Other",
)

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Foundation Model": (
        "foundation model", "language model", "large language model", "llm", "reasoning model",
        "model release", "frontier model", "gpt-", "gemini", "claude", "mistral",
    ),
    "AI Agent": (
        "ai agent", "agentic", "multi-agent", "tool use", "computer use", "autonomous agent",
        "voice agent",
    ),
    "AI Coding": (
        "ai coding", "code generation", "coding assistant", "developer tool", "software engineer",
        "copilot", "ide", "code review", "programming", "coding agent", "developers",
    ),
    "Multimodal / AIGC": (
        "multimodal", "image generation", "video generation", "music generation", "text-to-video",
        "diffusion", "creative control", "generated media", "aigc",
    ),
    "AI Product": (
        "ai product", "new feature", "assistant", "chatbot", "platform", "app", "consumer",
        "program", "ai tool", "web application", "workspace", "seat", "seats", "subscription",
        "pricing", "business tier", "usage limit", "product tier",
    ),
    "Enterprise Adoption": (
        "enterprise adoption", "case study", "customer journey", "chatgpt work", "workplace",
        "deployed across", "employees", "business transformation", "enterprise customer",
    ),
    "Research": (
        "research", "paper", "study", "benchmark", "evaluation", "scientific discovery",
        "technical report",
    ),
    "Open Source": (
        "open source", "open-source", "open weights", "open-weight", "apache license",
        "github release",
    ),
    "AI Safety": (
        "ai safety", "alignment", "model behavior", "preparedness", "responsible ai",
        "red teaming", "safety evaluation", "risk assessment",
    ),
    "Cybersecurity": (
        "cyber", "cybersecurity", "security incident", "vulnerability", "malware", "phishing",
        "threat", "exploit", "cyber defense",
    ),
    "Policy / Regulation": (
        "regulation", "regulator", "policy", "legislation", "lawmakers", "ai act", "executive order",
        "compliance", "government rule",
    ),
    "Funding / Business": (
        "funding", "raised", "valuation", "acquisition", "acquires", "merger", "revenue",
        "earnings", "partnership", "investment", "ipo",
    ),
}

CATEGORY_PRIORITY = {category: len(CATEGORIES) - index for index, category in enumerate(CATEGORIES)}


def _contains_keyword(text: str, keyword: str) -> bool:
    pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
    return re.search(pattern, text) is not None


def category_scores(title: str, content: str) -> dict[str, float]:
    title_text = title.casefold()
    full_text = f"{title} {content}".casefold()
    scores: dict[str, float] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0.0
        for keyword in keywords:
            if _contains_keyword(title_text, keyword):
                score += 3.0
            elif _contains_keyword(full_text, keyword):
                score += 1.0
        scores[category] = score
    return scores


def classify_text(title: str, content: str) -> tuple[str, list[str]]:
    scores = category_scores(title, content)
    highest = max(scores.values(), default=0.0)
    if highest <= 0:
        return "Other", []
    category = max(scores, key=lambda item: (scores[item], CATEGORY_PRIORITY[item]))
    text = f"{title} {content}".casefold()
    packaging_terms = (
        "seat", "seats", "subscription", "pricing", "business tier", "usage limit",
        "product tier", "workspace plan",
    )
    finance_terms = (
        "funding", "raised", "valuation", "acquisition", "acquires", "merger",
        "earnings", "investment round", "ipo",
    )
    if any(_contains_keyword(text, term) for term in packaging_terms) and not any(
        _contains_keyword(text, term) for term in finance_terms
    ):
        category = "AI Product"
    product_form_terms = ("ai tool", "web application", "assistant", "chatbot", "workspace")
    model_release_terms = ("model release", "introducing", "new model", "gemini", "gpt-", "claude")
    if any(_contains_keyword(text, term) for term in product_form_terms) and not any(
        _contains_keyword(title.casefold(), term) for term in model_release_terms
    ):
        category = "AI Product"

    cyber_context_terms = ("evaluation", "security incident", "vulnerability", "defense", "threat")
    cyber_is_primary = any(
        _contains_keyword(title.casefold(), term)
        for term in ("cybersecurity", "security incident", "vulnerability")
    ) or (
        _contains_keyword(title.casefold(), "cyber")
        and any(_contains_keyword(title.casefold(), term) for term in cyber_context_terms)
    )
    if scores["Cybersecurity"] > 0 and cyber_is_primary:
        category = "Cybersecurity"
    tags = [keyword for keyword in CATEGORY_KEYWORDS[category] if _contains_keyword(text, keyword)][:5]
    return category, tags


def taxonomy_prompt() -> str:
    return ", ".join(CATEGORIES)
