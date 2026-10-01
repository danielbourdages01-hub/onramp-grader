import streamlit as st
import streamlit.components.v1 as components
import os
import json
import base64
from google import genai
from google.genai import types

st.set_page_config(page_title="Onramp AI Grader", layout="wide", initial_sidebar_state="collapsed")

st.title("📱 Onramp Auto-Scan Camera Grader")

# --- 1. CREATE MANUAL CAPTURE CAMERA COMPONENT WITH WORKSHEET OUTLINE ---
COMPONENT_DIR = "auto_camera_component"
if not os.path.exists(COMPONENT_DIR):
    os.makedirs(COMPONENT_DIR)

INDEX_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { margin: 0; padding: 0; background: #111; font-family: system-ui, -apple-system, sans-serif; color: white; }
        
        .viewfinder { 
            position: relative; 
            width: 100%; 
            max-width: 320px; 
            height: 430px; 
            margin: 0 auto; 
            overflow: hidden; 
            border-radius: 16px; 
            background: #000; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            box-shadow: 0 4px 20px rgba(0,0,0,0.6);
        }
        
        video { width: 100%; height: 100%; object-fit: cover; display: none; background: #000; }
        
        #startBtn { 
            padding: 14px 28px; 
            font-size: 15px; 
            font-weight: 700; 
            background: #0066CC; 
            color: white; 
            border: none; 
            border-radius: 24px; 
            cursor: pointer; 
            z-index: 30; 
            box-shadow: 0 4px 14px rgba(0,102,204,0.5); 
        }
        #startBtn:active { transform: scale(0.96); }

        /* Fixed Visual Outline Guide for Page Alignment */
        .doc-frame { 
            position: absolute; 
            width: 82%; 
            height: 82%; 
            border: 3px dashed #FFD700; 
            border-radius: 12px; 
            box-sizing: border-box; 
            z-index: 10; 
            display: none;
            pointer-events: none;
            box-shadow: inset 0 0 12px rgba(255, 215, 0, 0.2);
        }

        /* Action bar containing manual capture button */
        .action-bar { 
            position: absolute; 
            bottom: 12px; 
            left: 50%; 
            transform: translateX(-50%); 
            width: 90%; 
            z-index: 20; 
            display: none; 
            text-align: center;
        }

        #captureBtn {
            width: 100%;
            padding: 12px 18px;
            font-size: 14px;
            font-weight: 700;
            background: #00C853;
            color: white;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(0,200,83,0.4);
        }
        #captureBtn:active { transform: scale(0.97); background: #00E676; }
    </style>
</head>
<body>
    <div class="viewfinder" id="viewfinder">
        <button id="startBtn" onclick="startCamera()">📷 Tap to Start Rear Camera</button>
        <video id="webcam" autoplay playsinline muted></video>
        
        <!-- Worksheet Visual Guide Frame -->
        <div id="docFrame" class="doc-frame"></div>

        <!-- Manual Capture Bar -->
        <div id="actionBar" class="action-bar">
            <button id="captureBtn" onclick="manualCapture()">📸 Tap to Capture & Grade</button>
        </div>

        <canvas id="procCanvas" style="display:none;"></canvas>
    </div>

    <script>
        function sendToStreamlit(type, data) {
            window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type: type }, data), "*");
        }
        
        sendToStreamlit("streamlit:componentReady", { apiVersion: 1 });
        sendToStreamlit("streamlit:setFrameHeight", { height: 460 });

        const video = document.getElementById('webcam');
        const canvas = document.getElementById('procCanvas');
        const startBtn = document.getElementById('startBtn');
        const docFrame = document.getElementById('docFrame');
        const actionBar = document.getElementById('actionBar');
        const captureBtn = document.getElementById('captureBtn');

        async function startCamera() {
            startBtn.style.display = "none";
            video.style.display = "block";
            docFrame.style.display = "block";
            actionBar.style.display = "block";

            const constraintsOptions = [
                { video: { facingMode: { exact: "environment" } }, audio: false },
                { video: { facingMode: "environment" }, audio: false },
                { video: true, audio: false }
            ];

            let stream = null;
            for (let config of constraintsOptions) {
                try {
                    stream = await navigator.mediaDevices.getUserMedia(config);
                    if (stream) break;
                } catch (e) {}
            }

            if (!stream) {
                captureBtn.innerText = "❌ Camera Access Denied";
                captureBtn.style.background = "#B71C1C";
                captureBtn.disabled = true;
                return;
            }

            video.srcObject = stream;
            video.onloadedmetadata = () => {
                video.play();
            };
        }

        function manualCapture() {
            if (video.readyState === video.HAVE_ENOUGH_DATA) {
                captureBtn.innerText = "⚡ Capturing...";
                captureBtn.style.background = "#0288D1";
                captureBtn.disabled = true;

                canvas.width = video.videoWidth || 640;
                canvas.height = video.videoHeight || 480;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

                const dataUrl = canvas.toDataURL('image/jpeg', 0.88);
                sendToStreamlit("streamlit:setComponentValue", { value: dataUrl });
            }
        }
    </script>
</body>
</html>
"""

with open(os.path.join(COMPONENT_DIR, "index.html"), "w") as f:
    f.write(INDEX_HTML)

camera_scanner = components.declare_component("auto_camera_component", path=COMPONENT_DIR)

# --- 2. API KEY SETUP ---
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

# --- 3. CAMERA DISPLAY & MANUAL CAPTURE ---
st.caption("Align the worksheet within the yellow frame and tap the green button to capture.")
captured_base64 = camera_scanner(key="auto_scanner")

uploaded_file = st.file_uploader("Or select photo manually from library:", type=["jpg", "jpeg", "png"], key="fallback_upload")

image_bytes = None
if captured_base64 and isinstance(captured_base64, str) and captured_base64.startswith("data:image"):
    base64_data = captured_base64.split(",")[1]
    image_bytes = base64.b64decode(base64_data)
elif uploaded_file:
    image_bytes = uploaded_file.getvalue()

# --- 4. GEMINI AI GRADING ---
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
