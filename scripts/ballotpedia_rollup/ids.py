"""Deterministic identifier generation."""
from .config import ELECTION_CYCLE_YEAR


def make_primary_id(seat: str, party: str, round_name: str, cycle: int = ELECTION_CYCLE_YEAR) -> str:
    return f"{seat}-{party}-{round_name}-{cycle}"
