import streamlit as st
import pandas as pd
import random


SHEET_URL = "https://docs.google.com/spreadsheets/d/1nvX2mTrJO49VykgzNtpdpcTmtbIrXmYOjoFD7ro1T54/export?format=csv"

@st.cache_data(ttl=600) # Cache data for 10 minutes
def load_data(url):
    """Function to load data from a Google Sheet."""
    try:
        df = pd.read_csv(url)
        # Drop rows where 'Quiz' or 'Word' is empty to prevent errors
        df.dropna(subset=['Quiz', 'Word', 'Answer'], inplace=True)
        return df
    except Exception as e:
        st.error(f"can not load Google Sheets URL: {e}")
        return None

def setup_question(df):
    """Sets up a new question and choices in the session state."""
    #  DataFrame
    question_row = df.sample(n=1).iloc[0]
    
    st.session_state.question = question_row['Quiz']
    st.session_state.correct_answer_word = question_row['Word']
    st.session_state.full_answer = question_row['Answer']

    # Choices
    correct_answer = st.session_state.correct_answer_word
    
    
    incorrect_words = df[df['Word'] != correct_answer]['Word'].unique()
    
    
    if len(incorrect_words) >= 3:
        choices = random.sample(list(incorrect_words), 3) + [correct_answer]
    else: 
        choices = list(incorrect_words) + [correct_answer]

    random.shuffle(choices)
    st.session_state.choices = choices
    st.session_state.answered = None 

# --- (UI) ---

st.title("B2 Goethe")


data = load_data(SHEET_URL)

if data is not None:
    if 'question' not in st.session_state:
        setup_question(data)

    st.subheader("")
    
    # แสดง "Front-Card" 
    st.markdown(f"### {st.session_state.question}")
    st.write("---")


    st.write(":")
    cols = st.columns(2) # แบ่งเป็น 2 คอลัมน์
    for i, choice in enumerate(st.session_state.choices):
        with cols[i % 2]:
            if st.button(choice, key=f"choice_{i}", use_container_width=True, disabled=(st.session_state.answered is not None)):
                if choice == st.session_state.correct_answer_word:
                    st.session_state.answered = "correct"
                else:
                    st.session_state.answered = "incorrect"
                st.rerun()

    st.write("---")

    
    if st.session_state.answered == "correct":
        st.success(f"yeah! 🎉 '{st.session_state.correct_answer_word}' ")
        st.info(f"**เฉลย**\n\n{st.session_state.full_answer}")
    
    elif st.session_state.answered == "incorrect":
        st.error("failed :(")
        st.info(f"**เฉลย:**\n\n{st.session_state.full_answer}")

    
    if st.session_state.answered:
        if st.button("next! ➡️", use_container_width=True):
            setup_question(data)
            st.rerun()
else:
    st.warning("check google sheet url")
