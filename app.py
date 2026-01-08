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

# --- COMPETITOR DATABASE (Front Three Niche) ---
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
                if user == st.secrets["login"]["username"] and pwd == st.secrets["login"]["password"]:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else: st.error("❌ Access Denied")
            except: st.error("🚨 Secrets Error")
    return False

# --- INTELLIGENT MODEL SELECTOR ---
def get_best_model(api_key):
    genai.configure(api_key=api_key)
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Prefer models that support Images + Text (Flash/Pro 1.5/2.0)
        priority = ['models/gemini-2.0-flash', 'models/gemini-1.5-flash', 'models/gemini-1.5-pro']
        for p in priority:
            if p in models: return p
        return models[0] if models else None
    except: return None

# --- HELPER FUNCTIONS ---
def get_channel_videos(channel_handle, api_key, limit=10):
    """Search for channel ID by handle then fetch videos."""
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
        # 1. Get Channel ID
        search = youtube.search().list(q=channel_handle, type="channel", part="id", maxResults=1).execute()
        if not search['items']: return []
        chan_id = search['items'][0]['id']['channelId']
        
        # 2. Get Videos
        search_vids = youtube.search().list(channelId=chan_id, type="video", part="id", order="date", maxResults=limit).execute()
        vid_ids = [item['id']['videoId'] for item in search_vids['items']]
        
        # 3. Get Stats
        stats = youtube.videos().list(part="snippet,statistics", id=",".join(vid_ids)).execute()
        return stats.get('items', [])
    except Exception as e:
        st.error(f"Error fetching competitor: {e}")
        return []

def get_transcript(video_id):
    try:
        # Tries to get English or Spanish, or auto-generated
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
    st.sidebar.success(f"Operative: {st.secrets['login']['username']}")
    
    # Model Status
    model_name = get_best_model(GEMINI_KEY)
    st.sidebar.caption(f"Brain: {model_name.split('/')[-1] if model_name else 'Offline'}")

    # TABS
    tab_comp, tab_thumb, tab_deep, tab_dl = st.tabs([
        "🕵️ Competitor Spy", 
        "👁️ Thumbnail Rater", 
        "🧠 Deep Dive (Transcript+Data)", 
        "📥 Downloader"
    ])

    # ==================================================
    # 1. COMPETITOR SPY & DASHBOARD
    # ==================================================
    with tab_comp:
        st.header("🕵️ Competitor Intelligence")
        
        col_c1, col_c2 = st.columns([1, 2])
        with col_c1:
            selected_comp = st.selectbox("Choose a Rival:", list(COMPETITORS.keys()))
            custom_handle = st.text_input("Or type Handle (e.g. @Sidemen):")
        
        target = custom_handle if custom_handle else (COMPETITORS[selected_comp] if selected_comp else None)

        if st.button("Analyze Rival") and target:
            with st.spinner(f"Spying on {target}..."):
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
                    st.success("✅ Data Acquired")
                else: st.warning("Target not found.")

        if 'comp_data' in st.session_state:
            df = st.session_state['comp_data']
            
            # 📊 Visual Dashboard
            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                fig_views = px.bar(df, x='Title', y='Views', title="Last 20 Videos Performance", color='Views')
                fig_views.update_layout(xaxis={'visible': False}) 
                st.plotly_chart(fig_views, use_container_width=True)
            with c2:
                fig_scat = px.scatter(df, x='Views', y='Likes', size='Comments', hover_name='Title', title="Engagement Matrix (Views vs Likes)")
                st.plotly_chart(fig_scat, use_container_width=True)

            # Chat with Competitor Data
            st.divider()
            st.subheader("💬 Ask about this Competitor")
            if "comp_msgs" not in st.session_state: st.session_state.comp_msgs = []
            
            for m in st.session_state.comp_msgs:
                with st.chat_message(m["role"]): st.markdown(m["content"])
            
            if prompt := st.chat_input("Ex: What content format works best for them?"):
                st.session_state.comp_msgs.append({"role": "user", "content": prompt})
                with st.chat_message("user"): st.markdown(prompt)
                
                with st.chat_message("assistant"):
                    genai.configure(api_key=GEMINI_KEY)
                    model = genai.GenerativeModel(model_name)
                    ctx = df.to_string()
                    res = model.generate_content(f"Analyze this competitor data:\n{ctx}\n\nUser: {prompt}").text
                    st.markdown(res)
                    st.session_state.comp_msgs.append({"role": "assistant", "content": res})

    # ==================================================
    # 2. THUMBNAIL VISION (URL & UPLOAD)
    # ==================================================
    with tab_thumb:
        st.header("👁️ AI Thumbnail Critic")
        st.info("Upload or Paste. The AI will rate CTR potential and composition.")

        col_t1, col_t2 = st.columns(2)
        
        # Initialize State for Image
        if "thumb_img" not in st.session_state: st.session_state.thumb_img = None
        
        with col_t1:
            st.subheader("A. Existing Video")
            url_th = st.text_input("Paste YouTube URL:")
            if st.button("Fetch Thumbnail"):
                vid_id = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url_th)
                if vid_id:
                    # Get Max Res
                    img_url = f"https://img.youtube.com/vi/{vid_id.group(1)}/maxresdefault.jpg"
                    st.session_state.thumb_img = download_image_from_url(img_url)
                    if not st.session_state.thumb_img: # Fallback
                        img_url = f"https://img.youtube.com/vi/{vid_id.group(1)}/hqdefault.jpg"
                        st.session_state.thumb_img = download_image_from_url(img_url)

        with col_t2:
            st.subheader("B. File Upload")
            uploaded_file = st.file_uploader("Upload Image", type=['jpg', 'png', 'jpeg'])
            if uploaded_file:
                st.session_state.thumb_img = Image.open(uploaded_file)

        # Analysis Area
        if st.session_state.thumb_img:
            st.image(st.session_state.thumb_img, caption="Analyzed Asset", width=400)
            
            # Initial Analysis Button
            if st.button("🚀 Analyze Thumbnail"):
                with st.spinner("AI is looking at the image..."):
                    genai.configure(api_key=GEMINI_KEY)
                    model = genai.GenerativeModel(model_name)
                    prompt = "Act as a YouTube Expert. Rate this thumbnail 1-10. Analyze: Colors, Faces, Text readability, and Curiosity Gap. Be critical."
                    res = model.generate_content([prompt, st.session_state.thumb_img]).text
                    st.session_state['thumb_analysis'] = res
            
            if 'thumb_analysis' in st.session_state:
                st.markdown(st.session_state['thumb_analysis'])

            # Chat with Thumbnail
            st.subheader("💬 Chat with this Thumbnail")
            if "thumb_chat" not in st.session_state: st.session_state.thumb_chat = []

            for m in st.session_state.thumb_chat:
                with st.chat_message(m["role"]): st.markdown(m["content"])

            if prompt_th := st.chat_input("Ex: Would a red arrow help?"):
                st.session_state.thumb_chat.append({"role": "user", "content": prompt_th})
                with st.chat_message("user"): st.markdown(prompt_th)
                
                with st.chat_message("assistant"):
                    genai.configure(api_key=GEMINI_KEY)
                    model = genai.GenerativeModel(model_name)
                    # MULTIMODAL CALL (Image + History + New Prompt)
                    res = model.generate_content([
                        "You are analyzing the provided image.", 
                        prompt_th, 
                        st.session_state.thumb_img
                    ]).text
                    st.markdown(res)
                    st.session_state.thumb_chat.append({"role": "assistant", "content": res})

    # ==================================================
    # 3. DEEP DIVE (TRANSCRIPT + STATS + CROSS CHECK)
    # ==================================================
    with tab_deep:
        st.header("🧠 Deep Content Brain")
        st.markdown("This tool reads the **Transcript**, checks **Stats**, reads **Comments**, and looks at the **Thumbnail** simultaneously.")
        
        dd_url = st.text_input("YouTube URL for Deep Dive:")
        
        if "dd_data" not in st.session_state: 
            st.session_state.dd_data = {}

        if st.button("⚡ Initialize Deep Analysis"):
            vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", dd_url)
            if vid_match:
                vid_id = vid_match.group(1)
                with st.spinner("📥 Downloading Brain Data..."):
                    # 1. Transcript
                    transcript = get_transcript(vid_id)
                    st.session_state.dd_data['transcript'] = transcript if transcript else "No transcript available."
                    
                    # 2. Stats & Title
                    youtube = build('youtube', 'v3', developerKey=YT_KEY)
                    vid_req = youtube.videos().list(part="snippet,statistics", id=vid_id).execute()
                    if vid_req['items']:
                        item = vid_req['items'][0]
                        st.session_state.dd_data['title'] = item['snippet']['title']
                        st.session_state.dd_data['stats'] = item['statistics']
                        # 3. Thumbnail
                        thumb_url = item['snippet']['thumbnails'].get('maxres', {}).get('url') or item['snippet']['thumbnails']['high']['url']
                        st.session_state.dd_data['image'] = download_image_from_url(thumb_url)
                    
                    # 4. Comments (Top 50)
                    com_req = youtube.commentThreads().list(part="snippet", videoId=vid_id, maxResults=50, textFormat="plainText").execute()
                    comments = [c['snippet']['topLevelComment']['snippet']['textDisplay'] for c in com_req.get('items', [])]
                    st.session_state.dd_data['comments'] = "\n".join(comments)

                    st.success("✅ All Data Loaded! Transcript hidden but ready.")
            else: st.error("Invalid URL")

        # Chat Interface for Deep Dive
        if st.session_state.dd_data:
            st.divider()
            
            # Show small context summary
            c1, c2, c3 = st.columns(3)
            c1.metric("Views", st.session_state.dd_data['stats'].get('viewCount'))
            c2.metric("Likes", st.session_state.dd_data['stats'].get('likeCount'))
            c3.info(f"Transcript Length: {len(st.session_state.dd_data['transcript'])} chars")

            st.subheader("💬 Query the Video Brain")
            
            if "dd_chat" not in st.session_state: st.session_state.dd_chat = []

            for m in st.session_state.dd_chat:
                with st.chat_message(m["role"]): st.markdown(m["content"])

            if prompt_dd := st.chat_input("Ex: Why did retention drop? Cross reference transcript with comments."):
                st.session_state.dd_chat.append({"role": "user", "content": prompt_dd})
                with st.chat_message("user"): st.markdown(prompt_dd)
                
                with st.chat_message("assistant"):
                    with st.spinner("Connecting dots..."):
                        genai.configure(api_key=GEMINI_KEY)
                        model = genai.GenerativeModel(model_name)
                        
                        # THE MEGA PROMPT
                        # We pass the IMAGE and the TEXT Context together
                        inputs = [
                            f"""
                            CONTEXT:
                            Title: {st.session_state.dd_data['title']}
                            Stats: {st.session_state.dd_data['stats']}
                            Transcript: {st.session_state.dd_data['transcript'][:25000]} (truncated if too long)
                            Comments: {st.session_state.dd_data['comments']}
                            
                            TASK:
                            Answer the user question by CROSS-REFERENCING the visual thumbnail (image provided), 
                            the spoken content (transcript), and the audience reaction (comments/stats).
                            
                            USER QUESTION: {prompt_dd}
                            """,
                            st.session_state.dd_data['image'] # Pass the image object!
                        ]
                        
                        res = model.generate_content(inputs).text
                        st.markdown(res)
                        st.session_state.dd_chat.append({"role": "assistant", "content": res})

    # ==================================================
    # 4. DOWNLOADER (Legacy)
    # ==================================================
    with tab_dl:
        st.header("📥 Media Downloader")
        dl_text = st.text_area("URLs:")
        if st.button("Generate Links"):
            ids = re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11})", dl_text)
            for vid in ids:
                st.markdown(f"**Video {vid}**: [Link](https://www.youtube.com/watch?v={vid}) (Use local tool for 4K)")

if __name__ == "__main__":
    if check_login():
        main_app()
