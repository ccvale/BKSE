"""Ad-hoc SQL against the built ticketing database."""

import sqlite3
from pathlib import Path

from loguru import logger

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bkse.db"

SAMPLE = """
SELECT game_date, tip_time_et, section_code, row_label, seat_number, list_price
FROM v_tickets
WHERE opponent = 'New York Knicks'
AND status = 'available'
AND game_date = (
    SELECT MIN(g.game_date)
    FROM games g JOIN teams t ON t.team_id = g.away_team_id
    WHERE t.name = 'New York Knicks'
        AND g.game_date >= (SELECT value FROM settings WHERE key = 'as_of_date'))
ORDER BY list_price
LIMIT 1;
"""


def test_query(query: str) -> list[sqlite3.Row]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(query).fetchall()


if __name__ == "__main__":
    for row in test_query(SAMPLE):
        logger.info(dict(row))
