'''Ad-hoc SQL against the built ticketing database.'''

import sqlite3
from pathlib import Path

from loguru import logger

DB_PATH = Path(__file__).resolve().parent / 'data' / 'bkse.db'

# game 72 is the id from seed 42. another seed will not match.
SAMPLE = '''
SELECT s.section_id, s.row_label, MIN(s.seat_number) AS start_seat, MAX(s.seat_number) AS end_seat, COUNT(*) AS cnt
FROM tickets t
JOIN seats s ON t.seat_id = s.seat_id
JOIN sections sec ON s.section_id = sec.section_id
WHERE t.game_id = 72
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
