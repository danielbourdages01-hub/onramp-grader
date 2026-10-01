import streamlit as st
import streamlit.components.v1 as components
import os
import json
import base64
from google import genai
from google.genai import types

st.set_page_config(page_title="Onramp AI Grader", layout="wide", initial_sidebar_state="collapsed")

st.title("📱 Onramp Auto-Scan Camera Grader")

# --- 1. CREATE CUSTOM CAMERA COMPONENT WITH REAL-TIME ALIGNMENT SCANNER ---
COMPONENT_DIR = "auto_camera_component"
if not os.path.exists(COMPONENT_DIR):
    os.makedirs(COMPONENT_DIR)

INDEX_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <script src="https://cdn.jsdelivr.net/npm/streamlit-component-lib@1.4.0/dist/streamlit-component-lib.js"></script>
    <style>
        body { margin: 0; padding: 0; background: #000; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
        .viewfinder { position: relative; width: 100%; max-width: 500px; margin: 0 auto; overflow: hidden; border-radius: 12px; background: #000; }
        video { width: 100%; height: auto; display: block; object-fit: cover; }
        
        /* 4 Corner Target Overlay Boxes */
        .target { position: absolute; width: 44px; height: 44px; border: 3px dashed #FFD700; border-radius: 6px; box-sizing: border-box; transition: all 0.2s ease; }
        .target.detected { border: 4px solid #00FF66; background-color: rgba(0, 255, 102, 0.25); box-shadow: 0 0 12px #00FF66; }
        
        #tl { top: 20px; left: 20px; }
        #tr { top: 20px; right: 20px; }
        #bl { bottom: 70px; left: 20px; }
        #br { bottom: 70px; right: 20px; }

        .status-bar { position: absolute; bottom: 15px; left: 50%; transform: translateX(-50%); width: 85%; padding: 10px; background: rgba(0,0,0,0.75); color: #FFF; text-align: center; border-radius: 20px; font-size: 14px; font-weight: 600; letter-spacing: 0.5px; z-index: 20; backdrop-filter: blur(4px); border: 1px solid rgba(255,255,255,0.2); }
        .status-bar.aligned { background: rgba(0, 200, 83, 0.9); color: #FFF; border-color: #00FF66; }
    </style>
</head>
<body>
    <div class="viewfinder">
        <video id="webcam" autoplay playsinline muted></video>
        
        <!-- Target Guides -->
        <div id="tl" class="target"></div>
        <div id="tr" class="target"></div>
        <div id="bl" class="target"></div>
        <div id="br" class="target"></div>

        <div id="status" class="status-bar">🎯 Align 4 corner squares in boxes</div>
        <canvas id="procCanvas" style="display:none;"></canvas>
    </div>

    <script>
        // Initialize Streamlit Component Bridge
        Streamlit.setComponentReady();
        Streamlit.setFrameHeight(480);

        const video = document.getElementById('webcam');
        const canvas = document.getElementById('procCanvas');
        const statusEl = document.getElementById('status');
        const targets = {
            tl: document.getElementById('tl'),
            tr: document.getElementById('tr'),
            bl: document.getElementById('bl'),
            br: document.getElementById('br')
        };

        let isCaptured = false;
        let alignmentFrames = 0;
        const REQUIRED_STEADY_FRAMES = 12; // ~0.4s steady alignment before auto-capture

        // Lock strictly to Rear Camera (environment)
        navigator.mediaDevices.getUserMedia({
            video: { 
                facingMode: { ideal: "environment" },
                width: { ideal: 1280 },
                height: { ideal: 720 }
            },
            audio: false
        }).then(stream => {
            video.srcObject = stream;
            video.onloadedmetadata = () => {
                requestAnimationFrame(scanLoop);
            };
        }).catch(err => {
            statusEl.innerText = "⚠️ Camera Access Error";
            statusEl.style.background = "#D32F2F";
        });

        // Real-time Frame Analysis for 4-Corner Square Detection
        function scanLoop() {
            if (isCaptured) return;

            if (video.readyState === video.HAVE_ENOUGH_DATA) {
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                const ctx = canvas.getContext('2d', { willReadFrequently: true });
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

                const vw = canvas.width;
                const vh = canvas.height;

                // Relative ROI zones for corner squares
                const zones = {
                    tl: { x: vw * 0.05, y: vh * 0.05, w: vw * 0.15, h: vh * 0.15 },
                    tr: { x: vw * 0.80, y: vh * 0.05, w: vw * 0.15, h: vh * 0.15 },
                    bl: { x: vw * 0.05, y: vh * 0.80, w: vw * 0.15, h: vh * 0.15 },
                    br: { x: vw * 0.80, y: vh * 0.80, w: vw * 0.15, h: vh * 0.15 }
                };

                let alignedCount = 0;

                for (let key in zones) {
                    const z = zones[key];
                    const imgData = ctx.getImageData(z.x, z.y, z.w, z.h);
                    if (hasDarkSquareMarker(imgData)) {
                        targets[key].classList.add('detected');
                        alignedCount++;
                    } else {
                        targets[key].classList.remove('detected');
                    }
                }

                if (alignedCount === 4) {
                    alignmentFrames++;
                    statusEl.innerText = `✨ Aligned! Hold steady (${Math.round((alignmentFrames/REQUIRED_STEADY_FRAMES)*100)}%)`;
                    statusEl.classList.add('aligned');

                    if (alignmentFrames >= REQUIRED_STEADY_FRAMES) {
                        isCaptured = true;
                        executeAutoCapture(ctx);
                        return;
                    }
                } else {
                    alignmentFrames = 0;
                    statusEl.innerText = `🎯 Align 4 corner squares in boxes (${alignedCount}/4)`;
                    statusEl.classList.remove('aligned');
                }
            }
            requestAnimationFrame(scanLoop);
        }

        // Checks for high-contrast dark fiducial marker inside target zone
        function hasDarkSquareMarker(imgData) {
            const data = imgData.data;
            let darkPixels = 0;
            const totalPixels = data.length / 4;

            for (let i = 0; i < data.length; i += 16) { // Sample every 4th pixel for speed
                const r = data[i];
                const g = data[i + 1];
                const b = data[i + 2];
                const brightness = (r + g + b) / 3;

                if (brightness < 80) { // Dark pixel threshold
                    darkPixels++;
                }
            }
            const ratio = darkPixels / (totalPixels / 4);
            return ratio > 0.12 && ratio < 0.65; // Expects corner marker coverage
        }

        function executeAutoCapture(ctx) {
            statusEl.innerText = "📸 Captured! Processing...";
            statusEl.style.background = "#0066CC";
            
            const dataUrl = canvas.toDataURL('image/jpeg', 0.88);
            
            // Send captured image to Streamlit Python backend
            Streamlit.setComponentValue(dataUrl);
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

# --- 3. AUTO-SCANNER DISPLAY & CAPTURE ---
st.caption("Point rear camera at worksheet. Position the 4 corner squares into the yellow target boxes.")
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
