import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yt_dlp
import isodate
import io
import time
import re
import requests
import os
import tempfile
import shutil
from datetime import datetime, timedelta
from PIL import Image

# --- CONFIGURATION ---
st.set_page_config(page_title="Front Three's AI Studio", page_icon="⚡", layout="wide")

# --- COMPETITOR DATABASE ---
COMPETITORS = {
    "Sidemen": "Sidemen",
    "Beta Squad": "BetaSquad",
    "The Overlap": "TheOverlap",
    "Ben Foster": "BenFosterTheCyclingGK",
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
You are a Senior YouTube Strategist & SEO Expert with 15+ years of experience working with top-tier creators.
Your tone is professional, direct, analytical, and highly strategic.
You possess deep knowledge of the YouTube Algorithm, distinguishing clearly between Shorts (feed velocity, swipe-away rate, looping) and Longform (CTR, retention, storytelling, pacing).
Never give generic advice. Provide actionable, data-backed insights.
"""

# --- AUTHENTICATION ---
def check_login():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if st.session_state["authenticated"]: return True

    st.title("🔒 Front Three's AI Studio")
    with st.form("login"):
        user = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        if st.form_submit_button("Enter System"):
            try:
                if user == st.secrets["login"]["username"] and pwd == st.secrets["login"]["password"]:
                    st.session_state["authenticated"] = True
                    st.success("✅ System Access Granted.")
                    time.sleep(0.5)
                    st.rerun()
                else: st.error("❌ Invalid Credentials")
            except: st.error("🚨 Configuration Error")
    return False

# --- UTILS & AI WRAPPERS ---
def get_best_model(api_key):
    genai.configure(api_key=api_key)
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        priority = ['models/gemini-1.5-pro', 'models/gemini-1.5-flash', 'models/gemini-2.0-flash']
        for p in priority:
            if p in models: return p
        return models[0] if models else None
    except: return None

def generate_ai_response(prompt, api_key, image=None):
    genai.configure(api_key=api_key)
    model_name = get_best_model(api_key)
    if not model_name: return "❌ AI Unavailable"
    
    model = genai.GenerativeModel(model_name)
    try:
        inputs = [prompt, image] if image else prompt
        return model.generate_content(inputs).text
    except Exception as e:
        return f"AI Error: {e}"

def download_image_from_url(url):
    try:
        resp = requests.get(url, stream=True)
        return Image.open(io.BytesIO(resp.content))
    except: return None

# --- YOUTUBE API HELPERS ---
def get_channel_id(handle, api_key):
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
        r = youtube.search().list(part="id", q=handle, type="channel", maxResults=1).execute()
        if r['items']: return r['items'][0]['id']['channelId']
    except: return None
    return None

def get_recent_videos(channel_handle, api_key, limit=20):
    """Fetches videos from a channel handle."""
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
        # 1. Get Channel ID
        ch_id = get_channel_id(channel_handle, api_key)
        if not ch_id: return []
        
        # 2. Get Uploads
        ch_req = youtube.channels().list(part="contentDetails,snippet,statistics", id=ch_id).execute()
        uploads_id = ch_req['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        videos = []
        pl_req = youtube.playlistItems().list(part="contentDetails", playlistId=uploads_id, maxResults=limit).execute()
        vid_ids = [x['contentDetails']['videoId'] for x in pl_req['items']]
        
        # 3. Get Details
        vid_req = youtube.videos().list(part="snippet,statistics,contentDetails", id=",".join(vid_ids)).execute()
        
        for v in vid_req['items']:
            dur_iso = v['contentDetails']['duration']
            seconds = isodate.parse_duration(dur_iso).total_seconds()
            videos.append({
                "ID": v['id'],
                "Title": v['snippet']['title'],
                "Published": v['snippet']['publishedAt'][:10],
                "Views": int(v['statistics'].get('viewCount', 0)),
                "Likes": int(v['statistics'].get('likeCount', 0)),
                "Comments": int(v['statistics'].get('commentCount', 0)),
                "Type": "Short" if seconds <= 60 else "Longform",
                "Description": v['snippet']['description'],
                "Thumbnail": v['snippet']['thumbnails']['high']['url']
            })
        return videos
    except Exception as e:
        print(e)
        return []

def get_video_deep_data(url, api_key):
    """Extracts deep data for a single video URL."""
    vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)
    if not vid_match: return None
    vid_id = vid_match.group(1)
    
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
        # Stats
        vid_req = youtube.videos().list(part="snippet,statistics,contentDetails", id=vid_id).execute()
        if not vid_req['items']: return None
        item = vid_req['items'][0]
        
        # Comments
        comments = []
        try:
            c_req = youtube.commentThreads().list(part="snippet", videoId=vid_id, maxResults=50, textFormat="plainText", order="relevance").execute()
            comments = [c['snippet']['topLevelComment']['snippet']['textDisplay'] for c in c_req['items']]
        except: pass
        
        return {
            "title": item['snippet']['title'],
            "desc": item['snippet']['description'],
            "stats": item['statistics'],
            "thumb": item['snippet']['thumbnails']['high']['url'],
            "comments": comments,
            "id": vid_id
        }
    except: return None

# --- APP TABS ---

def tab_channel_analyzer(api_key):
    st.header("📊 F3 Channel Analyzer (CSV Mode)")
    st.markdown("Upload YouTube Studio Exports. The AI will switch persona based on the content type.")
    
    col_mode, col_upload = st.columns([1, 2])
    
    with col_mode:
        mode = st.radio("Select Analysis Focus:", ["📹 Longform", "📱 Shorts", "🔄 ALL (Mixed)"])
    
    with col_upload:
        uploaded_file = st.file_uploader("Upload CSV File", type=['csv'])

    if uploaded_file and st.button("Run Strategic Analysis"):
        try:
            df = pd.read_csv(uploaded_file)
            # Create a summary string of the CSV to save tokens
            csv_preview = df.head(50).to_csv(index=False) 
            
            context_prompt = ""
            if "Longform" in mode:
                context_prompt = "FOCUS: Longform Metrics. Prioritize CTR, Average View Duration (AVD), and Storytelling hooks. Ignore Short-specific metrics like 'Swiped away'."
            elif "Shorts" in mode:
                context_prompt = "FOCUS: Shorts Metrics. Prioritize 'Viewed vs Swiped Away', Loopability, and pacing. Ignore thumbnail CTR as it's less relevant in the Feed."
            else:
                context_prompt = "FOCUS: Holistic Channel Health. Analyze how Shorts and Longform interact. Are Shorts driving subs to Longform?"

            final_prompt = f"""
            {STRATEGIST_PERSONA}
            
            TASK: Analyze this CSV data from Front Three's channel.
            {context_prompt}
            
            DATA SAMPLE:
            {csv_preview}
            
            OUTPUT:
            1. Executive Summary of Performance.
            2. Pattern Recognition (What is winning vs losing).
            3. 3 Actionable Steps to improve metrics immediately.
            """
            
            with st.spinner("Analyzing Data Rows..."):
                res = generate_ai_response(final_prompt, api_key)
                st.markdown(res)
                
        except Exception as e:
            st.error(f"Error reading CSV: {e}")

def tab_downloader():
    st.header("📥 Downloader (Shorts & Longform)")
    url = st.text_input("Paste YouTube URL (Video or Short):")
    
    c1, c2 = st.columns(2)
    vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)

    with c1:
        if st.button("🖼️ Download Thumbnail"):
            if vid_match:
                vid_id = vid_match.group(1)
                img_url = f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg"
                try:
                    resp = requests.get(img_url)
                    if resp.status_code == 200:
                        st.image(resp.content, width=300)
                        st.download_button("⬇️ Save JPG", resp.content, file_name=f"{vid_id}.jpg", mime="image/jpeg")
                    else: st.error("Thumbnail not found.")
                except: st.error("Error.")

    with c2:
        if st.button("🎥 Download 720p Video (w/ Audio)"):
            if vid_match:
                full_url = f"https://www.youtube.com/watch?v={vid_match.group(1)}"
                with st.spinner("Processing download..."):
                    try:
                        # Android spoofing for 403 bypass
                        ydl_opts = {
                            'quiet': True,
                            'format': 'best[height<=720][ext=mp4]/best[ext=mp4]',
                            'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
                        }
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(full_url, download=False)
                            st.success(f"Link Generated: {info.get('title')}")
                            st.markdown(f"[👉 Click Here to Download]({info['url']})")
                    except Exception as e: st.error(f"Download Error: {e}")

def tab_metadata_analyzer(api_key):
    st.header("👁️ Metadata & Thumbnail Audit")
    
    col1, col2 = st.columns(2)
    image_to_analyze = None
    
    with col1:
        st.subheader("Option A: Upload Image")
        uploaded = st.file_uploader("Upload Thumbnail", type=['jpg', 'png', 'jpeg'])
        if uploaded:
            image_to_analyze = Image.open(uploaded)
            st.image(image_to_analyze, caption="Preview", width=300)

    with col2:
        st.subheader("Option B: YouTube Link")
        url = st.text_input("Paste Video Link for Thumbnail:")
        if url:
            vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)
            if vid_match:
                img_url = f"https://img.youtube.com/vi/{vid_match.group(1)}/maxresdefault.jpg"
                image_to_analyze = download_image_from_url(img_url)
                if image_to_analyze: st.image(image_to_analyze, width=300)

    # Chat / Analysis
    st.divider()
    if "meta_chat" not in st.session_state: st.session_state.meta_chat = []

    if image_to_analyze and st.button("🚀 Rate & Audit Thumbnail"):
        with st.spinner("Strategist analyzing visuals..."):
            prompt = f"{STRATEGIST_PERSONA}\nTASK: Rate this thumbnail (1-10). Analyze Focal Point, Text Hierarchy, Faces, and Curiosity Gap. Be harsh and professional."
            res = generate_ai_response(prompt, api_key, image_to_analyze)
            st.session_state.meta_chat.append({"role": "assistant", "content": res})

    # Chat Interface
    for m in st.session_state.meta_chat:
        with st.chat_message(m["role"]): st.markdown(m["content"])

    if prompt := st.chat_input("Ask about the thumbnail (e.g., 'Would yellow text help?'):"):
        if image_to_analyze:
            st.session_state.meta_chat.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            with st.chat_message("assistant"):
                res = generate_ai_response(f"User Question: {prompt}", api_key, image_to_analyze)
                st.markdown(res)
                st.session_state.meta_chat.append({"role": "assistant", "content": res})
        else:
            st.warning("Please upload an image or provide a link first.")

def tab_engagement_room(api_key):
    st.header("💬 Engagement Room")
    url = st.text_input("YouTube Video URL to Analyze:")
    
    if "eng_data" not in st.session_state: st.session_state.eng_data = None
    if "eng_chat" not in st.session_state: st.session_state.eng_chat = []

    if st.button("⚡ Analyze Engagement"):
        with st.spinner("Downloading Metadata & Comments..."):
            data = get_video_deep_data(url, api_key)
            if data:
                st.session_state.eng_data = data
                # Initial AI Analysis
                prompt = f"""
                {STRATEGIST_PERSONA}
                TASK: Analyze the engagement of this video.
                Title: {data['title']}
                Stats: {data['stats']}
                Comments Sample: {data['comments']}
                
                OUTPUT: Breakdown of performance, sentiment analysis, patterns in comments, and future video ideas based on this feedback.
                """
                res = generate_ai_response(prompt, api_key)
                st.session_state.eng_chat = [{"role": "assistant", "content": res}]
            else: st.error("Could not fetch video data.")

    if st.session_state.eng_data:
        # Display Data
        d = st.session_state.eng_data
        c1, c2, c3 = st.columns(3)
        c1.metric("Views", d['stats'].get('viewCount'))
        c2.metric("Likes", d['stats'].get('likeCount'))
        c3.metric("Comments", d['stats'].get('commentCount'))

        # Chat
        st.divider()
        for m in st.session_state.eng_chat:
            with st.chat_message(m["role"]): st.markdown(m["content"])
            
        if prompt := st.chat_input("Ask about the comments/performance..."):
            st.session_state.eng_chat.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            with st.chat_message("assistant"):
                context = f"Title: {d['title']}\nComments: {d['comments']}\nUser: {prompt}"
                res = generate_ai_response(context, api_key)
                st.markdown(res)
                st.session_state.eng_chat.append({"role": "assistant", "content": res})

def tab_competitor_analysis(api_key):
    st.header("⚔️ Competitor Analysis")
    
    col_sel, col_act = st.columns([3, 1])
    with col_sel:
        selected_comps = st.multiselect("Select Competitors (Max 3):", list(COMPETITORS.keys()), max_selections=3)
    
    if st.button("Analyze & Compare"):
        if selected_comps:
            with st.spinner("Scouting competitors..."):
                all_videos = []
                for comp_name in selected_comps:
                    handle = COMPETITORS[comp_name]
                    vids = get_recent_videos(handle, api_key, limit=15)
                    for v in vids: v['Competitor'] = comp_name
                    all_videos.extend(vids)
                
                df = pd.DataFrame(all_videos)
                st.session_state.comp_df = df
        else: st.warning("Select at least one competitor.")

    if "comp_df" in st.session_state:
        df = st.session_state.comp_df
        
        # Visuals
        st.subheader("Performance Landscape")
        fig = px.scatter(df, x="Views", y="Likes", color="Competitor", hover_data=["Title"], size="Comments", title="Engagement Matrix (Last 15 Uploads)")
        st.plotly_chart(fig, use_container_width=True)
        
        # Narrative Comparison Button
        st.divider()
        st.subheader("🧠 Strategic Narrative Comparison")
        c1, c2 = st.columns([1, 2])
        with c1:
            target_comp = st.selectbox("Compare 'Goal's Front Three' against:", selected_comps)
            
        if st.button("Generate Narrative SWOT Analysis"):
            with st.spinner(f"Analyzing Narrative: Front Three vs {target_comp}..."):
                # Ideally we fetch F3 data too, simulating it here or fetching real time
                # Fetching Front Three Data (Assuming handle @FrontThree)
                f3_vids = get_recent_videos("@FrontThree", api_key, limit=10)
                comp_vids = df[df['Competitor'] == target_comp].head(10).to_dict('records')
                
                f3_text = "\n".join([v['Title'] for v in f3_vids])
                comp_text = "\n".join([v['Title'] for v in comp_vids])
                
                prompt = f"""
                {STRATEGIST_PERSONA}
                TASK: Perform a Narrative SWOT Analysis comparing MY CHANNEL (Front Three) vs COMPETITOR ({target_comp}).
                
                FRONT THREE RECENT TITLES:
                {f3_text}
                
                COMPETITOR TITLES:
                {comp_text}
                
                OUTPUT:
                1. Narrative Divergence (How are our stories different?).
                2. Opportunities (What are they doing that we are missing?).
                3. Threats (Where are they beating us?).
                4. Strategic Pivot (One suggestion to out-compete them).
                """
                res = generate_ai_response(prompt, api_key)
                st.markdown(res)

def tab_ideation(api_key):
    st.header("💡 Ideation Lab")
    url = st.text_input("Paste Channel URL to Analyze for Ideas:")
    
    if st.button("🧠 Generate 20 Viral Ideas"):
        # Extract handle or channel ID logic (simplified via regex for handles)
        handle_match = re.search(r"(@[a-zA-Z0-9_-]+)", url)
        if handle_match:
            handle = handle_match.group(1)
            with st.spinner(f"Deep scanning {handle} ecosystem..."):
                vids = get_recent_videos(handle, api_key, limit=30)
                
                # Prepare data for AI
                titles = [v['Title'] for v in vids]
                stats = [f"{v['Views']} views" for v in vids]
                data_str = "\n".join([f"{t} ({s})" for t, s in zip(titles, stats)])
                
                prompt = f"""
                {STRATEGIST_PERSONA}
                TASK: Analyze this channel's performance and generate 20 NEW VIDEO IDEAS.
                
                CHANNEL DATA (Recent Uploads):
                {data_str}
                
                OUTPUT FORMAT:
                1. **[Idea Title]**
                *Rationale: [Explain in italics why this works based on the data, referencing specific gaps or high-performing formats found in the analysis]*
                
                (Repeat for 20 ideas).
                """
                res = generate_ai_response(prompt, api_key)
                st.markdown(res)
        else:
            st.error("Please enter a valid Channel URL containing a handle (e.g. youtube.com/@Handle)")

# --- MAIN ENTRY ---
def main():
    try:
        YT_KEY = st.secrets["api"]["youtube_key"]
        GEMINI_KEY = st.secrets["api"]["gemini_key"]
    except: st.stop()

    if check_login():
        t1, t2, t3, t4, t5, t6 = st.tabs([
            "📊 Channel Analyzer", 
            "📥 Downloader", 
            "👁️ Metadata", 
            "💬 Engagement", 
            "⚔️ Competitors", 
            "💡 Ideation"
        ])
        
        with t1: tab_channel_analyzer(GEMINI_KEY)
        with t2: tab_downloader()
        with t3: tab_metadata_analyzer(GEMINI_KEY)
        with t4: tab_engagement_room(GEMINI_KEY)
        with t5: tab_competitor_analysis(YT_KEY)
        with t6: tab_ideation(YT_KEY)

if __name__ == "__main__":
    main()
