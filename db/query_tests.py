'''Ad-hoc SQL against the built ticketing database.'''

import sqlite3
from pathlib import Path

from loguru import logger

DB_PATH = Path(__file__).resolve().parent / 'data' / 'bkse.db'

# next home game after the 2026-10-28 snapshot.
SAMPLE = '''
SELECT s.section_id, s.row_label, MIN(s.seat_number) AS start_seat, MAX(s.seat_number) AS end_seat, COUNT(*) AS cnt
FROM tickets t
JOIN seats s ON t.seat_id = s.seat_id
JOIN sections sec ON s.section_id = sec.section_id
JOIN games g ON g.game_id = t.game_id
WHERE g.game_date = '2026-10-30'
  AND g.is_home = 1
  AND t.status = 'available'
  AND sec.level = 'Upper Bowl'
GROUP BY s.section_id, s.row_label
HAVING cnt >= 12
ORDER BY cnt DESC
'''

if __name__ == '__main__':
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(SAMPLE):
            logger.info(dict(row))
