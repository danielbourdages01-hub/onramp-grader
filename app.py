import streamlit as st
import json
import time
import pandas as pd
from google import genai
from google.genai import types

st.set_page_config(page_title="Onramp AI Grader", layout="wide", initial_sidebar_state="collapsed")

st.title("📱 Onramp Instant Camera Grader")

# Load API Key from Secrets or Sidebar
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    api_key = st.sidebar.text_input("Google AI Studio API Key", type="password")

if not api_key:
    st.info("👈 Please set up Streamlit Secrets or enter your API Key to begin.")
    st.stop()

try:
    client = genai.Client(api_key=api_key)
except Exception as e:
    st.error(f"API Client Error: {e}")
    st.stop()

# Sidebar Override Option
optional_key = st.sidebar.text_area(
    "Optional Answer Key Override", 
    placeholder="Leave blank! The AI reads and solves printed problems automatically.",
    height=100
)

MASTER_PROMPT = f"""
You are an expert high school math teacher grading a daily 'Onramp' practice worksheet.

GRADING PROCEDURE:
1. Extract the Student Name from the header box at the top.
2. Read all printed mathematics questions/problems directly from the worksheet image.
3. Solve each printed problem to establish ground-truth solutions.
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
    "feedback": "Brief, actionable feedback note highlighting correct work or specific conceptual mistakes."
}}
"""

# Live Camera Viewfinder
captured_image = st.camera_input("Point camera at worksheet:")

if captured_image:
    file_bytes = captured_image.getvalue()
    image_part = types.Part.from_bytes(
        data=file_bytes,
        mime_type="image/jpeg"
    )

    response = None
    last_exception = None
    max_retries = 3

    with st.spinner("⚡ Reading sheet, solving problems, & grading..."):
        for attempt in range(1, max_retries + 1):
            try:
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
                time.sleep(1)

    if response and response.text:
        try:
            data = json.loads(response.text)
            
            # Display Grade Card
            st.divider()
            st.subheader(f"👤 Student: {data.get('student_name', 'Unknown')}")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric(label="Score", value=f"{data.get('score', 0)} / 3")
            with col2:
                st.metric(label="Status", value=data.get('status', 'Unknown'))
            
            st.info(f"**Feedback:** {data.get('feedback', '')}")
            
            # Save session history for quick export
            if "grade_history" not in st.session_state:
                st.session_state["grade_history"] = []
                
            st.session_state["grade_history"].append({
                "Student Name": data.get("student_name", "Unknown"),
                "Score": data.get("score", 0),
                "Status": data.get("status", "Unknown"),
                "Feedback": data.get("feedback", "")
            })

            # Show session gradebook
            st.divider()
            st.subheader("📋 Session Gradebook")
            df = pd.DataFrame(st.session_state["grade_history"])
            st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Session Grades CSV",
                data=csv,
                file_name="session_grades.csv",
                mime="text/csv"
            )

        except Exception as parse_err:
            st.error(f"Parsing Error: {parse_err}")
    else:
        st.error(f"Grading failed: {last_exception}")
