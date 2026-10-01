import streamlit as st
import json
import time
import pandas as pd
from google import genai
from google.genai import types

st.set_page_config(page_title="Onramp AI Grader", layout="wide", initial_sidebar_state="expanded")

st.title("📱 Onramp Daily Worksheet Auto-Grader")
st.write("Snap or upload student worksheets. The AI automatically reads the printed questions, solves them, and grades student work.")

# Sidebar Configuration
st.sidebar.header("Settings")
api_key = st.sidebar.text_input("Google AI Studio API Key", type="password")

# Optional Answer Key Override
optional_key = st.sidebar.text_area(
    "Optional Answer Key Override", 
    placeholder="Leave blank! The AI will automatically solve the printed LaTeX problems. Only fill this in if you want to enforce specific solutions.",
    height=120
)

if not api_key:
    st.info("👈 Please enter your free Google AI Studio API Key in the sidebar to begin.")
    st.stop()

try:
    client = genai.Client(api_key=api_key)
except Exception as e:
    st.error(f"API Client Initialization Error: {e}")
    st.stop()

# Dynamic Master Prompt
MASTER_PROMPT = f"""
You are an expert high school math teacher grading a daily 'Onramp' practice worksheet.

GRADING PROCEDURE:
1. Extract the Student Name from the header box at the top.
2. Read all printed mathematics questions/problems directly from the worksheet image.
3. Solve each printed problem to establish the ground-truth solutions.
{"4. USE THIS SPECIFIC ANSWER KEY OVERRIDE:" + optional_key if optional_key.strip() else ""}

SCORING RUBRIC (0 to 3 Points):
- 3 | Mastered: Complete, correct reasoning, minor or no computational errors.
- 2 | Developing: Complete, shows effort, but contains conceptual errors or key misunderstandings.
- 1 | Incomplete: Started but under 50% finished, or minimal effort shown.
- 0 | Missing: Not submitted, blank, or completely unreadable.

OUTPUT FORMAT:
Output JSON strictly using this format:
{{
    "student_name": "Extracted Name or Unknown",
    "score": 3,
    "status": "Mastered",
    "feedback": "Brief, actionable feedback note for the student highlighting correct work or specific conceptual mistakes."
}}
"""

uploaded_files = st.file_uploader(
    "Snap or Upload Worksheet Photos", 
    type=["jpg", "jpeg", "png"], 
    accept_multiple_files=True
)

if uploaded_files and st.button("Grade Worksheets"):
    results = []

    for uploaded_file in uploaded_files:
        file_bytes = uploaded_file.getvalue()
        image_part = types.Part.from_bytes(
            data=file_bytes,
            mime_type=uploaded_file.type or "image/jpeg"
        )

        response = None
        last_exception = None
        max_retries = 5

        for attempt in range(1, max_retries + 1):
            try:
                with st.spinner(f"Grading {uploaded_file.name} (Attempt {attempt}/{max_retries})..."):
                    response = client.models.generate_content(
                        model="gemini-3.8-flash",
                        contents=[image_part, MASTER_PROMPT],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )
                    if response and response.text:
                        break
            except Exception as err:
                last_exception = err
                if "503" in str(err) or "UNAVAILABLE" in str(err):
                    wait_time = 2 ** attempt
                    st.warning(f"Server busy. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    time.sleep(2)

        if not response or not response.text:
            st.error(f"Error processing {uploaded_file.name}: {last_exception}")
            continue

        try:
            data = json.loads(response.text)
            
            row = {
                "File": uploaded_file.name,
                "Student Name": data.get("student_name", "Unknown"),
                "Score (0-3)": data.get("score", 0),
                "Status": data.get("status", "Unknown"),
                "Feedback": data.get("feedback", "")
            }
            results.append(row)
        except Exception as parse_err:
            st.error(f"Error parsing response for {uploaded_file.name}: {parse_err}")

    if results:
        df = pd.DataFrame(results)
        st.subheader("Grading Results")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Gradebook CSV",
            data=csv,
            file_name="onramp_daily_grades.csv",
            mime="text/csv"
        )