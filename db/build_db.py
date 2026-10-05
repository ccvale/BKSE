"""Build the BKSE ticketing database (SQLite) from the raw schedules plus synthetic data.

Usage:
    python db/build_db.py                 # writes db/data/bkse.db
    python db/build_db.py --out other.db --seed 7

What is real vs synthetic:
- Real: team names, the Nets' 2025-26 home results and attendance, the announced 2026-27 home schedule.
- Modeled: the Barclays Center seat map (real section numbering, approximate row/seat counts).
- Synthetic: every price, sale, order and seat status. Prices follow simple, documented drivers
  (opponent draw, day of week, holidays, seat location, days until the game) so trends are learnable.
"""

from __future__ import annotations

import argparse
import csv
import random
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from loguru import logger

DB_DIR = Path(__file__).resolve().parent
RAW = DB_DIR / 'data' / 'raw'
SCHEMA = DB_DIR / 'schema.sql'

AS_OF_DATE = date(2026, 10, 1)           # 'today' inside the dataset
SINGLE_GAME_ONSALE = {'2025-26': date(2025, 8, 20), '2026-27': date(2026, 8, 20)}
SEASON_TICKET_ORDER_DATE = {'2025-26': date(2025, 6, 15), '2026-27': date(2026, 6, 15)}
SEASONS = {'2025-26': ('2025-10-21', '2026-04-12'), '2026-27': ('2026-10-20', '2027-04-11')}
SEASON_PRICE_FACTOR = {'2025-26': 1.00, '2026-27': 1.05}   # year-over-year list price increase

# --------------------------------------------------------------------------- teams

TEAMS = [
    # name, abbreviation, city, nickname, conference, division
    ('Boston Celtics', 'BOS', 'Boston', 'Celtics', 'East', 'Atlantic'),
    ('Brooklyn Nets', 'BKN', 'Brooklyn', 'Nets', 'East', 'Atlantic'),
    ('New York Knicks', 'NYK', 'New York', 'Knicks', 'East', 'Atlantic'),
    ('Philadelphia 76ers', 'PHI', 'Philadelphia', '76ers', 'East', 'Atlantic'),
    ('Toronto Raptors', 'TOR', 'Toronto', 'Raptors', 'East', 'Atlantic'),
    ('Chicago Bulls', 'CHI', 'Chicago', 'Bulls', 'East', 'Central'),
    ('Cleveland Cavaliers', 'CLE', 'Cleveland', 'Cavaliers', 'East', 'Central'),
    ('Detroit Pistons', 'DET', 'Detroit', 'Pistons', 'East', 'Central'),
    ('Indiana Pacers', 'IND', 'Indiana', 'Pacers', 'East', 'Central'),
    ('Milwaukee Bucks', 'MIL', 'Milwaukee', 'Bucks', 'East', 'Central'),
    ('Atlanta Hawks', 'ATL', 'Atlanta', 'Hawks', 'East', 'Southeast'),
    ('Charlotte Hornets', 'CHA', 'Charlotte', 'Hornets', 'East', 'Southeast'),
    ('Miami Heat', 'MIA', 'Miami', 'Heat', 'East', 'Southeast'),
    ('Orlando Magic', 'ORL', 'Orlando', 'Magic', 'East', 'Southeast'),
    ('Washington Wizards', 'WAS', 'Washington', 'Wizards', 'East', 'Southeast'),
    ('Denver Nuggets', 'DEN', 'Denver', 'Nuggets', 'West', 'Northwest'),
    ('Minnesota Timberwolves', 'MIN', 'Minnesota', 'Timberwolves', 'West', 'Northwest'),
    ('Oklahoma City Thunder', 'OKC', 'Oklahoma City', 'Thunder', 'West', 'Northwest'),
    ('Portland Trail Blazers', 'POR', 'Portland', 'Trail Blazers', 'West', 'Northwest'),
    ('Utah Jazz', 'UTA', 'Utah', 'Jazz', 'West', 'Northwest'),
    ('Golden State Warriors', 'GSW', 'Golden State', 'Warriors', 'West', 'Pacific'),
    ('LA Clippers', 'LAC', 'Los Angeles', 'Clippers', 'West', 'Pacific'),
    ('Los Angeles Lakers', 'LAL', 'Los Angeles', 'Lakers', 'West', 'Pacific'),
    ('Phoenix Suns', 'PHX', 'Phoenix', 'Suns', 'West', 'Pacific'),
    ('Sacramento Kings', 'SAC', 'Sacramento', 'Kings', 'West', 'Pacific'),
    ('Dallas Mavericks', 'DAL', 'Dallas', 'Mavericks', 'West', 'Southwest'),
    ('Houston Rockets', 'HOU', 'Houston', 'Rockets', 'West', 'Southwest'),
    ('Memphis Grizzlies', 'MEM', 'Memphis', 'Grizzlies', 'West', 'Southwest'),
    ('New Orleans Pelicans', 'NOP', 'New Orleans', 'Pelicans', 'West', 'Southwest'),
    ('San Antonio Spurs', 'SAS', 'San Antonio', 'Spurs', 'West', 'Southwest'),
]

# How strongly each opponent drives demand (1.0 = average). Hidden pricing driver, not stored.
OPPONENT_DRAW = {
    'NYK': 2.2, 'LAL': 2.0, 'GSW': 1.9, 'BOS': 1.6, 'SAS': 1.45, 'OKC': 1.35, 'DEN': 1.3,
    'DAL': 1.25, 'PHI': 1.2, 'MIL': 1.2, 'MIA': 1.1, 'CLE': 1.1, 'PHX': 1.1, 'LAC': 1.1,
    'HOU': 1.1, 'MIN': 1.1, 'CHI': 1.0, 'NOP': 0.95, 'TOR': 0.95, 'ATL': 0.9, 'IND': 0.9,
    'ORL': 0.9, 'DET': 0.9, 'MEM': 0.9, 'SAC': 0.9, 'POR': 0.85, 'UTA': 0.85, 'CHA': 0.85,
    'WAS': 0.85,
}
WEEKDAY_FACTOR = [0.92, 0.95, 0.97, 1.00, 1.12, 1.15, 1.05]   # Mon..Sun

# --------------------------------------------------------------------------- seat map

# Lower/upper bowl sections share one layout: section n (1-31) and 200+n.
POSITION_OF = {}
for n in (7, 8, 9, 23, 24, 25):
    POSITION_OF[n] = 'Sideline Center'
for n in (5, 6, 10, 11, 21, 22, 26, 27):
    POSITION_OF[n] = 'Sideline'
for n in (3, 4, 12, 13, 19, 20, 28, 29):
    POSITION_OF[n] = 'Corner'
for n in (1, 2, 14, 15, 16, 17, 18, 30, 31):
    POSITION_OF[n] = 'Baseline'

# position -> (rows, seats in row 1, extra seat every k rows)
LOWER_LAYOUT = {'Sideline Center': (19, 18, 4), 'Sideline': (19, 16, 4), 'Corner': (17, 14, 4), 'Baseline': (17, 15, 4)}
UPPER_LAYOUT = {'Sideline Center': (20, 22, 0), 'Sideline': (14, 18, 0), 'Corner': (10, 14, 0), 'Baseline': (10, 14, 0)}

# code, name, position, rows, seats per row
COURTSIDE = [
    ('CS1', 'Courtside Nets Bench Side (Sections 7-9)', 'Sideline Center', ['AA', 'BB'], 36),
    ('CS2', 'Courtside Opposite Sideline (Sections 23-25)', 'Sideline Center', ['AA', 'BB', 'CC', 'DD'], 36),
    ('CS3', 'Courtside Baseline (Sections 1, 31)', 'Baseline', ['AA', 'BB'], 14),
    ('CS4', 'Courtside Baseline (Sections 15-17)', 'Baseline', ['AA', 'BB'], 14),
]

# price_level -> row-1 base price (USD) for an average opponent on a Thursday, 2025-26
BASE_PRICE = {
    'Courtside Sideline': 1500, 'Courtside Baseline': 750,
    'Lower Sideline Center': 240, 'Lower Sideline': 175, 'Lower Corner': 130, 'Lower Baseline': 105,
    'Upper Sideline Center': 70, 'Upper Sideline': 52, 'Upper Corner': 40, 'Upper Baseline': 30,
}
COURTSIDE_ROW_FACTOR = {'AA': 1.0, 'BB': 0.8, 'CC': 0.65, 'DD': 0.55}

# Share of seats held by season-ticket accounts.
SEASON_TICKET_SHARE = {
    'Courtside Sideline': 0.55, 'Courtside Baseline': 0.45,
    'Lower Sideline Center': 0.45, 'Lower Sideline': 0.35, 'Lower Corner': 0.25, 'Lower Baseline': 0.20,
    'Upper Sideline Center': 0.20, 'Upper Sideline': 0.12, 'Upper Corner': 0.10, 'Upper Baseline': 0.10,
}
# Relative chance a non-season seat goes unsold (higher = harder to sell).
UNSOLD_PROPENSITY = {
    'Courtside Sideline': 2.0, 'Courtside Baseline': 2.5,
    'Lower Sideline Center': 0.5, 'Lower Sideline': 0.7, 'Lower Corner': 1.0, 'Lower Baseline': 1.2,
    'Upper Sideline Center': 1.0, 'Upper Sideline': 1.4, 'Upper Corner': 2.0, 'Upper Baseline': 2.4,
}
ORDER_SIZES = [(1, 0.10), (2, 0.42), (3, 0.10), (4, 0.25), (5, 0.04), (6, 0.06), (8, 0.03)]
HOLD_RATE = 0.015


@dataclass
class Seat:
    seat_id: int
    section_id: int
    price_level: str
    level: str
    row_label: str
    row_order: int
    seat_number: int
    base: float          # season-neutral, opponent-neutral price for this seat


@dataclass
class Game:
    game_id: int
    season_id: str
    game_date: date
    opponent_abbr: str
    status: str
    attendance: int | None
    demand: float = 1.0


# --------------------------------------------------------------------------- helpers

def round_price(p: float, level: str) -> float:
    step = 25 if level == 'Courtside' else 1
    return float(max(step, round(p / step) * step))


def dynamic_factor(demand: float, days_out: int) -> float:
    '''Prices drift toward game day: up for hot games, down for soft ones.'''
    closeness = 1 - min(days_out, 120) / 120
    return 1 + (demand - 1) * 0.5 * closeness


def list_price(seat: Seat, game: Game, days_out: int) -> float:
    p = seat.base * SEASON_PRICE_FACTOR[game.season_id] * game.demand * dynamic_factor(game.demand, days_out)
    return round_price(p, seat.level)


def weighted_order_size(rng: random.Random) -> int:
    r, acc = rng.random(), 0.0
    for size, w in ORDER_SIZES:
        acc += w
        if r <= acc:
            return size
    return 2


def random_time(rng: random.Random, d: date) -> str:
    return datetime(d.year, d.month, d.day, rng.randint(8, 23), rng.randint(0, 59), rng.randint(0, 59)).isoformat(sep=' ')


# --------------------------------------------------------------------------- builders

def load_teams(con: sqlite3.Connection) -> dict[str, int]:
    con.executemany(
        'INSERT INTO teams (name, abbreviation, city, nickname, conference, division) VALUES (?,?,?,?,?,?)', TEAMS
    )
    return {abbr: tid for tid, abbr in con.execute('SELECT team_id, abbreviation FROM teams')}


def build_seat_map(con: sqlite3.Connection, rng: random.Random) -> list[Seat]:
    seats: list[Seat] = []

    def add_section(code, name, level, position, price_level, rows):
        cur = con.execute(
            'INSERT INTO sections (section_code, section_name, level, position, price_level) VALUES (?,?,?,?,?)',
            (code, name, level, position, price_level),
        )
        section_id = cur.lastrowid
        n_rows = len(rows)
        for row_order, (row_label, n_seats, row_factor) in enumerate(rows, start=1):
            for seat_number in range(1, n_seats + 1):
                is_aisle = int(seat_number in (1, n_seats))
                # wheelchair/companion seating on the back row of lower and upper baseline sections
                is_accessible = int(level != 'Courtside' and position == 'Baseline' and row_order == n_rows and seat_number <= 4)
                cur = con.execute(
                    'INSERT INTO seats (section_id, row_label, row_order, seat_number, is_aisle, is_accessible) VALUES (?,?,?,?,?,?)',
                    (section_id, row_label, row_order, seat_number, is_aisle, is_accessible),
                )
                aisle_bump = 1.03 if is_aisle else 1.0
                seat_noise = rng.uniform(0.96, 1.04)
                base = BASE_PRICE[price_level] * row_factor * aisle_bump * seat_noise
                seats.append(Seat(cur.lastrowid, section_id, price_level, level, row_label, row_order, seat_number, base))

    for code, name, position, row_labels, per_row in COURTSIDE:
        pl = 'Courtside Sideline' if position == 'Sideline Center' else 'Courtside Baseline'
        add_section(code, name, 'Courtside', position, pl, [(r, per_row, COURTSIDE_ROW_FACTOR[r]) for r in row_labels])

    for level, offset, layout, depth in (('Lower Bowl', 0, LOWER_LAYOUT, 0.30), ('Upper Bowl', 200, UPPER_LAYOUT, 0.25)):
        prefix = 'Lower' if offset == 0 else 'Upper'
        for n in range(1, 32):
            position = POSITION_OF[n]
            n_rows, first, every = layout[position]
            rows = []
            for r in range(1, n_rows + 1):
                n_seats = first + (r // every if every else 0)
                row_factor = 1 - depth * (r - 1) / (n_rows - 1)
                rows.append((str(r), n_seats, row_factor))
            code = str(n + offset)
            add_section(code, f'Section {code}', level, position, f'{prefix} {position}', rows)
    return seats


def load_games(con: sqlite3.Connection, team_ids: dict[str, int]) -> list[Game]:
    for sid, (start, end) in SEASONS.items():
        con.execute('INSERT INTO seasons VALUES (?,?,?)', (sid, start, end))
    name_to_abbr = {t[0]: t[1] for t in TEAMS}
    games: list[Game] = []

    with open(RAW / 'nets_2025_26_home_results.csv', newline='') as f:
        for row in csv.DictReader(f):
            abbr = name_to_abbr[row['opponent']]
            cur = con.execute(
                """INSERT INTO games (season_id, game_date, tip_time_et, away_team_id,
                   game_type, status, home_score, away_score, attendance)
                   VALUES ('2025-26', ?, ?, ?, ?, 'final', ?, ?, ?)""",
                (row['game_date'], row['tip_time_et'], team_ids[abbr], row['game_type'], int(row['nets_score']), int(row['opponent_score']), int(row['attendance'])),
            )
            games.append(Game(cur.lastrowid, '2025-26', date.fromisoformat(row['game_date']), abbr, 'final', int(row['attendance'])))

    with open(RAW / 'nets_2026_27_home_schedule.csv', newline='') as f:
        for row in csv.DictReader(f):
            abbr = name_to_abbr[row['opponent']]
            cur = con.execute(
                """INSERT INTO games (season_id, game_date, tip_time_et, away_team_id,
                   game_type, status) VALUES ('2026-27', ?, ?, ?, ?, 'scheduled')""",
                (row['game_date'], row['tip_time_et'], team_ids[abbr], row['game_type']),
            )
            games.append(Game(cur.lastrowid, '2026-27', date.fromisoformat(row['game_date']), abbr, 'scheduled', None))

    for sid in SEASONS:
        season_games = sorted((g for g in games if g.season_id == sid), key=lambda g: g.game_date)
        for i, g in enumerate(season_games):
            d = OPPONENT_DRAW[g.opponent_abbr] * WEEKDAY_FACTOR[g.game_date.weekday()]
            if i == 0:
                d *= 1.25                                    # home opener
            if (g.game_date.month, g.game_date.day) >= (12, 20) or (g.game_date.month == 1 and g.game_date.day <= 2):
                d *= 1.10                                    # holiday week
            if sid == '2025-26' and g.game_date.month == 3:
                d *= 0.92                                    # losing season fades late
            if sid == '2025-26' and g.game_date.month == 4:
                d *= 0.85
            g.demand = d
    return games


def season_ticket_accounts(seats: list[Seat], rng: random.Random) -> dict[int, int]:
    '''Map seat_id -> account number. Accounts hold 2-4 adjacent seats in one row.'''
    by_row: dict[tuple, list[Seat]] = {}
    for s in seats:
        by_row.setdefault((s.section_id, s.row_label), []).append(s)
    owner: dict[int, int] = {}
    account = 0
    for row in by_row.values():
        row.sort(key=lambda s: s.seat_number)
        share = SEASON_TICKET_SHARE[row[0].price_level]
        i = 0
        while i < len(row):
            size = rng.choice((2, 2, 2, 3, 4, 4))
            if rng.random() < share:
                account += 1
                for s in row[i:i + size]:
                    owner[s.seat_id] = account
            i += size
    return owner


def expected_sell_through(game: Game) -> float:
    '''Share of all seats that end up sold (incl. season tickets).'''
    if game.attendance is not None:
        # announced attendance includes comps and suites; map it onto our manifest
        return min(0.97, max(0.80, 0.82 + 0.15 * (game.attendance - 16400) / 1900))
    return min(0.97, 0.80 + 0.13 * min(1.0, max(0.0, (game.demand - 0.8) / 1.3)))


def simulate_game(game: Game, seats: list[Seat], owners: dict[int, int], rng: random.Random, next_order_id):
    '''Return (orders, tickets) rows for one game.'''
    orders, tickets = [], []
    days_until_game_from_asof = (game.game_date - AS_OF_DATE).days
    onsale = SINGLE_GAME_ONSALE[game.season_id]
    sale_window = (game.game_date - onsale).days

    # 1. holds
    held = {s.seat_id for s in seats if s.level != 'Courtside' and s.seat_id not in owners and rng.random() < HOLD_RATE}

    # 2. season tickets: one order per account per game, fixed season price
    season_price = {}
    by_account: dict[int, list[Seat]] = {}
    for s in seats:
        acc = owners.get(s.seat_id)
        if acc is not None:
            by_account.setdefault(acc, []).append(s)
    st_date = SEASON_TICKET_ORDER_DATE[game.season_id]
    for acc_seats in by_account.values():
        oid = next_order_id()
        total = 0.0
        ordered_at = random_time(rng, st_date + timedelta(days=rng.randint(0, 30)))
        for s in acc_seats:
            p = round_price(s.base * SEASON_PRICE_FACTOR[game.season_id] * 0.85, s.level)
            season_price[s.seat_id] = p
            total += p
            tickets.append((game.game_id, s.seat_id, 'sold', list_price(s, game, 0 if game.status == 'final' else max(days_until_game_from_asof, 0)), p, ordered_at, oid))
        orders.append((oid, game.game_id, ordered_at, 'season_ticket', len(acc_seats), round(total, 2)))

    # 3. single-game buyers: choose which open seats eventually sell, weighted toward easy-to-sell seats
    open_seats = [s for s in seats if s.seat_id not in owners and s.seat_id not in held]
    target_sold = int(expected_sell_through(game) * len(seats)) - len(owners)
    target_sold = max(0, min(target_sold, len(open_seats)))
    # Efraimidis-Spirakis weighted sampling of the seats that stay UNSOLD
    keyed = sorted(open_seats, key=lambda s: rng.random() ** (1 / UNSOLD_PROPENSITY[s.price_level]), reverse=True)
    will_sell = {s.seat_id for s in keyed[len(open_seats) - target_sold:]} if target_sold else set()

    # group sellable seats into orders of adjacent seats
    by_row: dict[tuple, list[Seat]] = {}
    for s in open_seats:
        by_row.setdefault((s.section_id, s.row_label), []).append(s)
    mean_lead = min(120.0, 18.0 * game.demand ** 1.5)     # hot games sell further ahead
    decided: dict[int, tuple] = {}
    for row in by_row.values():
        row.sort(key=lambda s: s.seat_number)
        i = 0
        while i < len(row):
            if row[i].seat_id not in will_sell:
                i += 1
                continue
            size = weighted_order_size(rng)
            chunk = [s for s in row[i:i + size] if s.seat_id in will_sell]
            # stop the chunk at the first gap so orders stay adjacent
            run = [chunk[0]]
            for s in chunk[1:]:
                if s.seat_number == run[-1].seat_number + 1:
                    run.append(s)
                else:
                    break
            days_out = int(rng.expovariate(1 / mean_lead))
            if days_out > sale_window:
                days_out = rng.randint(max(0, sale_window - 10), sale_window)   # on-sale rush
            for s in run:
                decided[s.seat_id] = (days_out, run[0].seat_id)
            i += len(run)

    pending_orders: dict[int, list] = {}
    for s in open_seats:
        if s.seat_id in decided:
            days_out, key = decided[s.seat_id]
            sold_by_asof = game.status == 'final' or days_out >= days_until_game_from_asof
            if sold_by_asof:
                pending_orders.setdefault(key, [days_out, []])[1].append(s)
                continue
        # still for sale (current season) or never sold (final)
        if game.status == 'final':
            tickets.append((game.game_id, s.seat_id, 'unsold', list_price(s, game, 0), None, None, None))
        else:
            tickets.append((game.game_id, s.seat_id, 'available', list_price(s, game, days_until_game_from_asof), None, None, None))

    for days_out, run in pending_orders.values():
        oid = next_order_id()
        sale_day = game.game_date - timedelta(days=days_out)
        ordered_at = random_time(rng, sale_day)
        channel = 'group' if len(run) >= 8 else 'single_game'
        total = 0.0
        for s in run:
            paid = round_price(list_price(s, game, days_out) * rng.uniform(0.97, 1.0), s.level)
            total += paid
            final_list = list_price(s, game, 0 if game.status == 'final' else days_until_game_from_asof)
            tickets.append((game.game_id, s.seat_id, 'sold', final_list, paid, ordered_at, oid))
        orders.append((oid, game.game_id, ordered_at, channel, len(run), round(total, 2)))

    for s in seats:
        if s.seat_id in held:
            tickets.append((game.game_id, s.seat_id, 'held', list_price(s, game, 0 if game.status == 'final' else days_until_game_from_asof), None, None, None))
    return orders, tickets


def build(out: Path, seed: int) -> None:
    rng = random.Random(seed)
    if out.exists():
        out.unlink()
    out.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(out)
    con.executescript(SCHEMA.read_text())
    team_ids = load_teams(con)
    seats = build_seat_map(con, rng)
    games = load_games(con, team_ids)

    counter = {'n': 0}

    def next_order_id():
        counter['n'] += 1
        return counter['n']

    for season_id in SEASONS:
        owners = season_ticket_accounts(seats, rng)       # accounts turn over between seasons
        for g in (g for g in games if g.season_id == season_id):
            orders, tickets = simulate_game(g, seats, owners, rng, next_order_id)
            con.executemany('INSERT INTO orders VALUES (?,?,?,?,?,?)', orders)
            con.executemany(
                'INSERT INTO tickets (game_id, seat_id, status, list_price, sold_price, sold_at, order_id) VALUES (?,?,?,?,?,?,?)',
                tickets,
            )
    con.commit()
    con.execute('ANALYZE')
    con.commit()
    con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=DB_DIR / 'data' / 'bkse.db')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    build(args.out, args.seed)
    logger.info('Wrote {}', args.out)


if __name__ == '__main__':
    main()
