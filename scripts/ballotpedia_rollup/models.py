"""Data models for Ballotpedia rollup output contracts."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class PrimaryStatus(str, Enum):
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    RUNOFF = "runoff"
    COMPLETE = "complete"
    NONE = "none"
    UNKNOWN = "unknown"


class GeneralStatus(str, Enum):
    UPCOMING = "upcoming"
    PARTIAL = "partial"
    COMPLETE = "complete"
    UNKNOWN = "unknown"


class PartyCode(str, Enum):
    D = "D"
    R = "R"
    G = "G"
    L = "L"
    NP = "NP"
    IND = "IND"
    OTH = "OTH"


class PrimaryRound(str, Enum):
    PRIMARY = "primary"
    RUNOFF = "runoff"
    CONVENTION = "convention"
    TOP_TWO = "top_two"


@dataclass(slots=True)
class GeneralElectionRow:
    seat: str
    state: str
    district: str
    incumbent_name: str | None = None
    incumbent_party: str | None = None
    incumbent_status: str = ""
    fec_incumbent_name: str = ""
    fec_incumbent_party: str = ""
    fec_incumbent_conflict: str = ""
    nominee_d: str | None = None
    nominee_r: str | None = None
    nominee_green: str | None = None
    nominee_libertarian: str | None = None
    other_general_candidates: list[str] = field(default_factory=list)
    primary_status_d: str = PrimaryStatus.UNKNOWN
    primary_status_r: str = PrimaryStatus.UNKNOWN
    primary_status_np: str = PrimaryStatus.UNKNOWN
    primary_reason_d: str = ""
    primary_reason_r: str = ""
    primary_reason_np: str = ""
    primary_id_d: str | None = None
    primary_id_r: str | None = None
    primary_id_np: str | None = None
    general_vote_total: int | None = None
    historical_general_vote_totals: dict[str, int] = field(default_factory=dict)
    historical_primary_vote_totals: dict[str, dict[str, int]] = field(default_factory=dict)
    historical_primary_status: dict[str, dict[str, str]] = field(default_factory=dict)
    historical_primary_reason: dict[str, dict[str, str]] = field(default_factory=dict)
    general_status: str = GeneralStatus.UNKNOWN
    source_file: str = ""
    source_url: str | None = None
    parser_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class PrimaryElectionRow:
    primary_id: str
    seat: str
    state: str
    district: str
    party: str
    round: str
    status: str
    cancellation_reason: str = ""
    candidates: list[str] = field(default_factory=list)
    primary_vote_total: int | None = None
    primary_vote_share: dict[str, float] = field(default_factory=dict)
    primary_vote_count: dict[str, int] = field(default_factory=dict)
    runoff_candidate_1: str | None = None
    runoff_candidate_2: str | None = None
    runoff_id: str | None = None
    parent_primary_id: str | None = None
    source_file: str = ""
    source_url: str | None = None
    parser_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
