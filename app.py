import streamlit as st
import json
import base64
import pandas as pd
from google import genai
from google.genai import types

st.set_page_config(page_title="Onramp AI Grader", layout="wide", initial_sidebar_state="collapsed")

st.title("📱 Onramp Live Camera Grader")

# --- 1. API KEY SETUP ---
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

# --- 2. NATIVE STREAMLIT CAMERA & FILE INPUT ---
st.subheader("1. Take or Upload Photo")
camera_photo = st.camera_input("Point camera at student worksheet and capture:")

uploaded_file = st.file_uploader("Or select photo from library:", type=["jpg", "jpeg", "png"], key="fallback_upload")

# Extract image bytes
image_bytes = None
if camera_photo:
    image_bytes = camera_photo.getvalue()
elif uploaded_file:
    image_bytes = uploaded_file.getvalue()

# --- 3. GEMINI GRADING LOGIC ---
if image_bytes:
    MASTER_PROMPT = """
    You are an expert high school math teacher grading a daily 'Onramp' practice worksheet.

    GRADING PROCEDURE:
    1. Extract Student Name from top header box.
    2. Read all printed mathematics questions directly from worksheet image.
    3. Solve printed problems to establish ground truth.
    4. Grade handwritten student work on 0-3 scale:
       - 3: Mastered | 2: Developing | 1: Incomplete | 0: Missing

    OUTPUT FORMAT (Strict JSON):
    {
        "student_name": "Extracted Name or Unknown",
        "score": 3,
        "status": "Mastered",
        "feedback": "Brief feedback note on student reasoning."
    }
    """

    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

    with st.spinner("⚡ Reading sheet & grading..."):
        try:
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=[image_part, MASTER_PROMPT],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            
            if response and response.text:
                data = json.loads(response.text)
                
                st.success("Grading Complete!")
                st.subheader(f"👤 Student: {data.get('student_name', 'Unknown')}")
                
                col1, col2 = st.columns(2)
                col1.metric("Score", f"{data.get('score', 0)} / 3")
                col2.metric("Status", data.get('status', 'Unknown'))
                
                st.info(f"**Feedback:** {data.get('feedback', '')}")

        except Exception as e:
            st.error(f"Grading error: {e}")
