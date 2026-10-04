"""Streamlit UI for asking natural-language questions of the ticketing database."""

# super simple, expand on this

import streamlit as st
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

st.set_page_config(page_title='BKSE Ticketing NLQ Agent', page_icon='🏀')
st.title('🏀 BKSE Ticketing NLQ Agent')
st.caption('Ask plain-English questions about Brooklyn Nets ticket sales and pricing.')

question = st.text_input('Your question', placeholder='e.g. How many tickets were sold last month?')

if st.button('Ask', type='primary') and question.strip():
    with st.spinner("Thinking..."):
        try:
            # will be something like: answer = run_agent(question)
            # st.success(result['answer'])
            # if result['sql']:
            #     with st.expander('Generated SQL'):
            #         st.code(result['sql'], language='sql')
        except Exception:
            logger.exception('NLQ request failed')
            st.error('Something went wrong. Check the logs.')
