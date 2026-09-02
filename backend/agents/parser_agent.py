"""
parser_agent.py — Phase 2 & 3
  • parse_transaction(raw_input)  → calls Groq LLM, returns structured dict
  • transcribe_audio(file_path)   → calls Groq Whisper, returns text

Parsing prompt is designed to be reliable on home-business voice notes.
A retry loop catches malformed JSON before it ever leaves this module.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# ─────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────

_client: Optional[Groq] = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY not set. Copy .env.example → .env and add your key."
            )
        _client = Groq(api_key=api_key)
    return _client


# ─────────────────────────────────────────────
# System prompt (Phase 2 design)
# ─────────────────────────────────────────────

PARSE_SYSTEM_PROMPT = """You are a bookkeeping assistant for a small home business (specifically a home pickle/condiment business).
Parse the following spoken or typed note into a structured transaction.

Return ONLY valid JSON — no markdown fences, no explanation — with EXACTLY these fields:
- type: "income" or "expense"
- category: one of ["sales", "raw_materials", "packaging", "transport", "other"]
- amount: total amount as a number (calculate quantity × unit_price if both given)
- quantity: number of units if mentioned, else null
- unit_price: price per unit if mentioned, else null
- confidence: your confidence 0.0–1.0 that this parse is correct

Category guidance:
  sales          → selling products, received payment, customer orders
  raw_materials  → ingredients, spices, produce bought for making products
  packaging      → jars, lids, labels, boxes, wrapping
  transport      → delivery, shipping, fuel, courier fees
  other          → anything that doesn't fit the above

Confidence guidance:
  0.9–1.0  → clear, unambiguous input with all key fields
  0.7–0.89 → reasonable inference, one field uncertain
  0.5–0.69 → ambiguous input, best-guess parse
  < 0.5    → very unclear, missing critical info (e.g. no amount)

Examples:
"sold 5 jars today, 200 each" → {"type":"income","category":"sales","amount":1000,"quantity":5,"unit_price":200,"confidence":0.95}
"paid 300 for jars" → {"type":"expense","category":"packaging","amount":300,"quantity":null,"unit_price":null,"confidence":0.90}
"bought chillies and mustard seeds, spent around 450" → {"type":"expense","category":"raw_materials","amount":450,"quantity":null,"unit_price":null,"confidence":0.85}
"delivery charges for last week" → {"type":"expense","category":"transport","amount":0,"quantity":null,"unit_price":null,"confidence":0.30}
"""


def _extract_json(text: str) -> dict:
    """
    Robustly extract a JSON object from an LLM response.
    Handles markdown fences, leading prose, trailing text.
    """
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract valid JSON from LLM response: {text[:200]!r}")


def _normalise_parsed(data: dict, raw_input: str) -> dict:
    """
    Normalise and validate parser output so downstream code never sees
    missing keys or wrong types.
    """
    allowed_types = {"income", "expense"}
    allowed_categories = {"sales", "raw_materials", "packaging", "transport", "other"}

    tx_type = str(data.get("type", "expense")).lower()
    if tx_type not in allowed_types:
        tx_type = "expense"

    category = str(data.get("category", "other")).lower()
    if category not in allowed_categories:
        category = "other"

    try:
        amount = float(data.get("amount", 0) or 0)
    except (TypeError, ValueError):
        amount = 0.0

    quantity = data.get("quantity")
    if quantity is not None:
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            quantity = None

    unit_price = data.get("unit_price")
    if unit_price is not None:
        try:
            unit_price = float(unit_price)
        except (TypeError, ValueError):
            unit_price = None

    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5) or 0.5)))
    except (TypeError, ValueError):
        confidence = 0.5

    return {
        "type": tx_type,
        "category": category,
        "amount": amount,
        "quantity": quantity,
        "unit_price": unit_price,
        "confidence": confidence,
        "raw_input": raw_input,
    }


# ─────────────────────────────────────────────
# Public: parse_transaction
# ─────────────────────────────────────────────

def parse_transaction(raw_input: str, max_retries: int = 3) -> dict:
    """
    Call the Groq LLM and return a normalised transaction dict.

    Retries up to `max_retries` times on JSON parse failure, using
    slightly higher temperature on each retry to unstick the model.
    """
    client = _get_client()

    for attempt in range(1, max_retries + 1):
        temperature = 0.1 + (attempt - 1) * 0.15  # 0.1 → 0.25 → 0.40
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": PARSE_SYSTEM_PROMPT},
                    {"role": "user", "content": raw_input},
                ],
                temperature=temperature,
                max_tokens=256,
            )

            content = response.choices[0].message.content or ""
            data = _extract_json(content)
            return _normalise_parsed(data, raw_input)

        except ValueError as exc:
            print(f"[parser] Attempt {attempt}/{max_retries} failed JSON parse: {exc}")
            if attempt < max_retries:
                time.sleep(0.5)
            else:
                # Fallback: return a low-confidence placeholder so the pipeline
                # doesn't crash — the validator will flag it for review.
                print("[parser] All retries exhausted — returning fallback transaction.")
                return _normalise_parsed(
                    {"confidence": 0.1, "amount": 0},
                    raw_input,
                )
        except Exception as exc:
            print(f"[parser] Groq API error on attempt {attempt}: {exc}")
            if attempt < max_retries:
                time.sleep(1.0)
            else:
                raise


# ─────────────────────────────────────────────
# Public: transcribe_audio  (Phase 3)
# ─────────────────────────────────────────────

SUPPORTED_AUDIO_FORMATS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}


def transcribe_audio(file_path: str) -> str:
    """
    Transcribe an audio file using Groq's Whisper Large V3 Turbo endpoint.

    Args:
        file_path: Absolute or relative path to the audio file.

    Returns:
        Transcribed text string.

    Raises:
        ValueError: If the file extension is not supported.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_AUDIO_FORMATS:
        raise ValueError(
            f"Unsupported audio format '{suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_AUDIO_FORMATS))}"
        )

    client = _get_client()

    with open(path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            file=(path.name, audio_file),
            model="whisper-large-v3-turbo",
            response_format="text",
            language="en",          # remove for auto-detect
        )

    # Groq returns a str when response_format="text"
    text = transcription if isinstance(transcription, str) else transcription.text
    return text.strip()
