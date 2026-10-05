# BKSE ticketing database

SQLite database of Brooklyn Nets home games at Barclays Center for 2025-26 and 2026-27. One ticket row per seat per game. Prices and availability are a snapshot as of 2026-10-01.

## Real and synthetic

| Data | Source |
| --- | --- |
| Team names | Real |
| 2025-26 home results and attendance (41 games) | Real, `data/raw/nets_2025_26_home_results.csv` |
| 2026-27 home schedule (40 announced games) | Real, `data/raw/nets_2026_27_home_schedule.csv` |
| Seat map (17,095 seats) | Modeled from real section numbers |
| Prices, sales, orders, seat status | Synthetic |

## Build

`build_db.py` replaces `db/data/bkse.db`. It applies `schema.sql`, then fills the tables. The default seed is 42. `--out` and `--seed` change the file and the random draws.

Teams are the 30 NBA clubs. The seat map is generated from the section layout in the script: courtside, lower bowl 1-31, upper bowl 201-231. Each seat gets a base price from its location, with a small random wobble.

Games are loaded from the two CSVs. A 2025-26 row becomes a final game with score, attendance, tip time, and game type. A 2026-27 row becomes a scheduled game with a tip time. Each game then gets a demand score from the opponent, the weekday, the home opener, and the holiday week. 2025-26 demand also drops in March and April.

For each season, adjacent seats are assigned to season-ticket accounts. Each game is then simulated. A few non-season seats are held off sale. Season seats sell at a fixed discount. Other seats are sold or left open so 2025-26 tracks announced attendance and 2026-27 tracks demand. A purchase dated before 2026-10-01 is `sold`. A future seat still open is `available`. A past seat that never sold is `unsold`. Adjacent seats bought together become one order: season ticket, single game, or group.

## Tables

| Table | Rows | Grain |
| --- | --- | --- |
| `teams` | 30 | NBA team, including the Nets |
| `seasons` | 2 | `2025-26`, `2026-27` |
| `games` | 81 | Nets home game. Opponent is `away_team_id` |
| `sections` | 66 | 4 courtside, lower 1-31, upper 201-231 |
| `seats` | 17,095 | One physical seat. Adjacent `seat_number`s sit together |
| `orders` | ~344k | One purchase: season ticket, single game, or group |
| `tickets` | ~1.38M | One seat at one game |

Ticket status: `available` (on sale at `list_price`), `sold` (`sold_price`, `sold_at`, `order_id`), `held` (not on sale), `unsold` (final game, never sold).

## Views

`v_tickets` joins ticket, game, opponent, section, and seat. Price is `list_price`, section is `section_code`, row is `row_label`, seat is `seat_number`.

`v_available_blocks` is a run of adjacent available seats in one row. Filter on `seats_in_block`. `first_seat`, `last_seat`, `seats_in_block`, `min_price`, and `max_price` are CAST to a type. Without that, the schema tool drops them.

## Seating

Courtside is CS1-CS4. CS1 is the Nets bench side (sections 7-9). Lower bowl is 1-31, upper bowl is 201-231. Sections 7-9 and 23-25 are center court. Seat 1 and the last seat in a row are aisles. The back row of each baseline section has 4 accessible seats.

## Pricing

`list_price = seat base × season factor × game demand × dynamic factor`

Seat base runs from $30 (upper baseline) to $1,500 (courtside sideline) and falls toward the back row. 2026-27 is 1.05× 2025-26. Demand is opponent draw (Knicks 2.2 down to 0.85), day of week, home opener (1.25), and holiday week (1.10). 2025-26 demand fades in March and April. Prices drift as the game nears. Season accounts hold 2-4 seats, from 55% of courtside sideline to 10% of upper corner, and pay 85% of the seat base. Single-game sell-through follows announced attendance in 2025-26 and demand in 2026-27.

## Limits

- Home games only. No away games, Liberty games, or concerts.
- One 2026-27 home date is not announced. 2025-26 is the full 41-game home slate.
- Tip times are Eastern, 24-hour. Two 2025-26 home games are NBA Cup: 2025-11-07 Detroit and 2025-11-28 Philadelphia.
- No suites, standing room, resale, or customers.
