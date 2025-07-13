import streamlit as st
import pandas as pd
import random
import os
import json

# URL ของ Google Sheet ของคุณ
SHEET_URL = "https://docs.google.com/spreadsheets/d/1nvX2mTrJO49VykgzNtpdpcTmtbIrXmYOjoFD7ro1T54/export?format=csv"

# ไฟล์สำหรับเก็บสถานะผู้ใช้และคำถาม (จะถูกสร้างในโฟลเดอร์เดียวกับสคริปต์นี้)
USER_DATA_FILE = 'user_data.json'

def load_user_data():
    """Load user-specific quiz data from JSON file."""
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                st.error("Error decoding user_data.json. Starting with empty data.")
                return {}
    return {}

def save_user_data(data):
    """Save user-specific quiz data to JSON file."""
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

@st.cache_data(ttl=600) # Cache data for 10 minutes
def load_data(url):
    """Function to load data from a Google Sheet."""
    try:
        df = pd.read_csv(url)
        df.dropna(subset=['Quiz', 'Word', 'Answer', 'Lektion'], inplace=True)
        df['Unique_ID'] = df['Quiz'] + "::" + df['Word']
        df['Status'] = 'not started yet'
        df['Richtig Count'] = 0
        df['False Count'] = 0
        return df
    except Exception as e:
        st.error(f"Cannot load Google Sheets URL: {e}. Please ensure the URL is correct and accessible.")
        return None

def initialize_quiz_data(df_base, username):
    """
    Initializes or loads quiz data for the current user, merging with the loaded Google Sheet data.
    If username is 'Guest', it always returns a fresh DataFrame without saving.
    """
    if df_base is None or df_base.empty: 
        return pd.DataFrame() 

    df_copy = df_base.copy()

    df_copy['Richtig Count'] = pd.to_numeric(df_copy['Richtig Count'], errors='coerce').fillna(0).astype(int)
    df_copy['False Count'] = pd.to_numeric(df_copy['False Count'], errors='coerce').fillna(0).astype(int)

    if username == "Faeng": # Only Faeng's data is persistent
        user_data = load_user_data()
        if username not in user_data:
            user_data[username] = {}

        for index, row in df_copy.iterrows():
            unique_id = row['Unique_ID']
            if unique_id not in user_data[username]:
                user_data[username][unique_id] = {
                    'Status': 'not started yet',
                    'Richtig Count': 0,
                    'False Count': 0
                }
            
            quiz_progress = user_data[username][unique_id]
            
            df_copy.loc[index, 'Status'] = quiz_progress.get('Status', 'not started yet')
            df_copy.loc[index, 'Richtig Count'] = int(quiz_progress.get('Richtig Count', 0))
            df_copy.loc[index, 'False Count'] = int(quiz_progress.get('False Count', 0))

        save_user_data(user_data)
        st.session_state.user_quiz_data[username] = user_data[username]
    else: # Guest or any other user - data is not loaded/saved persistently
        for index, row in df_copy.iterrows():
            df_copy.loc[index, 'Status'] = 'not started yet'
            df_copy.loc[index, 'Richtig Count'] = 0
            df_copy.loc[index, 'False Count'] = 0
        st.session_state.user_quiz_data[username] = {}
        
    return df_copy

def update_quiz_progress(unique_id, is_correct, username):
    """
    Updates the progress for a specific quiz item for the current user and saves it.
    Guest's progress is only stored in session state, not to file.
    """
    if username == "Faeng":
        user_data = load_user_data()
        
        if username not in user_data:
            user_data[username] = {}
        if unique_id not in user_data[username]:
            user_data[username][unique_id] = {'Status': 'not started yet', 'Richtig Count': 0, 'False Count': 0}

        current_progress = user_data[username][unique_id]

        if is_correct:
            current_progress['Richtig Count'] = int(current_progress.get('Richtig Count', 0)) + 1
        else:
            current_progress['False Count'] = int(current_progress.get('False Count', 0)) + 1
        
        current_progress['Status'] = 'done' 

        user_data[username][unique_id] = current_progress
        save_user_data(user_data)
        st.session_state.user_quiz_data[username][unique_id] = current_progress
    else: # Guest's progress - update only in session state
        if username not in st.session_state.user_quiz_data:
            st.session_state.user_quiz_data[username] = {}
        if unique_id not in st.session_state.user_quiz_data[username]:
            st.session_state.user_quiz_data[username][unique_id] = {'Status': 'not started yet', 'Richtig Count': 0, 'False Count': 0}
        
        current_progress = st.session_state.user_quiz_data[username][unique_id]
        if is_correct:
            current_progress['Richtig Count'] += 1
        else:
            current_progress['False Count'] += 1
        current_progress['Status'] = 'done'


def get_filtered_sorted_questions(df_with_progress, sort_option, lektion_filter):
    """
    Filters and sorts the DataFrame based on user's selected options.
    Receives df_with_progress which already includes user-specific counts and status.
    """
    if df_with_progress.empty:
        return pd.DataFrame()

    filtered_df = df_with_progress.copy()

    if lektion_filter and lektion_filter != "All":
        filtered_df = filtered_df[filtered_df['Lektion'] == lektion_filter]

    filtered_df['False Count'] = pd.to_numeric(filtered_df['False Count'], errors='coerce').fillna(0).astype(int)
    filtered_df['Richtig Count'] = pd.to_numeric(filtered_df['Richtig Count'], errors='coerce').fillna(0).astype(int)

    if sort_option == "Not Started Yet":
        not_started = filtered_df[filtered_df['Status'] == 'not started yet']
        if not not_started.empty:
            filtered_df = not_started
        else:
            questions_to_review = filtered_df[filtered_df['False Count'] > 0]
            if not questions_to_review.empty:
                filtered_df = questions_to_review.sort_values(by='False Count', ascending=False)
            
    elif sort_option == "False Count > 0":
        questions_to_review_specific = filtered_df[(filtered_df['False Count'] > 0) & (filtered_df['Richtig Count'] == 0)]
        
        if not questions_to_review_specific.empty:
            filtered_df = questions_to_review_specific.sort_values(by='False Count', ascending=False)
        else:
            questions_with_any_false = filtered_df[filtered_df['False Count'] > 0]
            if not questions_with_any_false.empty:
                filtered_df = questions_with_any_false.sort_values(by='False Count', ascending=False)
            else:
                fallback_df = df_with_progress.copy() 
                if lektion_filter and lektion_filter != "All":
                    fallback_df = fallback_df[fallback_df['Lektion'] == lektion_filter]
                filtered_df = fallback_df
                st.info(f"No questions with 'False Count > 0' (and Richtig Count = 0) found for Lektion '{lektion_filter if lektion_filter != 'All' else 'All'}'. Displaying random questions from this filter.")

    elif sort_option == "By Lektion":
        filtered_df = filtered_df.sort_values(by='Lektion')

    return filtered_df

def setup_question(df_base_original, username, sort_option, lektion_filter):
    """
    Sets up a new question and choices based on filters and sort option.
    df_base_original is the original DataFrame from Google Sheet (without user progress).
    """
    if df_base_original is None or df_base_original.empty: 
        st.session_state.question = "No data loaded. Please check the Google Sheet URL."
        st.session_state.choices = []
        st.session_state.answered = None
        st.session_state.correct_answer_word = ""
        st.session_state.full_answer = ""
        st.session_state.current_quiz_id = ""
        return

    df_with_progress_for_selection = initialize_quiz_data(df_base_original, username)

    filtered_sorted_df = get_filtered_sorted_questions(df_with_progress_for_selection, sort_option, lektion_filter)

    if filtered_sorted_df.empty:
        st.session_state.question = "No questions match your current filters. Try different options."
        st.session_state.choices = []
        st.session_state.answered = None
        st.session_state.correct_answer_word = ""
        st.session_state.full_answer = ""
        st.session_state.current_quiz_id = ""
        return

    question_row = filtered_sorted_df.sample(n=1).iloc[0]

    st.session_state.question = question_row['Quiz']
    st.session_state.correct_answer_word = question_row['Word']
    st.session_state.full_answer = question_row['Answer']
    st.session_state.current_quiz_id = question_row['Unique_ID']
    
    correct_answer = st.session_state.correct_answer_word
    
    incorrect_words_pool = df_base_original[df_base_original['Word'] != correct_answer]['Word'].unique().tolist()
    
    if correct_answer in incorrect_words_pool: 
        incorrect_words_pool.remove(correct_answer)

    if len(incorrect_words_pool) >= 3:
        choices = random.sample(incorrect_words_pool, 3) + [correct_answer]
    else:
        choices = incorrect_words_pool + [correct_answer]

    random.shuffle(choices)
    st.session_state.choices = choices
    st.session_state.answered = None

# --- Streamlit UI ---

st.set_page_config(layout="centered", page_title="B2 Goethe Quiz")
st.title("B2 Goethe Quiz 🇩🇪")

# Initialize 'data_base' as the base data from Google Sheet, which will be the source for details
data_base = load_data(SHEET_URL) 

if data_base is None or data_base.empty:
    st.warning("Could not load quiz data. Please check the Google Sheet URL and ensure it contains data.")
    st.stop() 

# --- Login Section ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None

# Show "Who to play" only if not logged in
if not st.session_state.logged_in:
    st.subheader("Who to play?")
    col_faeng, col_guest = st.columns(2)

    with col_faeng:
        if st.button("Faeng"):
            st.session_state.logged_in = True
            st.session_state.username = "Faeng"
            st.success("Logged in as Faeng! Welcome back! 🎉")
            st.rerun()
    with col_guest:
        if st.button("Guest"):
            st.session_state.logged_in = True
            st.session_state.username = "Guest"
            st.success("Logged in as Guest! Viel Erfolg beim Lernen! 📚")
            st.rerun()
else: # If logged in, show current user and logout option
    st.sidebar.success(f"Logged in as: **{st.session_state.username}**")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.clear() 
        st.rerun()

    # --- Quiz Application ---
    # 'data_for_quiz_logic' will be the DataFrame with user progress, initialized once per session/user
    if 'user_quiz_data' not in st.session_state or \
       st.session_state.get('user_quiz_data_loaded_for_user') != st.session_state.username:
        
        st.session_state.user_quiz_data = {} 
        # Pass the base data to initialize_quiz_data
        data_for_quiz_logic = initialize_quiz_data(data_base, st.session_state.username) 
        st.session_state.user_quiz_data_loaded_for_user = st.session_state.username
    else:
        # If already initialized, ensure 'data_for_quiz_logic' is the one with current user progress
        data_for_quiz_logic = initialize_quiz_data(data_base, st.session_state.username)


    # --- Filter and Sort Options in Sidebar ---
    st.sidebar.subheader("Filter & Sort Options")
    all_lektions = ["All"] + sorted(data_base['Lektion'].unique().tolist()) # Use data_base for overall lektions
    lektion_filter = st.sidebar.selectbox("Filter by Lektion", all_lektions, key='lektion_filter')
    sort_option = st.sidebar.selectbox(
        "Sort Questions By",
        ("Random", "Not Started Yet", "False Count > 0", "By Lektion"),
        key='sort_option'
    )
    
    # --- Display Quiz Progress Summary in Sidebar ---
    st.sidebar.subheader("Quiz Progress Summary")
    user_specific_data_for_display = st.session_state.user_quiz_data.get(st.session_state.username, {})
    
    total_quizzes_in_sheet = len(data_base['Unique_ID'].unique()) 
    
    done_quizzes = 0
    total_richtig = 0
    total_false = 0
    
    for unique_id_in_sheet in data_base['Unique_ID'].unique():
        if unique_id_in_sheet in user_specific_data_for_display:
            q_data = user_specific_data_for_display[unique_id_in_sheet]
            if q_data.get('Status') == 'done':
                done_quizzes += 1
            total_richtig += q_data.get('Richtig Count', 0)
            total_false += q_data.get('False Count', 0)

    st.sidebar.write(f"Total Quizzes: **{total_quizzes_in_sheet}**")
    st.sidebar.write(f"Completed: **{done_quizzes}**")
    st.sidebar.write(f"Remaining: **{total_quizzes_in_sheet - done_quizzes}**")
    st.sidebar.write(f"Total Correct Answers: **{total_richtig}**")
    st.sidebar.write(f"Total False Answers: **{total_false}**")


    # --- Setup Question Logic ---
    if data_base is not None and not data_base.empty: 
        if 'question' not in st.session_state or \
           st.session_state.get('current_user_for_question_setup') != st.session_state.username or \
           st.session_state.get('current_sort_option') != sort_option or \
           st.session_state.get('current_lektion_filter') != lektion_filter:
            
            # Use data_for_quiz_logic (which has user progress) for question selection
            setup_question(data_base, st.session_state.username, sort_option, lektion_filter) 
            st.session_state.current_user_for_question_setup = st.session_state.username
            st.session_state.current_sort_option = sort_option
            st.session_state.current_lektion_filter = lektion_filter
    else:
        st.error("Quiz data not available. Please check the Google Sheet link.")

    # --- Display Current Question ---
    current_lektion_display = 'N/A'
    if st.session_state.current_quiz_id and not data_base.empty and not data_base[data_base['Unique_ID'] == st.session_state.current_quiz_id].empty:
        current_lektion_display = data_base[data_base['Unique_ID'] == st.session_state.current_quiz_id]['Lektion'].iloc[0]
    
    st.subheader(f"Lektion: {current_lektion_display}")
    
    st.markdown(f"### {st.session_state.question}")
    st.write("---")

    st.write(":") 
    cols = st.columns(2) 

    if st.session_state.choices: 
        for i, choice in enumerate(st.session_state.choices):
            with cols[i % 2]: 
                if st.button(choice, key=f"choice_{i}", use_container_width=True, disabled=(st.session_state.answered is not None)):
                    if choice == st.session_state.correct_answer_word:
                        st.session_state.answered = "correct"
                        update_quiz_progress(st.session_state.current_quiz_id, True, st.session_state.username)
                    else:
                        st.session_state.answered = "incorrect"
                        update_quiz_progress(st.session_state.current_quiz_id, False, st.session_state.username)
                    st.rerun() 
    else:
        st.info("No choices available for this question, or no questions match your current filters. Try adjusting your filter/sort options.")

    st.write("---")


    # --- Feedback and Answer Display ---
    if st.session_state.answered == "correct":
        st.success(f"Yeah! 🎉 '{st.session_state.correct_answer_word}' ")
        st.info(f"**เฉลย**\n\n{st.session_state.full_answer}")
        
    elif st.session_state.answered == "incorrect":
        st.error("Failed :(")
        st.info(f"**เฉลย:**\n\n{st.session_state.full_answer}")

    # --- Pop-up for Word Detail ---
    if st.session_state.get('current_quiz_id') and data_base is not None and not data_base.empty:
        current_word_detail = data_base[data_base['Unique_ID'] == st.session_state.current_quiz_id]
        
        if not current_word_detail.empty:
            with st.popover("See word detail"):
                st.markdown(f"**Word Details for: `{st.session_state.correct_answer_word}`**")
                st.dataframe(current_word_detail.transpose(), use_container_width=True)
        else:
            st.warning("Word details not found for this question in the base data.")

    # Display current question's Richtig/False Counts if answered
    if st.session_state.answered is not None and st.session_state.current_quiz_id:
        current_quiz_data = st.session_state.user_quiz_data[st.session_state.username].get(st.session_state.current_quiz_id, {})
        st.write(f"**Richtig Count:** {current_quiz_data.get('Richtig Count', 0)} | **False Count:** {current_quiz_data.get('False Count', 0)}")


# --- Next Question Button ---
    if st.session_state.answered is not None or not st.session_state.choices: 
        if st.button("Next! ➡️", use_container_width=True):
            load_data.clear() 
            fresh_data_from_sheet = load_data(SHEET_URL)
            if fresh_data_from_sheet is not None and not fresh_data_from_sheet.empty:
                # No 'global data_base' needed here. data_base is already a module-level global.
                # We are simply re-assigning the module-level 'data_base' variable.
                data_base = fresh_data_from_sheet # This will now re-assign the global data_base directly
                
                processed_data_for_quiz_logic = initialize_quiz_data(data_base, st.session_state.username)
                
                setup_question(processed_data_for_quiz_logic, st.session_state.username, sort_option, lektion_filter)
            else:
                st.error("Could not load data for the next question. Please check the Google Sheet URL or ensure it's not empty.")
            st.rerun()
