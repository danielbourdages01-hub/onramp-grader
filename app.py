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

# Live Rear Camera Viewfinder (HTML5 + WebRTC)
camera_html = """
<div style="text-align: center; max-width: 100%;">
    <video id="webcam" autoplay playsinline style="width: 100%; max-width: 500px; border-radius: 12px; border: 2px solid #4A5568;"></video>
    <br>
    <button id="snap" style="margin-top: 12px; width: 100%; max-width: 500px; padding: 14px; background-color: #0066CC; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer;">
        📸 Capture & Grade Worksheet
    </button>
    <canvas id="canvas" style="display:none;"></canvas>
</div>

<script>
    const video = document.getElementById('webcam');
    const canvas = document.getElementById('canvas');
    const snapBtn = document.getElementById('snap');

    // Request high-res rear camera
    navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false
    }).then(stream => {
        video.srcObject = stream;
    }).catch(err => {
        console.error("Camera access error:", err);
    });

    snapBtn.addEventListener('click', () => {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const context = canvas.getContext('2d');
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
        
        // Pass base64 image data to Streamlit
        window.parent.postMessage({
            type: "streamlit:setComponentValue",
            value: dataUrl
        }, "*");
    });
</script>
"""

# Render embedded viewfinder
captured_base64 = st.components.v1.html(camera_html, height=420)

# Alternative standard camera input as fallback
if not captured_base64:
    captured_image = st.camera_input("Or tap here to toggle built-in camera:", key="std_cam")
else:
    captured_image = None

# Extract image bytes from captured frame
image_bytes = None
if captured_base64 and isinstance(captured_base64, str) and captured_base64.startswith("data:image"):
    base64_data = captured_base64.split(",")[1]
    image_bytes = base64.b64decode(base64_data)
elif captured_image:
    image_bytes = captured_image.getvalue()

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
