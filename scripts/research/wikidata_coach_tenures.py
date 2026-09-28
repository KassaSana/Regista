"""Print unreviewed Wikidata head-coach tenure candidates for one team QID."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from regista.adapters.wikidata.coaches import fetch_coach_tenures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("team_entity", help="Wikidata Q identifier of one sports team")
    arguments = parser.parse_args()
    user_agent = os.environ.get("REGISTA_WIKIDATA_USER_AGENT", "")
    if not user_agent:
        parser.error("set REGISTA_WIKIDATA_USER_AGENT to an identifiable contact string")
    candidates = fetch_coach_tenures(arguments.team_entity, user_agent=user_agent)
    print(json.dumps([asdict(candidate) for candidate in candidates], indent=2, default=str))


if __name__ == "__main__":
    main()
