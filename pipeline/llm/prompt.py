"""Prompt templates for LLM extraction (Milestone 7).

The article text may be Bulgarian or Romanian (see AGENTS.md). The model's
output is forced into grammar.gbnf's schema, so the prompt only needs to
describe the task, not the JSON syntax.
"""
from datetime import date

# Keep the article body within a safe context budget for a 7B model
# (system + user prompt + generation headroom all share the same window).
MAX_BODY_CHARS = 4000

SYSTEM_PROMPT = """You are an information-extraction assistant for a local-events aggregator covering Shabla, Bulgaria and the surrounding region (both Bulgarian and Romanian sides of the border).

You will be given the text of a news article or event-listing entry. It may be written in Bulgarian or Romanian.

Determine whether it describes a specific real-world local event -- a concert, festival, exhibition, municipal announcement with a date, sports event, theater performance, or similar -- taking place in or near the covered region. Purely administrative notices, general news with no scheduled activity, obituaries, and opinion pieces are NOT events.

If it does not describe an event, set is_event to false and leave the other fields empty strings (except category, which should be "other").

If it does describe an event, extract:
- title: a concise event title
- date: the event's date as YYYY-MM-DD if it can be determined (resolve relative phrases like "tomorrow"/"утре"/"mâine" using the provided current date), otherwise an empty string
- time: the event's start time as HH:MM (24-hour) if stated, otherwise an empty string
- location: the venue or place name as stated in the text
- category: one of concert, festival, exhibition, municipal, sports, theater, adult_18+, or other. Use adult_18+ for nightlife, adult-oriented, or age-restricted event programming (e.g. club parties, adult venues) rather than defaulting to other.
- description: a brief 1-2 sentence summary of the event, in the same language as the source text

Respond with only the JSON object matching the required schema."""


def build_user_prompt(source_name: str, source_url: str, title: str, body: str, today: date | None = None) -> str:
    today = today or date.today()
    truncated_body = (body or "")[:MAX_BODY_CHARS]
    return (
        f"Today's date: {today.isoformat()}\n"
        f"Source: {source_name} ({source_url})\n"
        f"Title: {title}\n"
        f"Body: {truncated_body}"
    )


TRANSLATE_SYSTEM_PROMPT = """You are a translator for a local-events website covering Shabla, Bulgaria and the surrounding region.

You will be given an event's title and short description, written in Bulgarian or Romanian (or occasionally English). Produce the title and description in ALL THREE of: English (en), Bulgarian (bg), and Romanian (ro).

Rules:
- For the language the text is already written in, copy it unchanged.
- Translate the MEANING of ordinary words into each language (for example "Festivalul Toamnei" becomes "Autumn Festival" / "Есенен фестивал"). Never transliterate an ordinary word into another alphabet as if it were a name.
- Only proper nouns (people, venues, place names, brand names) are kept or transliterated as-is; do not invent new names.
- If a description is provided, it is NOT empty: you must give a translated description in ALL THREE languages, about the same length as the original (1-2 sentences). Only return empty description strings when the input description is empty.

Respond with only the JSON object matching the required schema."""


def build_translate_prompt(title: str, description: str) -> str:
    return "Title: " + title + "\nDescription: " + (description or "")[:1500]
