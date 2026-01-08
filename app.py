import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
import pandas as pd
import yt_dlp
import zipfile
import io
import time
import re
import requests

# --- CONFIGURATION ---
st.set_page_config(page_title="FrontThree Suite", page_icon="⚡", layout="wide")

# --- AUTHENTICATION ---
def check_login():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        return True

    st.title("🔒 Restricted Access")
    with st.form("login_form"):
        username_input = st.text_input("Username")
        password_input = st.text_input("Password", type="password") 
        if st.form_submit_button("Login"):
            try:
                real_user = st.secrets["login"]["username"]
                real_pass = st.secrets["login"]["password"]
                if username_input == real_user and password_input == real_pass:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("❌ Invalid credentials.")
            except KeyError:
                st.error("🚨 Secrets not configured.")
    return False

# --- DEBUGGING FUNCTIONS (THE TRUTH SERUM) ---
def get_library_version():
    try:
        return genai.__version__
    except:
        return "Unknown (Old Version)"

def list_available_models(api_key):
    try:
        genai.configure(api_key=api_key)
        models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                models.append(m.name)
        return models
    except Exception as e:
        return [f"Error listing models: {str(e)}"]

# --- API HELPERS ---
def get_video_comments(video_id, api_key, max_limit=200):
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        comments = []
        request = youtube.commentThreads().list(
            part="snippet", videoId=video_id, maxResults=100, textFormat="plainText"
        )
        response = request.execute()
        for item in response['items']:
            comments.append(item['snippet']['topLevelComment']['snippet']['textDisplay'])
        return comments
    except Exception as e:
        st.error(f"YouTube API Error: {e}")
        return []

def download_thumbnail_bytes(url):
    try:
        ydl_opts = {'quiet': True, 'writethumbnail': True, 'skip_download': True, 'outtmpl': '-'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            response = requests.get(info['thumbnail'])
            safe_title = re.sub(r'[\\/*?:"<>|]', "", info['title'])
            return response.content, f"{safe_title[:30]}.jpg"
    except Exception as e:
        return None, str(e)

# --- AI WRAPPER ---
def ask_gemini(prompt, api_key, selected_model):
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel(selected_model)
        return model.generate_content(prompt).text
    except Exception as e:
        return f"❌ AI Error: {e}"

# --- MAIN APP ---
def main_app():
    try:
        YT_KEY = st.secrets["api"]["youtube_key"]
        GEMINI_KEY = st.secrets["api"]["gemini_key"]
    except:
        st.error("Secrets missing.")
        st.stop()

    # --- SIDEBAR DIAGNOSTICS ---
    st.sidebar.header("🛠️ Diagnostics")
    lib_ver = get_library_version()
    st.sidebar.info(f"GenAI Lib Version: {lib_ver}")
    
    st.sidebar.write("---")
    st.sidebar.write("🔎 **Model Checker**")
    if st.sidebar.button("List Available Models"):
        available_models = list_available_models(GEMINI_KEY)
        st.sidebar.success("Models found:")
        st.sidebar.code("\n".join(available_models))
        st.session_state['valid_models'] = available_models

    # Determine which model to use
    default_model = 'models/gemini-1.5-flash'
    # If we found models, grab the first one that looks like flash or pro
    if 'valid_models' in st.session_state and st.session_state['valid_models']:
        for m in st.session_state['valid_models']:
            if 'flash' in m:
                default_model = m
                break
            elif 'pro' in m:
                default_model = m
                break
    
    st.sidebar.write(f"**Targeting Model:** `{default_model}`")

    # --- MAIN UI ---
    st.title("⚡ FrontThree Suite (Debug Mode)")
    
    tab1, tab2 = st.tabs(["📥 Downloader", "🔴 Deep Dive"])

    with tab1:
        st.header("📥 Downloader")
        dl_urls = st.text_area("Paste URLs:")
        ids = list(set(re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11})", dl_urls)))
        if st.button("Get Thumbs"):
            if ids:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for i, vid in enumerate(ids):
                        d, n = download_thumbnail_bytes(f"https://youtu.be/{vid}")
                        if d: zf.writestr(n, d)
                st.download_button("Download ZIP", zip_buffer.getvalue(), "thumbs.zip")

    with tab2:
        st.header("🔴 Single Video Analysis")
        sv_url = st.text_input("URL:")
        
        if st.button("Analyze Video"):
            vid = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", sv_url)
            if vid:
                with st.spinner("Fetching comments..."):
                    comments = get_video_comments(vid.group(1), YT_KEY)
                
                if comments:
                    st.success(f"Fetched {len(comments)} comments.")
                    prompt = f"Summarize these comments:\n{comments[:50]}" # Limit for test
                    
                    with st.spinner(f"Asking Gemini ({default_model})..."):
                        res = ask_gemini(prompt, GEMINI_KEY, default_model)
                        st.markdown(res)
                else:
                    st.error("No comments found.")

if __name__ == "__main__":
    if check_login():
        main_app()
