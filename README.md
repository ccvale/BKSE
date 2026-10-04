# BKSE — Brooklyn Nets NLQ agent

Ask plain-English questions about Brooklyn Nets home-game ticketing. The agent writes SQL against a SQLite database, runs it, and answers in plain English with the SQL shown for transparency.

## Goal

Non-technical staff need to find things in the data we have on Nets home games: seating, ticketing, and scheduling. The agent should give up-to-date ticket availability and pricing, and help with related questions, without anyone needing to write SQL.

## Dataset

Real schedules and 2025-26 results, a modeled Barclays Center seat map, and synthetic prices and sales. The seat map is based on the Barclays Center seating chart, and the 2026-27 home schedule is the announced Nets schedule. Schema, pricing model, and known limits are in [db/DATA.md](db/DATA.md).

```bash
uv run python db/build_db.py
```



## Approach

Follows LangChain's [SQL agent pattern](https://docs.langchain.com/oss/python/langchain/sql-agent): the model sees the schema, writes a query, runs it through a SQL tool, reads the result, and answers.

Alternatives considered:

- **RAG over table metadata:** useful for large schemas. This schema is small enough to put in the prompt.
- **Agentic tool calls:** this is what the SQL agent does.
- **MCP connector:** expose the same tools to an existing client such as Claude, so the client can call them mid-conversation. Worth revisiting if the goal shifts from a standalone app to a client integration.

The interface is a simple Streamlit app. Users chat with the agent, and earlier messages stay in context so follow-ups work. Responses stream as the model produces them.

Example of a follow-up that depends on memory:

> When do the Nets play the Knicks next?
>
> What's the cheapest ticket that night?

The second question should be answered directly from the first, not returned as "I can't tell."

Single-game and season-ticket purchases are out of scope for the agent. Those requests get pointed to a BKSE representative or Ticketmaster.

## Model



## Safety

Two layers, one in the prompt and one in code:

- **Read-only connection:** SQLite opened with `mode=ro`, so writes fail at the database level. 
- **SELECT-only:** the prompt instructs read-only queries, and code rejects anything else. 
- **Output limits:** row cap on results returned to the model, so large results can't flood the context. 
- **Out-of-scope purchases:** single-game and season-ticket requests are directed to a BKSE representative or Ticketmaster.



## Setup

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Put an Anthropic API key in `.env` as `ANTHROPIC_API_KEY`. 

Build the database (writes `data/bkse.db`):

```bash
uv run python db/build_db.py
```



## Run

```bash
uv run streamlit run app.py
```



## Usage



## Tradeoffs and known issues



## Next steps

- **Role-based access:** tie access to Microsoft Entra ID, so leadership, developers, and accounting each see the data they need and no more. Different roles have different needs, and the agent is most useful when it serves each one.
- **Chat memory and streaming:** described above, not yet built.
- **MCP connector:** expose the same tools so existing clients can call them.
- **Smart ticket prompting:** provide the user the direct link to purchase tickets for a game they have inquired about. Not worth implementing in this example, but something that would enhance the user experience in production.



## AI tools used

- Claude helped develop the database structure and build script, and researched the Barclays Center seating layout and home schedule. This was the bulk of the time-consuming setup work.
- Cursor (Plan Mode) was used to discuss implementation. Outside of autocomplete and one-off debugging fixes, the agent layer was written by hand with reference to the LangChain documentation.
- The Streamlit app was written by hand referencing the documentation for that as well.

