import streamlit as st
import json
import time
import base64
import pandas as pd
from google import genai
from google.genai import types

st.set_page_config(page_title="Onramp AI Grader", layout="wide", initial_sidebar_state="collapsed")

st.title("📱 Onramp Live Camera Grader")

# API Key Check
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

# Camera viewfinder with floating shutter button
camera_html = """
<div style="position: relative; width: 100%; max-width: 500px; margin: 0 auto; overflow: hidden; border-radius: 12px; border: 2px solid #4A5568; background-color: #000;">
    <video id="webcam" autoplay playsinline style="width: 100%; max-height: 380px; object-fit: cover; display: block;"></video>
    <button id="snap" style="position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); width: 80%; padding: 14px 20px; background-color: #0066CC; color: white; border: none; border-radius: 30px; font-size: 16px; font-weight: bold; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.5); z-index: 10;">
        📸 Capture & Grade Worksheet
    </button>
    <canvas id="canvas" style="display:none;"></canvas>
</div>

<script>
    const video = document.getElementById('webcam');
    const canvas = document.getElementById('canvas');
    const snapBtn = document.getElementById('snap');

    navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false
    }).then(stream => {
        video.srcObject = stream;
    }).catch(err => {
        console.error("Camera access error:", err);
    });

    snapBtn.addEventListener('click', () => {
        canvas.width = video.videoWidth || 1280;
        canvas.height = video.videoHeight || 720;
        const context = canvas.getContext('2d');
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
        
        window.parent.postMessage({
            type: "streamlit:setComponentValue",
            value: dataUrl
        }, "*");
    });
</script>
"""

# Render embedded viewfinder container
captured_base64 = st.components.v1.html(camera_html, height=420)

# Alternative standard file uploader as fallback below viewfinder
uploaded_file = st.file_uploader("Or select photo from library:", type=["jpg", "jpeg", "png"], key="fallback_upload")

# Extract image bytes
image_bytes = None
if captured_base64 and isinstance(captured_base64, str) and captured_base64.startswith("data:image"):
    base64_data = captured_base64.split(",")[1]
    image_bytes = base64.b64decode(base64_data)
elif uploaded_file:
    image_bytes = uploaded_file.getvalue()

# Grading Logic
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

    with st.spinner("⚡ Processing worksheet..."):
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
