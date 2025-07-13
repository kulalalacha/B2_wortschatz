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
        # Drop rows where 'Quiz' or 'Word' or 'Answer' or 'Lektion' is empty
        df.dropna(subset=['Quiz', 'Word', 'Answer', 'Lektion'], inplace=True)
        # Create a unique ID for each row based on Quiz and Word for persistent tracking
        df['Unique_ID'] = df['Quiz'] + "::" + df['Word']
        return df
    except Exception as e:
        st.error(f"Cannot load Google Sheets URL: {e}. Please ensure the URL is correct and accessible.")
        return None

def initialize_quiz_data(df, username):
    """
    Initializes or loads quiz data for the current user, merging with the loaded Google Sheet data.
    """
    user_data = load_user_data()
    if username not in user_data:
        user_data[username] = {}

    # Ensure all current quiz items from Google Sheet are in user_data with default values if new
    for index, row in df.iterrows():
        unique_id = row['Unique_ID']
        if unique_id not in user_data[username]:
            user_data[username][unique_id] = {
                'Status': 'not started yet',
                'Richtig Count': 0,
                'False Count': 0
            }
        
        # Update the in-memory DataFrame with current user's progress
        # This is crucial so filters/sorts can use the latest progress
        df.loc[index, 'Status'] = user_data[username][unique_id].get('Status', 'not started yet')
        df.loc[index, 'Richtig Count'] = user_data[username][unique_id].get('Richtig Count', 0)
        df.loc[index, 'False Count'] = user_data[username][unique_id].get('False Count', 0)

    save_user_data(user_data)
    st.session_state.user_quiz_data[username] = user_data[username] # Update session state's user_quiz_data
    return df

def update_quiz_progress(unique_id, is_correct, username):
    """
    Updates the progress for a specific quiz item for the current user and saves it.
    """
    user_data = load_user_data()
    
    # Ensure the user and quiz ID exist in the loaded data
    if username not in user_data:
        user_data[username] = {}
    if unique_id not in user_data[username]:
        user_data[username][unique_id] = {'Status': 'not started yet', 'Richtig Count': 0, 'False Count': 0}

    current_progress = user_data[username][unique_id]

    if is_correct:
        current_progress['Richtig Count'] += 1
    else:
        current_progress['False Count'] += 1
    
    current_progress['Status'] = 'done' # Mark as done once attempted

    user_data[username][unique_id] = current_progress
    save_user_data(user_data)
    # Update the session state's user_quiz_data to reflect immediate changes
    st.session_state.user_quiz_data[username][unique_id] = current_progress


def get_filtered_sorted_questions(df_with_progress, username, sort_option, lektion_filter):
    """
    Filters and sorts the DataFrame based on user's selected options.
    Receives df_with_progress which already includes user-specific counts and status.
    """
    if df_with_progress.empty:
        return pd.DataFrame()

    filtered_df = df_with_progress.copy()

    # Apply Lektion filter
    if lektion_filter and lektion_filter != "All":
        filtered_df = filtered_df[filtered_df['Lektion'] == lektion_filter]

    # Apply sorting logic
    if sort_option == "Not Started Yet":
        # Prioritize 'not started yet', then 'False Count' (desc), then random
        not_started = filtered_df[filtered_df['Status'] == 'not started yet']
        if not not_started.empty:
            filtered_df = not_started
        else:
            # Fallback to questions with False Count > 0 (any richtig count) if all are started
            questions_to_review = filtered_df[filtered_df['False Count'] > 0]
            if not questions_to_review.empty:
                filtered_df = questions_to_review.sort_values(by='False Count', ascending=False)
            # If everything is 'done' and 'False Count' is 0, just return the filtered_df as is for random sample
            
    elif sort_option == "False Count > 0":
        # Ensure 'False Count' and 'Richtig Count' are numeric
        filtered_df['False Count'] = pd.to_numeric(filtered_df['False Count'], errors='coerce').fillna(0).astype(int)
        filtered_df['Richtig Count'] = pd.to_numeric(filtered_df['Richtig Count'], errors='coerce').fillna(0).astype(int)

        # Apply the new condition: False Count > 0 AND Richtig Count = 0
        questions_to_review_specific = filtered_df[(filtered_df['False Count'] > 0) & (filtered_df['Richtig Count'] == 0)]
        
        if not questions_to_review_specific.empty:
            # Prioritize those you've failed but not yet corrected
            filtered_df = questions_to_review_specific.sort_values(by='False Count', ascending=False)
        else:
            # Fallback: if no words meet the (False > 0 AND Richtig = 0) criteria,
            # then show any word with False Count > 0 (even if Richtig > 0)
            questions_with_any_false = filtered_df[filtered_df['False Count'] > 0]
            if not questions_with_any_false.empty:
                filtered_df = questions_with_any_false.sort_values(by='False Count', ascending=False)
            else:
                # If no questions with False Count > 0 at all, fallback to all filtered by Lektion
                fallback_df = df_with_progress.copy()
                if lektion_filter and lektion_filter != "All":
                    fallback_df = fallback_df[fallback_df['Lektion'] == lektion_filter]
                filtered_df = fallback_df
                st.info(f"No questions with 'False Count > 0' found for Lektion '{lektion_filter if lektion_filter != 'All' else 'All'}'. Displaying random questions.")

    elif sort_option == "By Lektion":
        filtered_df = filtered_df.sort_values(by='Lektion')
    # "Random" doesn't need specific sorting here, just ensures filtered_df is available

    return filtered_df

def setup_question(df, username, sort_option, lektion_filter):
    """Sets up a new question and choices based on filters and sort option."""
    
    filtered_sorted_df = get_filtered_sorted_questions(df, username, sort_option, lektion_filter)

    if filtered_sorted_df.empty:
        st.session_state.question = "No questions match your current filters. Try different options."
        st.session_state.choices = []
        st.session_state.answered = None
        st.session_state.correct_answer_word = ""
        st.session_state.full_answer = ""
        st.session_state.current_quiz_id = ""
        return

    # Randomly select a question from the filtered/sorted set
    question_row = filtered_sorted_df.sample(n=1).iloc[0]

    st.session_state.question = question_row['Quiz']
    st.session_state.correct_answer_word = question_row['Word']
    st.session_state.full_answer = question_row['Answer']
    st.session_state.current_quiz_id = question_row['Unique_ID']
    
    # Generate choices: one correct, three incorrect from the full dataset to ensure variety
    correct_answer = st.session_state.correct_answer_word
    
    # Filter out the correct answer from potential incorrect choices
    incorrect_words_pool = df[df['Word'] != correct_answer]['Word'].unique().tolist()
    
    # Ensure we don't pick the correct answer as an incorrect choice
    if correct_answer in incorrect_words_pool:
        incorrect_words_pool.remove(correct_answer)

    # Pick 3 random incorrect choices, or fewer if not enough are available
    if len(incorrect_words_pool) >= 3:
        choices = random.sample(incorrect_words_pool, 3) + [correct_answer]
    else:
        # If not enough incorrect words, use all available incorrect words plus the correct one
        choices = incorrect_words_pool + [correct_answer]

    random.shuffle(choices) # Shuffle to randomize button order
    st.session_state.choices = choices
    st.session_state.answered = None # Reset answer state for new question

# --- Streamlit UI ---

st.set_page_config(layout="centered", page_title="B2 Goethe Quiz")
st.title("B2 Goethe Quiz 🇩🇪")

data = load_data(SHEET_URL)

if data is None:
    st.stop() # Stop the app if data cannot be loaded

# --- Login Section ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None

if not st.session_state.logged_in:
    st.subheader("Login")
    username_input = st.selectbox("Select User", ("Faeng", "Gast"))
    password_input = st.text_input("Password", type="password")

    if st.button("Login"):
        if username_input == "Faeng" and password_input == "36912":
            st.session_state.logged_in = True
            st.session_state.username = "Faeng"
            st.success("Logged in as Faeng! Welcome back! 🎉")
            st.rerun()
        elif username_input == "Gast" and password_input == "": # Gast has no password
            st.session_state.logged_in = True
            st.session_state.username = "Gast"
            st.success("Logged in as Gast! Viel Erfolg beim Lernen! 📚")
            st.rerun()
        else:
            st.error("Incorrect username or password.")
else:
    st.sidebar.success(f"Logged in as: **{st.session_state.username}**")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.clear() # Clear all session state on logout
        st.rerun()

    # --- Quiz Application ---
    # Initialize user data only once per user session or if user changes
    if 'user_quiz_data' not in st.session_state or \
       st.session_state.get('user_quiz_data_loaded_for_user') != st.session_state.username:
        
        st.session_state.user_quiz_data = {} # Initialize empty dict
        # This call will load from user_data.json and populate st.session_state.user_quiz_data
        data = initialize_quiz_data(data, st.session_state.username) 
        st.session_state.user_quiz_data_loaded_for_user = st.session_state.username

    # --- Filter and Sort Options in Sidebar ---
    st.sidebar.subheader("Filter & Sort Options")
    all_lektions = ["All"] + sorted(data['Lektion'].unique().tolist())
    lektion_filter = st.sidebar.selectbox("Filter by Lektion", all_lektions, key='lektion_filter')
    sort_option = st.sidebar.selectbox(
        "Sort Questions By",
        ("Random", "Not Started Yet", "False Count > 0", "By Lektion"),
        key='sort_option'
    )
    
    # --- Display Quiz Progress Summary in Sidebar ---
    st.sidebar.subheader("Quiz Progress Summary")
    user_specific_data_for_display = st.session_state.user_quiz_data.get(st.session_state.username, {})
    
    # Ensure counts are accurate based on available questions in the sheet
    # Only count progress for Unique_IDs that exist in the current `data` DataFrame
    total_quizzes_in_sheet = len(data['Unique_ID'].unique()) 
    
    done_quizzes = 0
    total_richtig = 0
    total_false = 0
    
    for unique_id_in_sheet in data['Unique_ID'].unique():
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
    # Trigger new question setup if necessary (e.g., first load, user changed, filters/sort changed)
    if 'question' not in st.session_state or \
       st.session_state.get('current_user_for_question_setup') != st.session_state.username or \
       st.session_state.get('current_sort_option') != sort_option or \
       st.session_state.get('current_lektion_filter') != lektion_filter:
        
        setup_question(data, st.session_state.username, sort_option, lektion_filter)
        st.session_state.current_user_for_question_setup = st.session_state.username
        st.session_state.current_sort_option = sort_option
        st.session_state.current_lektion_filter = lektion_filter

    # --- Display Current Question ---
    # Safely get Lektion for current question
    current_lektion_display = 'N/A'
    if st.session_state.current_quiz_id:
        lektion_row = data[data['Unique_ID'] == st.session_state.current_quiz_id]
        if not lektion_row.empty:
            current_lektion_display = lektion_row['Lektion'].iloc[0]
    
    st.subheader(f"Lektion: {current_lektion_display}")
    
    st.markdown(f"### {st.session_state.question}")
    st.write("---")

    st.write(":") # Placeholder for question type/hint, or could be removed if not needed
    cols = st.columns(2) # Divide into 2 columns for choice buttons

    # Display choice buttons
    if st.session_state.choices: # Only display buttons if choices exist
        for i, choice in enumerate(st.session_state.choices):
            with cols[i % 2]: # Distribute buttons across 2 columns
                if st.button(choice, key=f"choice_{i}", use_container_width=True, disabled=(st.session_state.answered is not None)):
                    if choice == st.session_state.correct_answer_word:
                        st.session_state.answered = "correct"
                        update_quiz_progress(st.session_state.current_quiz_id, True, st.session_state.username)
                    else:
                        st.session_state.answered = "incorrect"
                        update_quiz_progress(st.session_state.current_quiz_id, False, st.session_state.username)
                    st.rerun() # Rerun to show feedback and disable buttons
    else:
        st.info("No choices available for this question, or no questions match your current filters.")

    st.write("---")

    # --- Feedback and Answer Display ---
    if st.session_state.answered == "correct":
        st.success(f"Yeah! 🎉 '{st.session_state.correct_answer_word}' ")
        st.info(f"**เฉลย**\n\n{st.session_state.full_answer}")
        
    elif st.session_state.answered == "incorrect":
        st.error("Failed :(")
        st.info(f"**เฉลย:**\n\n{st.session_state.full_answer}")

    # --- Feedback and Answer Display ---
if st.session_state.answered == "correct":
    st.success(f"Yeah! 🎉 '{st.session_state.correct_answer_word}' ")
    st.info(f"**เฉลย**\n\n{st.session_state.full_answer}")
    
elif st.session_state.answered == "incorrect":
    st.error("Failed :(")
    st.info(f"**เฉลย:**\n\n{st.session_state.full_answer}")

# --- Pop-up for Word Detail ---
# Ensure current_quiz_id is set and data is available before showing the button
if st.session_state.get('current_quiz_id') and data is not None and not data.empty:
    # Find the row for the current word using Unique_ID
    current_word_detail = data[data['Unique_ID'] == st.session_state.current_quiz_id]
    
    if not current_word_detail.empty:
        with st.popover("See word detail"):
            st.markdown(f"**Word Details for: `{st.session_state.correct_answer_word}`**")
            # Display the relevant columns from your Google Sheet for this single row
            # You can customize which columns to show here.
            # Example: st.write(current_word_detail[['Quiz', 'Word', 'Answer', 'Lektion', 'MoreInfoColumn']].transpose())
            # For simplicity, let's just show the entire row's details transposing it for better readability in popover.
            st.dataframe(current_word_detail.transpose(), use_container_width=True)
            # You might want to format this more cleanly, e.g., using st.write for each detail:
            # st.write(f"**Quiz:** {current_word_detail['Quiz'].iloc[0]}")
            # st.write(f"**Word:** {current_word_detail['Word'].iloc[0]}")
            # st.write(f"**Answer:** {current_word_detail['Answer'].iloc[0]}")
            # st.write(f"**Lektion:** {current_word_detail['Lektion'].iloc[0]}")
    else:
        st.warning("Word details not found for this question.")


# Display current question's Richtig/False Counts if answered
if st.session_state.answered is not None and st.session_state.current_quiz_id:
    current_quiz_data = st.session_state.user_quiz_data[st.session_state.username].get(st.session_state.current_quiz_id, {})
    st.write(f"**Richtig Count:** {current_quiz_data.get('Richtig Count', 0)} | **False Count:** {current_quiz_data.get('False Count', 0)}")

# --- Next Question Button ---
# ... (rest of your code for the next button)
    # Display current question's Richtig/False Counts if answered
    if st.session_state.answered is not None and st.session_state.current_quiz_id:
        current_quiz_data = st.session_state.user_quiz_data[st.session_state.username].get(st.session_state.current_quiz_id, {})
        st.write(f"**Richtig Count:** {current_quiz_data.get('Richtig Count', 0)} | **False Count:** {current_quiz_data.get('False Count', 0)}")

    # --- Next Question Button ---
    if st.session_state.answered is not None or not st.session_state.choices: # Show next button if answered or no choices
        if st.button("Next! ➡️", use_container_width=True):
            # Re-initialize data to get the latest progress from user_data.json for next question selection
            data = initialize_quiz_data(data, st.session_state.username) 
            setup_question(data, st.session_state.username, sort_option, lektion_filter)
            st.rerun()
