import streamlit as st
import streamlit.components.v1 as components
import os
import json
import base64
from google import genai
from google.genai import types

st.set_page_config(page_title="Onramp AI Grader", layout="wide", initial_sidebar_state="collapsed")

st.title("📱 Onramp Auto-Scan Camera Grader")

# --- 1. CREATE COMPACT, ACCURATE AUTO-CAMERA COMPONENT ---
COMPONENT_DIR = "auto_camera_component"
if not os.path.exists(COMPONENT_DIR):
    os.makedirs(COMPONENT_DIR)

# Updated CSS for Portrait aspect ratio & JavaScript for strict detection
INDEX_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { margin: 0; padding: 0; background: #111; font-family: system-ui, -apple-system, sans-serif; color: white; }
        
        /* Fixed: Portrait aspect ratio for 8.5x11 sheets */
        .viewfinder { 
            position: relative; 
            width: 100%; 
            max-width: 340px; 
            height: 440px; 
            margin: 0 auto; 
            overflow: hidden; 
            border-radius: 14px; 
            background: #000; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            box-shadow: 0 4px 16px rgba(0,0,0,0.5);
        }
        
        video { width: 100%; height: 100%; object-fit: cover; display: none; background: #000; }
        
        #startBtn { 
            padding: 12px 24px; 
            font-size: 15px; 
            font-weight: 700; 
            background: #0066CC; 
            color: white; 
            border: none; 
            border-radius: 20px; 
            cursor: pointer; 
            z-index: 30; 
            box-shadow: 0 4px 12px rgba(0,102,204,0.4); 
        }
        #startBtn:active { transform: scale(0.96); }

        /* Larger 56px x 56px target boxes for high-visibility anchors */
        .target { 
            position: absolute; 
            width: 56px; 
            height: 56px; 
            border: 3px dashed #FFD700; 
            border-radius: 8px; 
            box-sizing: border-box; 
            transition: all 0.15s ease; 
            z-index: 10; 
            display: none; 
        }
        .target.detected { 
            border: 4px solid #00FF66; 
            background-color: rgba(0, 255, 102, 0.35); 
            box-shadow: 0 0 16px #00FF66; 
        }
        
        /* Symmetric placement matching uniform 0.5in LaTeX page margins */
        #tl { top: 22px; left: 22px; }
        #tr { top: 22px; right: 22px; }
        #bl { bottom: 65px; left: 22px; }
        #br { bottom: 65px; right: 22px; }

        .status-bar { 
            position: absolute; 
            bottom: 12px; 
            left: 50%; 
            transform: translateX(-50%); 
            width: 90%; 
            padding: 8px 12px; 
            background: rgba(0,0,0,0.85); 
            color: #FFF; 
            text-align: center; 
            border-radius: 12px; 
            font-size: 13px; 
            font-weight: 600; 
            z-index: 20; 
            border: 1px solid rgba(255,255,255,0.2); 
            display: none; 
        }
        .status-bar.aligned { background: rgba(0, 200, 83, 0.95); color: #FFF; border-color: #00FF66; }
    </style>
</head>
<body>
    <div class="viewfinder" id="viewfinder">
        <button id="startBtn" onclick="startCamera()">📷 Tap to Start Rear Camera</button>
        <video id="webcam" autoplay playsinline muted></video>
        
        <div id="tl" class="target"></div>
        <div id="tr" class="target"></div>
        <div id="bl" class="target"></div>
        <div id="br" class="target"></div>

        <div id="status" class="status-bar">🎯 Align corners with yellow boxes</div>
        <canvas id="procCanvas" style="display:none;"></canvas>
    </div>

    <script>
        function sendToStreamlit(type, data) {
            window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type: type }, data), "*");
        }
        
        sendToStreamlit("streamlit:componentReady", { apiVersion: 1 });
        // Fixed: Adjusted height to accommodate the taller portrait viewfinder
        sendToStreamlit("streamlit:setFrameHeight", { height: 460 });

        const video = document.getElementById('webcam');
        const canvas = document.getElementById('procCanvas');
        const statusEl = document.getElementById('status');
        const startBtn = document.getElementById('startBtn');
        const vfEl = document.getElementById('viewfinder');
        
        const targets = {
            tl: document.getElementById('tl'),
            tr: document.getElementById('tr'),
            bl: document.getElementById('bl'),
            br: document.getElementById('br')
        };

        let isCaptured = false;
        let alignmentFrames = 0;
        // Fixed: Increased required frames from 5 to 12 so the user must hold steady to capture
        const REQUIRED_STEADY_FRAMES = 12; 

        async function startCamera() {
            startBtn.style.display = "none";
            video.style.display = "block";
            statusEl.style.display = "block";
            for (let k in targets) targets[k].style.display = "block";

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
                statusEl.innerText = "❌ Camera Access Denied";
                statusEl.style.background = "#B71C1C";
                return;
            }

            video.srcObject = stream;
            video.onloadedmetadata = () => {
                video.play();
                requestAnimationFrame(scanLoop);
            };
        }

        function scanLoop() {
            if (isCaptured) return;

            if (video.readyState === video.HAVE_ENOUGH_DATA) {
                canvas.width = video.videoWidth || 640;
                canvas.height = video.videoHeight || 480;
                const ctx = canvas.getContext('2d', { willReadFrequently: true });
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

                const videoRect = video.getBoundingClientRect();
                const scaleX = canvas.width / videoRect.width;
                const scaleY = canvas.height / videoRect.height;

                let alignedCount = 0;

                for (let key in targets) {
                    const tEl = targets[key];
                    const tRect = tEl.getBoundingClientRect();

                    const roiX = Math.max(0, (tRect.left - videoRect.left) * scaleX);
                    const roiY = Math.max(0, (tRect.top - videoRect.top) * scaleY);
                    const roiW = Math.min(canvas.width - roiX, tRect.width * scaleX);
                    const roiH = Math.min(canvas.height - roiY, tRect.height * scaleY);

                    try {
                        const imgData = ctx.getImageData(roiX, roiY, roiW, roiH);
                        if (hasDarkSquareMarker(imgData)) {
                            tEl.classList.add('detected');
                            alignedCount++;
                        } else {
                            tEl.classList.remove('detected');
                        }
                    } catch(err) {}
                }

                if (alignedCount === 4) {
                    alignmentFrames++;
                    statusEl.innerText = `✨ Hold steady! (${alignmentFrames}/${REQUIRED_STEADY_FRAMES})`;
                    statusEl.classList.add('aligned');

                    if (alignmentFrames >= REQUIRED_STEADY_FRAMES) {
                        isCaptured = true;
                        executeAutoCapture(ctx);
                        return;
                    }
                } else {
                    alignmentFrames = 0;
                    statusEl.innerText = `🎯 Align corners with yellow boxes (${alignedCount}/4)`;
                    statusEl.classList.remove('aligned');
                }
            }
            requestAnimationFrame(scanLoop);
        }

        // Fixed: Strict "Ink AND Paper" detection logic
        function hasDarkSquareMarker(imgData) {
            const data = imgData.data;
            let darkPixels = 0;
            let lightPixels = 0;
            let sampledCount = 0;

            for (let i = 0; i < data.length; i += 16) {
                const r = data[i];
                const g = data[i + 1];
                const b = data[i + 2];
                const brightness = (r + g + b) / 3;
                sampledCount++;

                if (brightness < 90) { // Strict threshold for black ink/box
                    darkPixels++;
                } else if (brightness > 150) { // Strict threshold for white paper
                    lightPixels++;
                }
            }
            
            const darkRatio = darkPixels / sampledCount;
            const lightRatio = lightPixels / sampledCount;
            
            // For a valid corner, the target area MUST contain a mix of dark ink (10% to 60%) 
            // AND the surrounding white paper background (>25%). 
            // This prevents solid dark backgrounds (like a desk or shadow) from false-triggering.
            return (darkRatio > 0.10 && darkRatio < 0.60 && lightRatio > 0.25);
        }

        function executeAutoCapture(ctx) {
            statusEl.innerText = "📸 Captured! Processing...";
            statusEl.style.background = "#0288D1";
            const dataUrl = canvas.toDataURL('image/jpeg', 0.88);
            sendToStreamlit("streamlit:setComponentValue", { value: dataUrl });
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
st.caption("Align the 4 LaTeX corner squares inside the yellow boxes to auto-scan.")
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
                model="gemini-2.5-flash",
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
