# BKSE ticketing database

SQLite database of the full Brooklyn Nets schedule for 2025-26 and 2026-27. Ticket rows exist only for home games at Barclays Center, one per seat. Prices and availability are a snapshot as of 2026-10-28.

## Real and synthetic

| Data | Source |
| --- | --- |
| Team names | Real |
| 2025-26 schedule and results (82 games) | Real, `data/raw/nets_2025_26_games.csv` |
| 2026-27 schedule (80 announced games, 40 home) | Real, `data/raw/nets_2026_27_games.csv` |
| 2026-27 results through 2026-10-27 (4 games) | Real, same file. Later rows have no score |
| Seat map (17,095 seats) | Modeled from real section numbers |
| Prices, sales, orders, seat status | Synthetic |

## Build

`build_db.py` replaces `db/data/bkse.db`. It applies `schema.sql`, then fills the tables. The default seed is 42. `--out` and `--seed` change the file and the random draws.

Teams are the 30 NBA clubs. The seat map is generated from the section layout in the script: courtside, lower bowl 1-31, upper bowl 201-231. Each seat gets a base price from its location, with a small random wobble.

Games are loaded from the two CSVs. `is_home` is 1 at Barclays and 0 on the road. A row with a score becomes a final game. A 2026-27 row without a score stays scheduled. Each home game then gets a demand score from the opponent, the weekday, the home opener, and the holiday week. 2025-26 demand also drops in March and April. Road games are not priced.

For each season, adjacent seats are assigned to season-ticket accounts. Each home game is then simulated. A few non-season seats are held off sale. Season seats sell at a fixed discount. Other seats are sold or left open so final home games track announced attendance and scheduled home games track demand. A purchase dated before 2026-10-28 is `sold`. A future seat still open is `available`. A past seat that never sold is `unsold`. Adjacent seats bought together become one order: season ticket, single game, or group. Road games get no orders and no tickets.

## Tables

| Table | Rows | Grain |
| --- | --- | --- |
| `teams` | 30 | NBA team, including the Nets |
| `seasons` | 2 | `2025-26`, `2026-27` |
| `games` | 162 | One Nets game, home or road. Opponent is `opponent_team_id`. `is_home = 1` is Barclays |
| `sections` | 66 | 4 courtside, lower 1-31, upper 201-231 |
| `seats` | 17,095 | One physical seat. Adjacent `seat_number`s sit together |
| `orders` | ~344k | One purchase: season ticket, single game, or group |
| `tickets` | ~1.38M | One seat at one home game. Road games are absent |

Ticket status: `available` (on sale at `list_price`), `sold` (`sold_price`, `sold_at`, `order_id`), `held` (not on sale), `unsold` (final game, never sold).

## Views

`v_tickets` joins ticket, game, opponent, section, and seat, and keeps `is_home = 1`. Price is `list_price`, section is `section_code`, row is `row_label`, seat is `seat_number`.

`v_available_blocks` is a run of adjacent available seats in one row, also home games only. Filter on `seats_in_block`. `first_seat`, `last_seat`, `seats_in_block`, `min_price`, and `max_price` are CAST to a type. Without that, the schema tool drops them.

## Seating

Courtside is CS1-CS4. CS1 is the Nets bench side (sections 7-9). Lower bowl is 1-31, upper bowl is 201-231. Sections 7-9 and 23-25 are center court. Seat 1 and the last seat in a row are aisles. The back row of each baseline section has 4 accessible seats.

## Pricing

`list_price = seat base × season factor × game demand × dynamic factor`

Seat base runs from $30 (upper baseline) to $1,500 (courtside sideline) and falls toward the back row. 2026-27 is 1.05× 2025-26. Demand is opponent draw (Knicks 2.2 down to 0.85), day of week, home opener (1.25), and holiday week (1.10). 2025-26 demand fades in March and April. Prices drift as the game nears. Season accounts hold 2-4 seats, from 55% of courtside sideline to 10% of upper corner, and pay 85% of the seat base. Single-game sell-through follows announced Barclays attendance for a final home game and demand while that home game is still scheduled.

## Limits

- Tickets are Barclays home games only. The schedule includes road games. No Liberty games or concerts.
- 2026-27 has 80 announced games. One home date and one road date are still unannounced. 2025-26 is the full 82-game slate.
- Tip times are Eastern, 24-hour. `game_type` is `nba_cup` for Cup games at home and on the road.
- No suites, standing room, resale, or customers.
