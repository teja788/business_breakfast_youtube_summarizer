from __future__ import annotations

from openai import OpenAI


class SummaryError(RuntimeError):
    """Raised when summary generation fails."""


def summarize_business_news(english_text: str, api_key: str, model: str) -> str:
    client = OpenAI(api_key=api_key)
    prompt = (
        "You summarize Telugu business-news videos for a Telegram audience. "
        "Write in plain English. Return exactly these sections: Summary, Key Points. "
        "The Summary section must be 2 to 3 sentences. "
        "The Key Points section must contain 5 to 8 short bullet points. "
        "Preserve company names, people names, dates, percentages, prices, and quantities when present."
    )

    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": english_text},
            ],
        )
    except Exception as exc:
        raise SummaryError(f"Summary generation failed: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        raise SummaryError("OpenAI returned an empty summary")
    return content.strip()


def format_telegram_message(title: str, url: str, summary_text: str) -> str:
    return "\n\n".join(
        [
            f"Business Breakfast Summary\n{title}",
            url,
            summary_text,
        ]
    )
