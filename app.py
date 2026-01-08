import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
import pandas as pd
import plotly.express as px
import yt_dlp
import io
import time
import re
import requests
import os
import tempfile
import shutil
from PIL import Image

# --- CONFIGURATION ---
st.set_page_config(page_title="FrontThree Master Suite", page_icon="🔥", layout="wide")

# --- COMPETITOR DATABASE ---
COMPETITORS = {
    "Select a Competitor...": "",
    "Sidemen": "Sidemen",
    "Beta Squad": "BetaSquad",
    "The Overlap (Gary Neville)": "TheOverlap",
    "Ben Foster - The Cycling GK": "BenFosterTheCyclingGK",
    "Pitch Side": "PitchSide",
    "FilthyFellas": "FilthyFellas",
    "The Fellas": "TheFellas",
    "John Nellis": "JohnNellis",
    "ChrisMD": "ChrisMD",
    "Miniminter": "Miniminter",
    "Thogden": "Thogden",
    "Box2Box Show": "Box2BoxShow",
    "Get Stuck In": "GetStuckIn",
    "Sports Dr": "SportsDr",
    "Rio Ferdinand Presents": "RioFerdinandPresents",
    "Stick to Football": "StickToFootball",
    "Club 1872": "Club1872",
    "Shoot for Love": "ShootForLove",
    "UMM": "UMM",
    "JD Sports": "JDSports",
    "Footasylum": "Footasylum",
    "Bleacher Report Football": "BleacherReportFootball",
    "Sky Sports Premier League": "SkySportsPL",
    "SpencerFC": "SpencerFC",
    "Calfreezy": "Calfreezy",
    "Zerkaa": "Zerkaa",
    "Danny Aarons": "DannyAarons",
    "Girth N Turf": "GirthNTurf",
    "Sharky": "Sharky",
    "Chunkz": "Chunkz"
}

# --- STRATEGIST PERSONA ---
STRATEGIST_PERSONA = """
You are a Senior YouTube Strategist & SEO Expert (15+ years exp).
Tone: Professional, Direct, Analytical. 
Method: 360-degree analysis crossing Psychology, Algo-mechanics, and Content Strategy.
"""

# --- AUTHENTICATION ---
def check_login():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if st.session_state["authenticated"]: return True

    st.title("🔒 FrontThree Master Suite")
    with st.form("login"):
        user = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        if st.form_submit_button("Access System"):
            try:
                real_user = st.secrets["login"]["username"]
                real_pass = st.secrets["login"]["password"]
            except KeyError:
                st.error("🚨 Cloud Config Error: Secrets missing.")
                return False

            if user == real_user and pwd == real_pass:
                st.session_state["authenticated"] = True
                st.success("✅ Authenticated.")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("❌ Invalid Credentials.")
    return False

# --- INTELLIGENT MODEL SELECTOR ---
def get_best_model(api_key):
    genai.configure(api_key=api_key)
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        priority = ['models/gemini-1.5-flash', 'models/gemini-2.0-flash', 'models/gemini-1.5-pro']
        for p in priority:
            if p in models: return p
        return models[0] if models else None
    except: return None

# --- ROBUST AI CALLER (ANTI-QUOTA) ---
def generate_content_safe(model, inputs):
    """Retries automatically if Quota Limit (429) is hit."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return model.generate_content(inputs).text
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e):
                wait_time = (attempt + 1) * 5
                st.toast(f"⚠️ High Traffic (Quota). Cooling down {wait_time}s...", icon="🧊")
                time.sleep(wait_time)
                continue
            else:
                return f"❌ AI Error: {e}"
    return "❌ Failed after retries (Google API Limits)."

# --- VIDEO VISION ENGINE (ROBUST DOWNLOAD) ---
def upload_video_to_gemini(video_url, api_key):
    genai.configure(api_key=api_key)
    
    # 1. Create a specific TEMP DIRECTORY (Clean environment)
    temp_dir = tempfile.mkdtemp()
    
    status_text = st.empty()
    status_text.info("⏳ Initializing Stealth Download (Bypassing Bot Detection)...")
    
    try:
        # 2. Config yt-dlp to act like a Browser & use Directory
        file_path = os.path.join(temp_dir, "vision_video.mp4")
        
        ydl_opts = {
            'format': 'best[height<=480][ext=mp4]/best[height<=360][ext=mp4]/best[ext=mp4]', # Flexible
            'outtmpl': file_path,
            'quiet': True,
            'noplaylist': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        
        # Check if file exists and has size
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            raise Exception("YouTube rejected the Cloud IP download request.")

        # 3. Upload
        status_text.info("☁️ Uploading content to Gemini Brain...")
        video_file = genai.upload_file(path=file_path)
        
        # 4. Wait
        while video_file.state.name == "PROCESSING":
            time.sleep(2)
            video_file = genai.get_file(video_file.name)
            status_text.info("⚙️ Google is processing visual frames...")
            
        if video_file.state.name == "FAILED":
            raise Exception("Google Vision processing failed.")
            
        status_text.success("✅ AI Vision Ready! (Video Loaded)")
        time.sleep(1)
        status_text.empty()
        
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)
        return video_file
        
    except Exception as e:
        status_text.error(f"Vision Skipped: {e}")
        st.caption("ℹ️ Note: If YouTube blocks Cloud IPs, the analysis will proceed using Transcript + Screenshots automatically.")
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None

# --- DATA FETCHING ---
def get_channel_videos(channel_handle, api_key, limit=10):
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
        search = youtube.search().list(q=channel_handle, type="channel", part="id", maxResults=1).execute()
        if not search['items']: return []
        chan_id = search['items'][0]['id']['channelId']
        search_vids = youtube.search().list(channelId=chan_id, type="video", part="id", order="date", maxResults=limit).execute()
        vid_ids = [item['id']['videoId'] for item in search_vids['items']]
        stats = youtube.videos().list(part="snippet,statistics", id=",".join(vid_ids)).execute()
        return stats.get('items', [])
    except Exception as e:
        st.error(f"API Error: {e}")
        return []

def get_transcript_or_fallback(video_id, snippet_description):
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = transcript_list.find_transcript(['en', 'en-GB', 'es', 'es-ES']) 
        if not transcript: transcript = transcript_list.find_generated_transcript(['en', 'es'])
        full_text = " ".join([t['text'] for t in transcript.fetch()])
        return full_text, "✅ Official Transcript"
    except Exception:
        fallback_text = f"[TRANSCRIPT UNAVAILABLE]\nDESCRIPTION:\n{snippet_description}"
        return fallback_text, "⚠️ Metadata Fallback"

def download_image_from_url(url):
    try:
        resp = requests.get(url, stream=True)
        return Image.open(io.BytesIO(resp.content))
    except: return None

# --- MAIN APP ---
def main_app():
    try:
        YT_KEY = st.secrets["api"]["youtube_key"]
        GEMINI_KEY = st.secrets["api"]["gemini_key"]
    except: st.stop()

    st.sidebar.title("🔥 F3 Suite")
    st.sidebar.success(f"Strategist: {st.secrets['login']['username']}")
    
    model_name = get_best_model(GEMINI_KEY)
    st.sidebar.caption(f"Engine: {model_name.split('/')[-1] if model_name else 'Offline'}")

    tab_comp, tab_thumb, tab_deep, tab_dl = st.tabs([
        "🕵️ Competitor Spy", "👁️ Thumbnail Rater", "🧠 Deep Dive", "📥 Downloader"
    ])

    # 1. COMPETITOR SPY
    with tab_comp:
        st.header("🕵️ Competitor Intelligence")
        col_c1, col_c2 = st.columns([1, 2])
        with col_c1:
            selected_comp = st.selectbox("Select Rival:", list(COMPETITORS.keys()))
            custom_handle = st.text_input("Or Manual Handle:")
        target = custom_handle if custom_handle else (COMPETITORS[selected_comp] if selected_comp else None)

        if st.button("Run Strategic Analysis") and target:
            with st.spinner(f"Extracting intelligence on {target}..."):
                data = get_channel_videos(target, YT_KEY, limit=10)
                if data:
                    rows = []
                    for item in data:
                        rows.append({
                            "Title": item['snippet']['title'],
                            "Views": int(item['statistics'].get('viewCount', 0)),
                            "Likes": int(item['statistics'].get('likeCount', 0)),
                            "Comments": int(item['statistics'].get('commentCount', 0)),
                            "Date": item['snippet']['publishedAt'][:10]
                        })
                    df = pd.DataFrame(rows)
                    st.session_state['comp_data'] = df
                    st.success("✅ Dataset Acquired")
                else: st.warning("Target not found.")

        if 'comp_data' in st.session_state:
            df = st.session_state['comp_data']
            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                fig_views = px.bar(df, x='Title', y='Views', title="Recent Views", color='Views')
                fig_views.update_layout(xaxis={'visible': False}) 
                st.plotly_chart(fig_views, use_container_width=True)
            with c2:
                fig_scat = px.scatter(df, x='Views', y='Likes', size='Comments', hover_name='Title', title="Engagement Matrix")
                st.plotly_chart(fig_scat, use_container_width=True)

            if prompt := st.chat_input("Ask about this competitor..."):
                with st.chat_message("user"): st.markdown(prompt)
                with st.chat_message("assistant"):
                    with st.spinner("Analyzing..."):
                        genai.configure(api_key=GEMINI_KEY)
                        model = genai.GenerativeModel(model_name)
                        csv_context = df[['Title', 'Views', 'Likes']].head(10).to_csv(index=False)
                        full_prompt = f"{STRATEGIST_PERSONA}\nDATA:\n{csv_context}\nUSER: {prompt}"
                        res = generate_content_safe(model, full_prompt)
                        st.markdown(res)

    # 2. THUMBNAIL VISION
    with tab_thumb:
        st.header("👁️ Thumbnail Audit")
        col_t1, col_t2 = st.columns(2)
        if "thumb_img" not in st.session_state: st.session_state.thumb_img = None
        
        with col_t1:
            url_th = st.text_input("Paste Video URL:", key="th_in")
            if st.button("Fetch Thumbnail"):
                vid_id = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url_th)
                if vid_id:
                    img_url = f"https://img.youtube.com/vi/{vid_id.group(1)}/maxresdefault.jpg"
                    st.session_state.thumb_img = download_image_from_url(img_url)

        with col_t2:
            uploaded = st.file_uploader("Upload Image", type=['jpg', 'png'])
            if uploaded: st.session_state.thumb_img = Image.open(uploaded)

        if st.session_state.thumb_img:
            st.image(st.session_state.thumb_img, width=400)
            if st.button("🚀 Run Visual Audit"):
                with st.spinner("Auditing..."):
                    genai.configure(api_key=GEMINI_KEY)
                    model = genai.GenerativeModel(model_name)
                    prompt = f"{STRATEGIST_PERSONA}\nAudit this thumbnail (1-10). Analyze Focal Point, Text, Emotion, and CTR potential."
                    res = generate_content_safe(model, [prompt, st.session_state.thumb_img])
                    st.markdown(res)

            if prompt_th := st.chat_input("Refine strategy..."):
                with st.chat_message("user"): st.markdown(prompt_th)
                with st.chat_message("assistant"):
                    genai.configure(api_key=GEMINI_KEY)
                    model = genai.GenerativeModel(model_name)
                    res = generate_content_safe(model, [f"{STRATEGIST_PERSONA}\nUser: {prompt_th}", st.session_state.thumb_img])
                    st.markdown(res)

    # 3. DEEP DIVE (VIDEO VISION)
    with tab_deep:
        st.header("🧠 360º Content Deep Dive")
        dd_url = st.text_input("YouTube URL:", key="dd_in")
        
        if "dd_data" not in st.session_state: st.session_state.dd_data = {}
        if "uploaded_video" not in st.session_state: st.session_state.uploaded_video = None

        col_act1, col_act2 = st.columns(2)
        
        with col_act1:
            if st.button("⚡ 1. Initialize Metadata"):
                vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", dd_url)
                if vid_match:
                    vid_id = vid_match.group(1)
                    with st.spinner("Aggregating Data..."):
                        youtube = build('youtube', 'v3', developerKey=YT_KEY)
                        vid_req = youtube.videos().list(part="snippet,statistics", id=vid_id).execute()
                        if vid_req['items']:
                            item = vid_req['items'][0]
                            st.session_state.dd_data['title'] = item['snippet']['title']
                            st.session_state.dd_data['stats'] = item['statistics']
                            desc = item['snippet']['description']
                            content_text, source_label = get_transcript_or_fallback(vid_id, desc)
                            st.session_state.dd_data['transcript'] = content_text
                            st.session_state.dd_data['source_label'] = source_label
                            thumb_url = item['snippet']['thumbnails'].get('maxres', {}).get('url') or item['snippet']['thumbnails']['high']['url']
                            st.session_state.dd_data['image'] = download_image_from_url(thumb_url)
                            try:
                                com_req = youtube.commentThreads().list(part="snippet", videoId=vid_id, maxResults=50, textFormat="plainText").execute()
                                comments = [c['snippet']['topLevelComment']['snippet']['textDisplay'] for c in com_req.get('items', [])]
                                st.session_state.dd_data['comments'] = "\n".join(comments)
                            except: st.session_state.dd_data['comments'] = "Comments disabled."
                            st.success(f"✅ Metadata Loaded.")
                else: st.error("Invalid URL")
        
        with col_act2:
            if st.session_state.dd_data:
                if st.button("👁️ 2. AI Watch Video (Vision)"):
                    with st.spinner("Preparing Vision System..."):
                        vid_file = upload_video_to_gemini(dd_url, GEMINI_KEY)
                        if vid_file: st.session_state.uploaded_video = vid_file

        if st.session_state.dd_data:
            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.metric("Views", st.session_state.dd_data['stats'].get('viewCount'))
            c2.metric("Likes", st.session_state.dd_data['stats'].get('likeCount'))
            c3.info(f"Context: {st.session_state.dd_data.get('source_label')}")
            
            if st.session_state.uploaded_video:
                st.success("🟢 AI Vision Active: Gemini is watching the video frames.")

            if prompt_dd := st.chat_input("Ex: How is the editing pacing in the first minute?"):
                with st.chat_message("user"): st.markdown(prompt_dd)
                with st.chat_message("assistant"):
                    with st.spinner("Synthesizing..."):
                        genai.configure(api_key=GEMINI_KEY)
                        model = genai.GenerativeModel(model_name)
                        safe_text = st.session_state.dd_data['transcript'][:15000]
                        inputs = [
                            f"""{STRATEGIST_PERSONA}
                            DATA GRID:
                            1. Title: {st.session_state.dd_data['title']}
                            2. Metrics: {st.session_state.dd_data['stats']}
                            3. Transcript/Meta: {safe_text}
                            4. Feedback: {st.session_state.dd_data['comments']}
                            TASK: Answer user query crossing all data points.
                            USER: {prompt_dd}""",
                            st.session_state.dd_data['image']
                        ]
                        if st.session_state.uploaded_video:
                            inputs.append(st.session_state.uploaded_video)
                            inputs.append("Also analyze the visual pacing/editing from the video file.")

                        res = generate_content_safe(model, inputs)
                        st.markdown(res)

    # 4. DOWNLOADER
    with tab_dl:
        st.header("📥 Asset Retrieval")
        dl_url = st.text_input("Paste YouTube URL:", key="dl_in")
        c1, c2 = st.columns(2)
        vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", dl_url)

        with c1:
            if st.button("🖼️ Get Thumbnail"):
                if vid_match:
                    vid_id = vid_match.group(1)
                    img_url = f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg"
                    try:
                        resp = requests.get(img_url)
                        if resp.status_code == 200:
                            st.image(resp.content, width=300)
                            st.download_button("⬇️ Save JPG", resp.content, file_name=f"{vid_id}.jpg", mime="image/jpeg")
                        else: st.error("HQ Thumb not found.")
                    except: st.error("Error.")

        with c2:
            if st.button("🎥 Get 720p Link"):
                if vid_match:
                    full_url = f"https://www.youtube.com/watch?v={vid_match.group(1)}"
                    with st.spinner("Generating..."):
                        try:
                            with yt_dlp.YoutubeDL({'quiet':True}) as ydl:
                                info = ydl.extract_info(full_url, download=False)
                                best_url = None
                                for f in info['formats']:
                                    if f.get('ext') == 'mp4' and f.get('acodec') != 'none':
                                        best_url = f['url']
                                if best_url: st.markdown(f"[👉 Click to Download MP4]({best_url})")
                                else: st.warning("No direct link.")
                        except Exception as e: st.error(f"Error: {e}")

if __name__ == "__main__":
    if check_login():
        main_app()
