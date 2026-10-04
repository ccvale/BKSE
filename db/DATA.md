# BKSE ticketing database

A SQLite database of Brooklyn Nets home games at Barclays Center, with a seat-level manifest and one ticket row per seat per game, covering the finished 2025-26 season and the upcoming 2026-27 season.

## What is real and what is synthetic


| Data                                             | Source                                                                     |
| ------------------------------------------------ | -------------------------------------------------------------------------- |
| Team names, conferences, divisions               | Real                                                                       |
| 2025-26 home games, scores, announced attendance | Real (`data/raw/nets_2025_26_home_results.csv`)                            |
| 2026-27 home schedule (40 announced games)       | Real (`data/raw/nets_2026_27_home_schedule.csv`)                           |
| Barclays Center seat map                         | Modeled: real section numbering, approximate rows and seats (17,095 seats) |
| Prices, sales, orders, seat status               | Synthetic, from the pricing model below                                    |


## Tables


| Table      | Rows   | Grain                                                             |
| ---------- | ------ | ----------------------------------------------------------------- |
| `settings` | 3      | key/value (`as_of_date`, `currency`, `data_note`)                 |
| `teams`    | 30     | NBA team                                                          |
| `venues`   | 1      | Barclays Center                                                   |
| `seasons`  | 2      | `2025-26`, `2026-27`                                              |
| `games`    | 80     | Nets home game (opponent = `away_team_id`)                        |
| `sections` | 66     | seating section: 4 courtside, 31 lower (1-31), 31 upper (201-231) |
| `seats`    | 17,095 | physical seat; adjacent `seat_number`s in a row sit together      |
| `orders`   | ~337k  | one purchase (season-ticket account, single-game or group)        |
| `tickets`  | ~1.37M | one seat at one game, with status and price                       |


Ticket `status` values:

- `available`: on sale now at `list_price` (upcoming games only).
- `sold`: has `sold_price`, `sold_at` and `order_id`.
- `held`: not on sale.
- `unsold`: the game is over and the seat never sold.



## Views

- `v_tickets`: tickets joined to game, opponent, section and seat. This is the easiest starting point for most questions.
- `v_available_blocks`: runs of adjacent available seats in the same row, with `seats_in_block`, `first_seat`, `last_seat` and price range. Use it for "N seats together" questions. It takes about 2.5 seconds because it scans all available tickets.



## Seating model


| Level      | Sections                                                            | Rows                                                   | Price levels                                         |
| ---------- | ------------------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------- |
| Courtside  | CS1 (Nets bench side), CS2 (opposite sideline), CS3/CS4 (baselines) | AA-BB, CS2 AA-DD                                       | Courtside Sideline, Courtside Baseline               |
| Lower Bowl | 1-31                                                                | 1-19 (sideline), 1-17 (corner/baseline)                | Lower Sideline Center / Sideline / Corner / Baseline |
| Upper Bowl | 201-231                                                             | 1-20 (center), 1-14 (sideline), 1-10 (corner/baseline) | Upper Sideline Center / Sideline / Corner / Baseline |


Sections 7-9 and 23-25 are center court, and the Nets bench is at section 7. Seats 1 and the last seat in each row are aisle seats. The back row of each baseline section has 4 accessible seats.

## Pricing model (synthetic)

`list_price = seat base × season factor × game demand × dynamic factor`

- **Seat base:** the price level's base price (from $30 for upper baseline to $1,500 for courtside sideline). Prices drop up to 30% toward the back row, aisle seats get +3%, and each seat gets ±4% fixed noise.
- **Season factor:** 1.00 for 2025-26 and 1.05 for 2026-27.
- **Game demand:** opponent draw (Knicks 2.2, Lakers 2.0, Warriors 1.9, Celtics 1.6, down to 0.85) × day of week (Saturday 1.15, Monday 0.92) × home opener 1.25 × holiday week 1.10. 2025-26 demand also fades in March (×0.92) and April (×0.85) to reflect a 20-62 season.
- **Dynamic factor:** as the game nears, prices rise for high-demand games and fall for low-demand ones.
- **Season-ticket accounts:** 2-4 adjacent seats, from 55% of courtside sideline down to 10% of upper corner. They pay 85% of the seat base for every game.
- **Single-game sales:** total sell-through follows announced attendance (2025-26) or demand (2026-27), and expensive or far seats are more likely to go unsold. Orders are adjacent seats, usually 2 or 4. High-demand games sell further ahead.



## Example queries

Cheapest ticket for the next Nets vs Knicks game:

```sql
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
```

Four courtside seats together at the next home game:

```sql
SELECT game_date, opponent, section_code, row_label, first_seat, last_seat, seats_in_block, min_price, max_price
FROM v_available_blocks
WHERE level = 'Courtside' AND seats_in_block >= 4
  AND game_id = (
      SELECT game_id FROM games
      WHERE game_date >= (SELECT value FROM settings WHERE key = 'as_of_date')
      ORDER BY game_date LIMIT 1)
ORDER BY min_price;
```



## Known limits

- Only Nets home games at Barclays Center are included: no away games, no Liberty, no concerts.
- One 2026-27 home game has not been announced yet, and the 2025-26 game log has 40 of the 41 home games.
- Suites, loge boxes and standing room are not modeled.
- There is no resale market and no customer table.

