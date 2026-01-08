import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
import pandas as pd
import plotly.express as px
import yt_dlp
import zipfile
import io
import time
import re
import requests
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

# --- SYSTEM PROMPTS (THE 15-YEAR STRATEGIST PERSONA) ---
STRATEGIST_PERSONA = """
You are a Senior YouTube Strategist & SEO Expert with 15+ years of experience managing high-growth channels. 
Your tone is professional, direct, and analytical. You adopt a 'comprehensive, 360-degree approach', always crossing data points (psychology, algorithm mechanics, content pacing, and metadata).
Never state the obvious. Provide high-level strategic insights actionable for a professional production team.
"""

# --- AUTHENTICATION (FIXED) ---
def check_login():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if st.session_state["authenticated"]: return True

    st.title("🔒 FrontThree Master Suite")
    with st.form("login"):
        user = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        if st.form_submit_button("Access System"):
            # 1. Read secrets first
            try:
                real_user = st.secrets["login"]["username"]
                real_pass = st.secrets["login"]["password"]
            except KeyError:
                st.error("🚨 Configuration Error: Secrets missing in Cloud.")
                return False

            # 2. Validate outside the try block to allow rerun
            if user == real_user and pwd == real_pass:
                st.session_state["authenticated"] = True
                st.success("✅ Access Granted. Initializing Strategy Core...")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("❌ Access Denied: Invalid Credentials.")
    return False

# --- INTELLIGENT MODEL SELECTOR ---
def get_best_model(api_key):
    genai.configure(api_key=api_key)
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        priority = ['models/gemini-2.0-flash', 'models/gemini-1.5-flash', 'models/gemini-1.5-pro']
        for p in priority:
            if p in models: return p
        return models[0] if models else None
    except: return None

# --- HELPER FUNCTIONS ---
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
        st.error(f"Error fetching competitor: {e}")
        return []

def get_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'es', 'en-GB', 'auto'])
        full_text = " ".join([entry['text'] for entry in transcript])
        return full_text
    except Exception as e:
        return None

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

    # TABS
    tab_comp, tab_thumb, tab_deep, tab_dl = st.tabs([
        "🕵️ Competitor Spy", 
        "👁️ Thumbnail Rater", 
        "🧠 Deep Dive (Transcript+Data)", 
        "📥 Downloader"
    ])

    # ==================================================
    # 1. COMPETITOR SPY
    # ==================================================
    with tab_comp:
        st.header("🕵️ Competitor Intelligence")
        
        col_c1, col_c2 = st.columns([1, 2])
        with col_c1:
            selected_comp = st.selectbox("Select Rival:", list(COMPETITORS.keys()))
            custom_handle = st.text_input("Or Manual Handle:")
        
        target = custom_handle if custom_handle else (COMPETITORS[selected_comp] if selected_comp else None)

        if st.button("Run Strategic Analysis") and target:
            with st.spinner(f"Extracting intelligence on {target}..."):
                data = get_channel_videos(target, YT_KEY, limit=20)
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
                fig_views = px.bar(df, x='Title', y='Views', title="Recent Performance (Views)", color='Views')
                fig_views.update_layout(xaxis={'visible': False}) 
                st.plotly_chart(fig_views, use_container_width=True)
            with c2:
                fig_scat = px.scatter(df, x='Views', y='Likes', size='Comments', hover_name='Title', title="Engagement Quality (Views vs Likes)")
                st.plotly_chart(fig_scat, use_container_width=True)

            st.divider()
            st.subheader("💬 Strategic Consultant Chat")
            if "comp_msgs" not in st.session_state: st.session_state.comp_msgs = []
            
            for m in st.session_state.comp_msgs:
                with st.chat_message(m["role"]): st.markdown(m["content"])
            
            if prompt := st.chat_input("Ask the Strategist about this competitor..."):
                st.session_state.comp_msgs.append({"role": "user", "content": prompt})
                with st.chat_message("user"): st.markdown(prompt)
                
                with st.chat_message("assistant"):
                    genai.configure(api_key=GEMINI_KEY)
                    model = genai.GenerativeModel(model_name)
                    
                    full_prompt = f"{STRATEGIST_PERSONA}\n\nDATA CONTEXT:\n{df.to_string()}\n\nUSER QUESTION: {prompt}\n\nProvide a high-level strategic answer."
                    
                    res = model.generate_content(full_prompt).text
                    st.markdown(res)
                    st.session_state.comp_msgs.append({"role": "assistant", "content": res})

    # ==================================================
    # 2. THUMBNAIL VISION
    # ==================================================
    with tab_thumb:
        st.header("👁️ Thumbnail Strategic Audit")
        
        col_t1, col_t2 = st.columns(2)
        if "thumb_img" not in st.session_state: st.session_state.thumb_img = None
        
        with col_t1:
            st.subheader("A. Analyze Published Video")
            url_th = st.text_input("Paste Video URL:")
            if st.button("Fetch Asset"):
                vid_id = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url_th)
                if vid_id:
                    img_url = f"https://img.youtube.com/vi/{vid_id.group(1)}/maxresdefault.jpg"
                    st.session_state.thumb_img = download_image_from_url(img_url)
                    if not st.session_state.thumb_img:
                        img_url = f"https://img.youtube.com/vi/{vid_id.group(1)}/hqdefault.jpg"
                        st.session_state.thumb_img = download_image_from_url(img_url)

        with col_t2:
            st.subheader("B. Analyze Raw File")
            uploaded_file = st.file_uploader("Upload Image (JPG/PNG)", type=['jpg', 'png', 'jpeg'])
            if uploaded_file:
                st.session_state.thumb_img = Image.open(uploaded_file)

        if st.session_state.thumb_img:
            st.image(st.session_state.thumb_img, caption="Asset Loaded", width=400)
            
            if st.button("🚀 Run 360º Visual Audit"):
                with st.spinner("Analyzing composition, psychology, and CTR potential..."):
                    genai.configure(api_key=GEMINI_KEY)
                    model = genai.GenerativeModel(model_name)
                    prompt = f"{STRATEGIST_PERSONA}\n\nTASK: Conduct a rigorous 360-degree audit of this thumbnail. Evaluate: 1. Focal Point Clarity. 2. Text/Typography Hierarchy. 3. Emotional Hook. 4. Saturation/Contrast balance for Mobile. Give a final Strategic Rating (1-10) and specific improvement points."
                    res = model.generate_content([prompt, st.session_state.thumb_img]).text
                    st.session_state['thumb_analysis'] = res
            
            if 'thumb_analysis' in st.session_state:
                st.markdown(st.session_state['thumb_analysis'])

            st.subheader("💬 Refine Strategy")
            if "thumb_chat" not in st.session_state: st.session_state.thumb_chat = []

            for m in st.session_state.thumb_chat:
                with st.chat_message(m["role"]): st.markdown(m["content"])

            if prompt_th := st.chat_input("Ex: Would adding a red arrow improve CTR?"):
                st.session_state.thumb_chat.append({"role": "user", "content": prompt_th})
                with st.chat_message("user"): st.markdown(prompt_th)
                
                with st.chat_message("assistant"):
                    genai.configure(api_key=GEMINI_KEY)
                    model = genai.GenerativeModel(model_name)
                    full_prompt = [f"{STRATEGIST_PERSONA}\n\nUser Question on this specific thumbnail: {prompt_th}", st.session_state.thumb_img]
                    res = model.generate_content(full_prompt).text
                    st.markdown(res)
                    st.session_state.thumb_chat.append({"role": "assistant", "content": res})

    # ==================================================
    # 3. DEEP DIVE CORE
    # ==================================================
    with tab_deep:
        st.header("🧠 360º Content Deep Dive")
        st.markdown("Cross-references: **Transcript (Content)** + **Thumbnail (Visual)** + **Stats (Performance)** + **Comments (Feedback)**.")
        
        dd_url = st.text_input("YouTube URL to Deep Dive:")
        
        if "dd_data" not in st.session_state: st.session_state.dd_data = {}

        if st.button("⚡ Initialize Full Spectrum Analysis"):
            vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", dd_url)
            if vid_match:
                vid_id = vid_match.group(1)
                with st.spinner("📥 Aggregating Data Points..."):
                    transcript = get_transcript(vid_id)
                    st.session_state.dd_data['transcript'] = transcript if transcript else "No transcript available."
                    
                    youtube = build('youtube', 'v3', developerKey=YT_KEY)
                    vid_req = youtube.videos().list(part="snippet,statistics", id=vid_id).execute()
                    if vid_req['items']:
                        item = vid_req['items'][0]
                        st.session_state.dd_data['title'] = item['snippet']['title']
                        st.session_state.dd_data['stats'] = item['statistics']
                        thumb_url = item['snippet']['thumbnails'].get('maxres', {}).get('url') or item['snippet']['thumbnails']['high']['url']
                        st.session_state.dd_data['image'] = download_image_from_url(thumb_url)
                    
                    com_req = youtube.commentThreads().list(part="snippet", videoId=vid_id, maxResults=50, textFormat="plainText").execute()
                    comments = [c['snippet']['topLevelComment']['snippet']['textDisplay'] for c in com_req.get('items', [])]
                    st.session_state.dd_data['comments'] = "\n".join(comments)

                    st.success("✅ 360 Data Grid Loaded.")
            else: st.error("Invalid URL")

        if st.session_state.dd_data:
            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.metric("Views", st.session_state.dd_data['stats'].get('viewCount'))
            c2.metric("Retention/Likes", st.session_state.dd_data['stats'].get('likeCount'))
            c3.info(f"Transcript Status: {'Available' if len(st.session_state.dd_data['transcript']) > 50 else 'Missing'}")

            st.subheader("💬 Strategic Inquiry")
            if "dd_chat" not in st.session_state: st.session_state.dd_chat = []

            for m in st.session_state.dd_chat:
                with st.chat_message(m["role"]): st.markdown(m["content"])

            if prompt_dd := st.chat_input("Ex: Audit the hook (0-30s) vs the thumbnail promise."):
                st.session_state.dd_chat.append({"role": "user", "content": prompt_dd})
                with st.chat_message("user"): st.markdown(prompt_dd)
                
                with st.chat_message("assistant"):
                    with st.spinner("Synthesizing multi-modal strategy..."):
                        genai.configure(api_key=GEMINI_KEY)
                        model = genai.GenerativeModel(model_name)
                        
                        inputs = [
                            f"""
                            {STRATEGIST_PERSONA}
                            
                            DATA GRID:
                            1. Title: {st.session_state.dd_data['title']}
                            2. Key Metrics: {st.session_state.dd_data['stats']}
                            3. Audience Sentiment (Comments): {st.session_state.dd_data['comments']}
                            4. Content (Transcript): {st.session_state.dd_data['transcript'][:30000]} (truncated)
                            
                            TASK: Provide a comprehensive answer to the user query, explicitly crossing data points (e.g., "The thumbnail promised X, but the transcript shows Y at minute 2, explaining the comment Z").
                            
                            USER QUERY: {prompt_dd}
                            """,
                            st.session_state.dd_data['image']
                        ]
                        
                        res = model.generate_content(inputs).text
                        st.markdown(res)
                        st.session_state.dd_chat.append({"role": "assistant", "content": res})

    # ==================================================
    # 4. DOWNLOADER
    # ==================================================
    with tab_dl:
        st.header("📥 Asset Retrieval")
        dl_text = st.text_area("Paste URLs for Quick Link Generation:")
        if st.button("Generate Secure Links"):
            ids = re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11})", dl_text)
            for vid in ids:
                st.markdown(f"**Video ID {vid}**: [Direct Download Link](https://www.youtube.com/watch?v={vid})")
            st.info("Note: For 4K/1080p raw file merging, please use the local Python script version due to Cloud processing limits.")

if __name__ == "__main__":
    if check_login():
        main_app()
