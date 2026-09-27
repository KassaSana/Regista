"""Provider-neutral metadata needed to select a corpus and freeze evaluation splits."""

from dataclasses import dataclass
from datetime import date, time
from typing import Literal

CorpusRole = Literal["core_breadth", "modern_robustness"]
Coverage = Literal["complete_season", "single_team", "tournament"]


@dataclass(frozen=True)
class CompetitionSeason:
    competition_id: int
    season_id: int
    role: CorpusRole
    coverage: Coverage
    expected_matches: int
    known_missing_matches: int = 0


@dataclass(frozen=True)
class CorpusConfiguration:
    provider: str
    dataset: str
    source_commit: str
    seasons: tuple[CompetitionSeason, ...]
    inspected_match_ids: tuple[int, ...]
    review_seed: int
    sha256: str


@dataclass(frozen=True)
class MatchIndex:
    match_id: int
    competition_id: int
    season_id: int
    match_date: date
    kickoff: time
    has_three_sixty: bool
    missing_metadata: tuple[str, ...]
    provider_last_updated: str | None = None

    @property
    def season_key(self) -> tuple[int, int]:
        return self.competition_id, self.season_id


@dataclass(frozen=True)
class IndexSource:
    relative_path: str
    url: str
    sha256: str
    byte_count: int
    retrieved_at: str


@dataclass(frozen=True)
class IndexCatalog:
    matches: tuple[MatchIndex, ...]
    sources: tuple[IndexSource, ...]
