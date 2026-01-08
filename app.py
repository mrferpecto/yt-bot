import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yt_dlp
import isodate
import io
import time
import re
import requests
import json
from datetime import datetime
from PIL import Image
# Si wordcloud da error, lo manejamos con try/except dentro, no rompera la app
try:
    from wordcloud import WordCloud
    import matplotlib.pyplot as plt
    WORDCLOUD_AVAILABLE = True
except ImportError:
    WORDCLOUD_AVAILABLE = False

# --- CONFIGURATION ---
st.set_page_config(page_title="Front Three's AI Studio", page_icon="⚡", layout="wide")

# --- COMPETITOR DATABASE ---
COMPETITORS = {
    "Sidemen": "Sidemen", "Beta Squad": "BetaSquad", "The Overlap": "TheOverlap",
    "Ben Foster": "BenFosterTheCyclingGK", "Pitch Side": "PitchSide", "FilthyFellas": "FilthyFellas",
    "The Fellas": "TheFellas", "John Nellis": "JohnNellis", "ChrisMD": "ChrisMD",
    "Miniminter": "Miniminter", "Thogden": "Thogden", "Box2Box Show": "Box2BoxShow",
    "Get Stuck In": "GetStuckIn", "Sports Dr": "SportsDr", "Rio Ferdinand Presents": "RioFerdinandPresents",
    "Stick to Football": "StickToFootball", "Club 1872": "Club1872", "Shoot for Love": "ShootForLove",
    "UMM": "UMM", "JD Sports": "JDSports", "Footasylum": "Footasylum",
    "Bleacher Report Football": "BleacherReportFootball", "Sky Sports Premier League": "SkySportsPL",
    "SpencerFC": "SpencerFC", "Calfreezy": "Calfreezy", "Zerkaa": "Zerkaa",
    "Danny Aarons": "DannyAarons", "Girth N Turf": "GirthNTurf", "Sharky": "Sharky", "Chunkz": "Chunkz"
}

# --- STRATEGIST PERSONA ---
STRATEGIST_PERSONA = """
You are a Senior YouTube Strategist (15+ years exp). 
Tone: Professional, Analytical.
Focus: Differentiate Shorts (velocity, loop) vs Longform (retention, story).
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
                    st.success("✅ Access Granted.")
                    time.sleep(0.5)
                    st.rerun()
                else: st.error("❌ Invalid Credentials")
            except: st.error("🚨 Secrets Config Error")
    return False

# --- UTILS & AI (CACHED TO SAVE QUOTA) ---

@st.cache_data(show_spinner=False)
def get_best_model_cached(api_key):
    # Just returns the model name string
    return 'models/gemini-1.5-flash'

def generate_ai_response(prompt, api_key, image=None):
    """
    Handles AI calls with Error Handling for Quota Limits.
    """
    genai.configure(api_key=api_key)
    # Priority: Flash is faster and has higher limits for free tier
    model_name = 'models/gemini-1.5-flash'
    
    try:
        model = genai.GenerativeModel(model_name)
        inputs = [prompt, image] if image else prompt
        return model.generate_content(inputs).text
    except Exception as e:
        if "429" in str(e) or "Quota" in str(e):
            return "⚠️ **AI Quota Exceeded.** Please wait a minute or use a different API Key. (Google Free Tier Limit)"
        return f"AI Error: {e}"

def extract_json_from_ai(text):
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match: return json.loads(match.group(0))
    except: pass
    return None

def download_image_from_url(url):
    try:
        resp = requests.get(url, stream=True)
        return Image.open(io.BytesIO(resp.content))
    except: return None

# --- YOUTUBE DATA FUNCTIONS ---

def get_channel_id(handle, api_key):
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
        r = youtube.search().list(part="id", q=handle, type="channel", maxResults=1).execute()
        if r['items']: return r['items'][0]['id']['channelId']
    except: return None

@st.cache_data(ttl=3600) # Cache results for 1 hour to save API calls
def get_recent_videos(channel_handle, api_key, limit=20):
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
        ch_id = get_channel_id(channel_handle, api_key)
        if not ch_id: return []
        
        ch_req = youtube.channels().list(part="contentDetails", id=ch_id).execute()
        uploads_id = ch_req['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        videos = []
        pl_req = youtube.playlistItems().list(part="contentDetails", playlistId=uploads_id, maxResults=limit).execute()
        vid_ids = [x['contentDetails']['videoId'] for x in pl_req['items']]
        
        vid_req = youtube.videos().list(part="snippet,statistics,contentDetails", id=",".join(vid_ids)).execute()
        
        for v in vid_req['items']:
            dur_iso = v['contentDetails']['duration']
            seconds = isodate.parse_duration(dur_iso).total_seconds()
            videos.append({
                "ID": v['id'],
                "Title": v['snippet']['title'],
                "Published": v['snippet']['publishedAt'],
                "Views": int(v['statistics'].get('viewCount', 0)),
                "Likes": int(v['statistics'].get('likeCount', 0)),
                "Comments": int(v['statistics'].get('commentCount', 0)),
                "Type": "Short" if seconds <= 60 else "Longform",
                "Description": v['snippet']['description'],
                "Thumbnail": v['snippet']['thumbnails']['high']['url'],
                "Competitor": channel_handle # Marker
            })
        return videos
    except: return []

def get_video_deep_data(url, api_key):
    vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)
    if not vid_match: return None
    vid_id = vid_match.group(1)
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
        vid_req = youtube.videos().list(part="snippet,statistics", id=vid_id).execute()
        if not vid_req['items']: return None
        item = vid_req['items'][0]
        
        comments = []
        try:
            c_req = youtube.commentThreads().list(part="snippet", videoId=vid_id, maxResults=50, textFormat="plainText", order="relevance").execute()
            comments = [c['snippet']['topLevelComment']['snippet']['textDisplay'] for c in c_req['items']]
        except: pass
        
        return {
            "title": item['snippet']['title'],
            "stats": item['statistics'],
            "thumb": item['snippet']['thumbnails']['high']['url'],
            "comments": comments
        }
    except: return None

# --- APP TABS ---

def tab_channel_analyzer(api_key):
    st.header("📊 Channel Analyzer (Studio Export)")
    st.info("Upload your YouTube Studio CSV Export.")
    
    uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        
        # 1. FUNNEL VISUAL
        if 'Impressions' in df.columns and 'Views' in df.columns:
            st.subheader("🔻 Retention Funnel")
            imps = df['Impressions'].sum()
            views = df['Views'].sum()
            # Simple assumption if likes missing
            likes = df['Likes'].sum() if 'Likes' in df.columns else (views * 0.04) 
            
            fig = px.funnel(dict(number=[imps, views, likes], stage=["Impressions", "Views", "Engagements"]), x='number', y='stage')
            st.plotly_chart(fig, use_container_width=True)
        
        # 2. AI ANALYSIS
        if st.button("🧠 Run Strategic Analysis"):
            with st.spinner("Analyzing CSV..."):
                prompt = f"{STRATEGIST_PERSONA}\nAnalyze this channel data:\n{df.head(20).to_csv()}"
                res = generate_ai_response(prompt, api_key)
                st.markdown(res)

def tab_downloader():
    st.header("📥 Downloader (Fixed)")
    url = st.text_input("Paste YouTube URL:", placeholder="https://youtube.com/watch?v=...")
    
    if url:
        vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)
        if vid_match:
            vid_id = vid_match.group(1)
            
            c1, c2 = st.columns(2)
            
            # COLUMN 1: THUMBNAIL
            with c1:
                st.subheader("🖼️ Thumbnail")
                img_url = f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg"
                try:
                    resp = requests.get(img_url)
                    if resp.status_code == 200:
                        st.image(resp.content, use_container_width=True)
                        st.download_button("⬇️ Download JPG", resp.content, file_name=f"{vid_id}.jpg", mime="image/jpeg")
                    else:
                        st.warning("MaxRes Thumb not found.")
                except: st.error("Error fetching image.")

            # COLUMN 2: VIDEO
            with c2:
                st.subheader("🎥 Video (720p/MP4)")
                if st.button("Generate Video Link"):
                    with st.spinner("Processing..."):
                        try:
                            # Android User Agent to bypass 403
                            ydl_opts = {
                                'quiet': True,
                                'format': 'best[height<=720][ext=mp4]/best[ext=mp4]',
                                'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
                            }
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                info = ydl.extract_info(url, download=False)
                                st.success("Link Ready!")
                                st.markdown(f"### [👉 Click to Download MP4]({info['url']})")
                        except Exception as e:
                            st.error(f"Error: {e}")

def tab_metadata_analyzer(api_key):
    st.header("👁️ Metadata & Radar Audit")
    
    c1, c2 = st.columns(2)
    img = None
    
    with c1:
        u = st.text_input("YouTube URL (for thumbnail):")
        if u:
            vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", u)
            if vid_match:
                img = download_image_from_url(f"https://img.youtube.com/vi/{vid_match.group(1)}/maxresdefault.jpg")
    with c2:
        up = st.file_uploader("Or Upload Image", type=['jpg','png'])
        if up: img = Image.open(up)

    if img:
        st.image(img, width=300)
        if st.button("🎯 Rate Thumbnail"):
            with st.spinner("AI Auditing..."):
                prompt = f"""
                {STRATEGIST_PERSONA}
                Rate thumbnail 0-10 on metrics. Output JSON: {{"Legibility": 0, "Emotion": 0, "Contrast": 0, "Curiosity": 0, "Branding": 0}}
                Then add summary.
                """
                res = generate_ai_response(prompt, api_key, img)
                
                # Try Parse JSON for Chart
                data = extract_json_from_ai(res)
                if data:
                    fig = go.Figure(data=go.Scatterpolar(
                        r=list(data.values()), theta=list(data.keys()), fill='toself'
                    ))
                    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 10])), showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                
                # Show text
                clean_text = res.replace("{", "").replace("}", "") if data else res
                st.write(clean_text)

def tab_engagement_room(api_key):
    st.header("💬 Engagement Visualizer")
    url = st.text_input("Video URL:", key="eng_url")
    
    if st.button("Analyze Sentiment"):
        with st.spinner("Fetching comments..."):
            data = get_video_deep_data(url, api_key)
            if data and data['comments']:
                text = " ".join(data['comments'])
                
                # 1. WORDCLOUD
                if WORDCLOUD_AVAILABLE:
                    st.subheader("☁️ Word Cloud")
                    wc = WordCloud(width=800, height=300, background_color='black').generate(text)
                    fig, ax = plt.subplots()
                    ax.imshow(wc, interpolation='bilinear')
                    ax.axis("off")
                    st.pyplot(fig)
                
                # 2. AI SENTIMENT
                prompt = f"""Analyze comments: "{text[:1500]}..." Output JSON: {{"Positive": 0, "Neutral": 0, "Negative": 0}}"""
                res = generate_ai_response(prompt, api_key)
                s_data = extract_json_from_ai(res)
                
                if s_data:
                    st.subheader("🍩 Sentiment")
                    fig = px.pie(values=list(s_data.values()), names=list(s_data.keys()), hole=0.5, color_discrete_sequence=px.colors.sequential.RdBu)
                    st.plotly_chart(fig, use_container_width=True)
                
                st.write("### AI Insights")
                st.write(generate_ai_response(f"Summarize sentiment: {text[:1500]}", api_key))
            else:
                st.error("No comments found or API error.")

def tab_competitor_analysis(api_key):
    st.header("⚔️ Competitor Heatmaps")
    sel = st.multiselect("Select Rivals:", list(COMPETITORS.keys()), default=["Sidemen"])
    
    if st.button("Generate Heatmap"):
        with st.spinner("Scouting..."):
            all_vids = []
            for name in sel:
                # Use cached function to save quota
                vids = get_recent_videos(COMPETITORS[name], api_key, limit=20)
                for v in vids: v['Competitor'] = name
                all_vids.extend(vids)
            
            df = pd.DataFrame(all_vids)
            if not df.empty:
                df['Published_DT'] = pd.to_datetime(df['Published'])
                df['Hour'] = df['Published_DT'].dt.hour
                df['Day'] = df['Published_DT'].dt.day_name()
                
                # HEATMAP
                st.subheader("🔥 Upload Heatmap")
                fig = px.density_heatmap(df, x="Hour", y="Day", z="Views", color_continuous_scale="Viridis", title="Best Upload Times")
                st.plotly_chart(fig, use_container_width=True)
                
                # SCATTER
                st.subheader("🔵 View Dominance")
                fig2 = px.scatter(df, x="Views", y="Likes", size="Comments", color="Competitor", hover_name="Title")
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.warning("No data found or API quota hit.")

def tab_ideation(api_key):
    st.header("💡 Ideation Lab")
    handle = st.text_input("Analyze Channel Handle (e.g. @Sidemen):")
    if st.button("Generate Ideas"):
        with st.spinner("Thinking..."):
            vids = get_recent_videos(handle, api_key, limit=10)
            if vids:
                titles = "\n".join([v['Title'] for v in vids])
                prompt = f"{STRATEGIST_PERSONA}\nBased on these recent videos:\n{titles}\nGenerate 10 NEW VIRAL IDEAS."
                res = generate_ai_response(prompt, api_key)
                st.markdown(res)
            else:
                st.error("Channel not found.")

# --- MAIN ---
def main():
    try:
        YT_KEY = st.secrets["api"]["youtube_key"]
        GEMINI_KEY = st.secrets["api"]["gemini_key"]
    except: st.stop()

    if check_login():
        t1, t2, t3, t4, t5, t6 = st.tabs([
            "📊 Channel (CSV)", 
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
