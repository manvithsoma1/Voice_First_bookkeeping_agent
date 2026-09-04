"""
transcription.py — Clean service wrapper for Groq Whisper STT.

Re-exports transcribe_audio from parser_agent so callers don't need to
know the internal module structure. Satisfies the planned services/ layout.
"""

from __future__ import annotations

# Re-export — the real implementation lives in parser_agent to keep
# the Groq client centralised.
from backend.agents.parser_agent import transcribe_audio as transcribe_audio  # noqa: F401

__all__ = ["transcribe_audio"]
