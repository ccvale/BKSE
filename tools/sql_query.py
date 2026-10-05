'''Run a read-only query and cap how many rows come back.'''

import sqlite3
from pathlib import Path

from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_core.tools import tool
from loguru import logger

DB_PATH = Path(__file__).resolve().parent.parent / 'db' / 'data' / 'bkse.db'
MAX_ROWS = 20


@tool('sql_db_query')
def sql_query(query: str) -> str:
    '''Execute one SELECT or WITH query and return the rows.

    At most 20 rows come back. If the query is wrong, an error is returned.
    If a column does not exist, call sql_db_schema and use the names it returns.
    '''
    statement = query.strip().lower()
    if not statement.startswith('select') and not statement.startswith('with'):
        logger.warning('Blocked a query that is not a SELECT')
        return 'Error: only SELECT queries are allowed.'
    try:
        # connect to the database in read-only mode
        with sqlite3.connect(f'file:{DB_PATH.as_posix()}?mode=ro', uri=True) as con:
            # one extra row tells us the result was cut off
            rows = con.execute(query).fetchmany(MAX_ROWS + 1)
    # if the query is not a SELECT or WITH query, return an error
    except sqlite3.Error as exc:
        logger.warning('Query failed: {}', exc)
        return f'Error: {exc}'
    if not rows: # if there are no rows, say so instead of returning silence
        return 'No rows.'
    text = str(rows[:MAX_ROWS]) # get the first MAX_ROWS rows
    if len(rows) > MAX_ROWS: # if there are more rows than the limit, add a message saying so
        text += f'\nOnly the first {MAX_ROWS} rows are shown. Use COUNT or SUM instead of selecting every row.'
    return text


class ReadOnlyToolkit(SQLDatabaseToolkit):
    '''Uses our modified sql_query in place of the default query tool.'''

    def get_tools(self):
        tools = super().get_tools()
        return [sql_query if item.name == 'sql_db_query' else item for item in tools] # replace the default query tool with our modified one


if __name__ == '__main__':
    wide = sql_query.invoke({'query': 'SELECT ticket_id FROM tickets'})
    total = sql_query.invoke({'query': 'SELECT COUNT(ticket_id) FROM tickets'})
    cte = sql_query.invoke({'query': 'WITH x AS (SELECT 1 AS n) SELECT n FROM x'})
    empty = sql_query.invoke({'query': 'SELECT 1 WHERE 1 = 0'})
    blocked = sql_query.invoke({'query': 'DELETE FROM games'})
    write_cte = sql_query.invoke({'query': 'WITH x AS (SELECT 1) DELETE FROM games'})
    assert str(MAX_ROWS) in sql_query.description
    assert f'Only the first {MAX_ROWS} rows' in wide
    assert '1384695' in total
    assert empty == 'No rows.'
    assert '(1,)' in cte
    assert blocked == 'Error: only SELECT queries are allowed.'
    assert write_cte.startswith('Error:')
    logger.info(total)
