-- BKSE ticketing database (SQLite)
-- One home venue (Barclays Center), Brooklyn Nets home games for two seasons,
-- a seat-level manifest, and one ticket row per seat per game.
-- Data is synthetic except team names, schedules and 2025-26 results/attendance.

PRAGMA foreign_keys = ON;

-- Key/value settings. 'as_of_date' is "today" for the dataset: use it for
-- "next game", "last month", etc. instead of the real clock.
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE teams (
    team_id      INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,   -- full name, e.g. 'New York Knicks'
    abbreviation TEXT NOT NULL UNIQUE,   -- e.g. 'NYK'
    city         TEXT NOT NULL,          -- e.g. 'New York'
    nickname     TEXT NOT NULL,          -- e.g. 'Knicks'
    conference   TEXT NOT NULL CHECK (conference IN ('East', 'West')),
    division     TEXT NOT NULL
);

CREATE TABLE venues (
    venue_id            INTEGER PRIMARY KEY,
    name                TEXT NOT NULL,
    city                TEXT NOT NULL,
    basketball_capacity INTEGER NOT NULL
);

CREATE TABLE seasons (
    season_id  TEXT PRIMARY KEY,         -- e.g. '2026-27'
    start_date TEXT NOT NULL,            -- ISO date
    end_date   TEXT NOT NULL
);

-- Brooklyn Nets home games only.
CREATE TABLE games (
    game_id          INTEGER PRIMARY KEY,
    season_id        TEXT    NOT NULL REFERENCES seasons(season_id),
    game_date        TEXT    NOT NULL,   -- ISO date, local (ET)
    tip_time_et      TEXT,               -- 'HH:MM' 24h, Eastern
    home_team_id     INTEGER NOT NULL REFERENCES teams(team_id),
    away_team_id     INTEGER NOT NULL REFERENCES teams(team_id),
    venue_id         INTEGER NOT NULL REFERENCES venues(venue_id),
    game_type        TEXT    NOT NULL CHECK (game_type IN ('regular', 'nba_cup')),
    status           TEXT    NOT NULL CHECK (status IN ('scheduled', 'final')),
    home_score       INTEGER,            -- NULL until final
    away_score       INTEGER,
    attendance       INTEGER             -- announced attendance, NULL until final
);
CREATE INDEX idx_games_date ON games(game_date);

-- Price level groups sections that are priced alike.
CREATE TABLE sections (
    section_id   INTEGER PRIMARY KEY,
    venue_id     INTEGER NOT NULL REFERENCES venues(venue_id),
    section_code TEXT    NOT NULL,       -- as printed on the ticket: '8', '224', 'CS1'
    section_name TEXT    NOT NULL,       -- e.g. 'Section 8', 'Courtside Nets Bench Side'
    level        TEXT    NOT NULL CHECK (level IN ('Courtside', 'Lower Bowl', 'Upper Bowl')),
    position     TEXT    NOT NULL CHECK (position IN ('Sideline Center', 'Sideline', 'Corner', 'Baseline')),
    price_level  TEXT    NOT NULL,       -- e.g. 'Courtside Sideline', 'Lower Corner'
    UNIQUE (venue_id, section_code)
);

CREATE TABLE seats (
    seat_id       INTEGER PRIMARY KEY,
    section_id    INTEGER NOT NULL REFERENCES sections(section_id),
    row_label     TEXT    NOT NULL,      -- as printed: '1'..'20', or 'AA'..'DD' courtside
    row_order     INTEGER NOT NULL,      -- 1 = closest to the court within the section
    seat_number   INTEGER NOT NULL,      -- consecutive within a row: adjacent numbers sit together
    is_aisle      INTEGER NOT NULL DEFAULT 0 CHECK (is_aisle IN (0, 1)),
    is_accessible INTEGER NOT NULL DEFAULT 0 CHECK (is_accessible IN (0, 1)),
    UNIQUE (section_id, row_label, seat_number)
);

-- A purchase of one or more tickets to one game.
CREATE TABLE orders (
    order_id     INTEGER PRIMARY KEY,
    game_id      INTEGER NOT NULL REFERENCES games(game_id),
    ordered_at   TEXT    NOT NULL,       -- ISO datetime
    channel      TEXT    NOT NULL CHECK (channel IN ('season_ticket', 'single_game', 'group')),
    quantity     INTEGER NOT NULL,
    total_amount REAL    NOT NULL        -- USD, sum of tickets.sold_price
);
CREATE INDEX idx_orders_game ON orders(game_id);

-- One row per seat per game: the game's full inventory.
--   available: on sale now at list_price
--   sold:      sold_price / sold_at / order_id are set
--   held:      not on sale (team, league or production holds)
--   unsold:    game is final and the seat never sold
CREATE TABLE tickets (
    ticket_id   INTEGER PRIMARY KEY,
    game_id     INTEGER NOT NULL REFERENCES games(game_id),
    seat_id     INTEGER NOT NULL REFERENCES seats(seat_id),
    status      TEXT    NOT NULL CHECK (status IN ('available', 'sold', 'held', 'unsold')),
    list_price  REAL    NOT NULL,        -- USD per ticket: current price, or final price if the game is over
    sold_price  REAL,                    -- USD actually paid; NULL unless sold
    sold_at     TEXT,                    -- ISO datetime; NULL unless sold
    order_id    INTEGER REFERENCES orders(order_id),
    UNIQUE (game_id, seat_id)
);
CREATE INDEX idx_tickets_game_status ON tickets(game_id, status);
CREATE INDEX idx_tickets_order ON tickets(order_id);

-- Flattened ticket view: the easiest place to answer most questions.
CREATE VIEW v_tickets AS
SELECT
    t.ticket_id,
    g.game_id,
    g.season_id,
    g.game_date,
    g.tip_time_et,
    g.game_type,
    g.status          AS game_status,
    opp.name          AS opponent,
    opp.abbreviation  AS opponent_abbr,
    s.section_code,
    s.level,
    s.position,
    s.price_level,
    st.row_label,
    st.row_order,
    st.seat_number,
    st.is_aisle,
    st.is_accessible,
    t.status,
    t.list_price,
    t.sold_price,
    t.sold_at,
    t.order_id
FROM tickets t
JOIN games    g   ON g.game_id    = t.game_id
JOIN teams    opp ON opp.team_id  = g.away_team_id
JOIN seats    st  ON st.seat_id   = t.seat_id
JOIN sections s   ON s.section_id = st.section_id;

-- Runs of adjacent available seats (same game, section and row, consecutive
-- seat numbers). Use for "N seats together" questions: filter seats_in_block >= N.
CREATE VIEW v_available_blocks AS
WITH avail AS (
    SELECT
        t.game_id,
        st.section_id,
        st.row_label,
        st.row_order,
        st.seat_number,
        t.list_price,
        st.seat_number - ROW_NUMBER() OVER (
            PARTITION BY t.game_id, st.section_id, st.row_label
            ORDER BY st.seat_number
        ) AS grp
    FROM tickets t
    JOIN seats st ON st.seat_id = t.seat_id
    WHERE t.status = 'available'
)
SELECT
    a.game_id,
    g.game_date,
    opp.name               AS opponent,
    s.section_code,
    s.level,
    s.position,
    s.price_level,
    a.row_label,
    a.row_order,
    MIN(a.seat_number)     AS first_seat,
    MAX(a.seat_number)     AS last_seat,
    COUNT(*)               AS seats_in_block,
    MIN(a.list_price)      AS min_price,
    MAX(a.list_price)      AS max_price
FROM avail a
JOIN games    g   ON g.game_id    = a.game_id
JOIN teams    opp ON opp.team_id  = g.away_team_id
JOIN sections s   ON s.section_id = a.section_id
GROUP BY a.game_id, a.section_id, a.row_label, a.grp;
