'''Streamlit UI for asking natural-language questions of the ticketing database.'''

from datetime import date

from anthropic import APIConnectionError, AuthenticationError, InternalServerError, PermissionDeniedError, RateLimitError
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from loguru import logger
import streamlit as st

from agent import agent

load_dotenv()

# configuration settings
st.set_page_config(page_title='Brooklyn Nets Ticketing Agent', page_icon='🏀')
st.title('🏀 Brooklyn Nets Ticketing Agent')
st.caption('Ask questions about Brooklyn Nets ticket sales, pricing, and scheduling.')


@st.cache_resource # caching such that we don't re-initialize the agent for each new chat
def get_agent():
    '''Keeps one agent for the life of the Streamlit process.'''
    return agent()

# function to format the response for the user
def for_user(content):
    '''Drops raw query rows if the model copies them into the answer. This is to prevent the model from returning too much information that is not relevant to the user.'''
    # claude often returns a list of content blocks instead of a string, so we need to convert it to a string
    text = content if isinstance(content, str) else AIMessage(content=content).text
    for marker in ('Query results:', 'Saved rows for the next question only:'):
        if marker in text:
            text = text.split(marker)[0]
    return text.strip()


def for_user_error(exc):
    '''Turns a failed request into a short message for the chat.'''
    for item in (exc, exc.__cause__):
        if item is None:
            continue
        if isinstance(item, TypeError) and 'ANTHROPIC_API_KEY' in str(item):
            return 'The model did not answer. Check the ANTHROPIC_API_KEY in your .env file and restart the app.'
        if isinstance(item, (AuthenticationError, PermissionDeniedError)):
            return 'The model did not answer. Check the ANTHROPIC_API_KEY in your .env file and restart the app.'
        if isinstance(item, (APIConnectionError, RateLimitError, InternalServerError)):
            return 'The model did not answer. Try again in a moment. If the problem persists, restart the app.'
    return 'That question was not answered. Try again.'


def show_message(message):
    '''Draws one chat bubble, including the SQL when this reply ran a query.'''
    with st.chat_message(message.type):
        # streamlit reads $...$ as LaTeX, which breaks prices
        st.markdown(for_user(message.content).replace('$', '\\$'))
        # parsing for the SQL query tag if exists (some questions don't yield a SQL query)
        sql = message.additional_kwargs.get('sql')
        if sql:
            # show the SQL query in a hideable component that can be expanded to show the details
            with st.expander('Generated SQL'):
                st.code(sql, language='sql')

# initialize the messages list if it doesn't exist
if 'messages' not in st.session_state:
    st.session_state.messages = []

# show the messages in the chat
for message in st.session_state.messages:
    show_message(message)

# add the chatbar and buttom at the end of the chat
with st.bottom:
    question_col, reset_col = st.columns([6, 1], vertical_alignment='center')
    with question_col:
        question = st.chat_input('e.g. How many tickets were sold last month?')
    with reset_col:
        new_chat = st.button('New chat', disabled=not st.session_state.messages)

# new chat button clicked - we restart state and rerun
if new_chat:
    st.session_state.messages = []
    st.rerun()

# if the user didn't enter a question, stop
if not question:
    st.stop()

# the history is the list of messages that the agent has seen and responded to
history = []
for message in st.session_state.messages:
    data = message.additional_kwargs.get('data')
    if data:
        history.append(AIMessage(content=f'{message.content}\n\nSaved rows for the next question only: {data}'))
    else:
        history.append(message)

# add the user's message to the history
user_message = HumanMessage(content=question)
st.session_state.messages.append(user_message)
show_message(user_message)

# on asking an agent a question, the agent invokes, and a result is returned
try:
    with st.spinner('Thinking...'):
        result = get_agent().invoke({
            'input': f'Today is {date.today().isoformat()}.\n{question}',
            'chat_history': history,
        })
except FileNotFoundError as exc:
    logger.exception('NLQ request failed')
    st.error(str(exc))
    st.stop()
except Exception as exc:
    logger.exception('NLQ request failed')
    st.error(for_user_error(exc))
    st.stop()

# the answer is the response from the agent
answer = for_user(result['output'])

# the queries are the SQL queries that the agent ran
queries = []

# the rows are the rows that the agent returned
rows = []

for action, observation in result.get('intermediate_steps', []):
    # if the action is not a SQL query, or the tool input is not a dictionary, skip
    if action.tool != 'sql_db_query' or not isinstance(action.tool_input, dict):
        continue
    query = action.tool_input.get('query', '')
    # if the query is not empty, add it to the list of queries
    if query:
        queries.append(query)
    if observation:
        rows.append(str(observation))
# create the reply message with the SQL query and the rows
reply = AIMessage(
    content=answer,
    additional_kwargs={'sql': '\n\n'.join(queries), 'data': '\n\n'.join(rows)},
)
show_message(reply)
# add the reply to the messages list
st.session_state.messages.append(reply)