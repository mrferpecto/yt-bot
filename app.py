import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
# BORRADA la línea de youtube_transcript_api que daba error
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
import random
from datetime import datetime, timedelta
from PIL import Image
from wordcloud import WordCloud
import matplotlib.pyplot as plt

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
You are a Senior YouTube Strategist & SEO Expert (15+ years exp).
Tone: Professional, Direct, Analytical.
Focus: Distinguish between Shorts (velocity) and Longform (retention).
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

# --- UTILS & AI ---
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
    except Exception as e: return f"AI Error: {e}"

def download_image_from_url(url):
    try:
        resp = requests.get(url, stream=True)
        return Image.open(io.BytesIO(resp.content))
    except: return None

# --- VISUAL HELPERS ---
def create_radar_chart(data_dict):
    categories = list(data_dict.keys())
    values = list(data_dict.values())
    fig = go.Figure(data=go.Scatterpolar(
        r=values, theta=categories, fill='toself', name='Thumbnail Score'
    ))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 10])), showlegend=False)
    return fig

def create_wordcloud(text):
    wc = WordCloud(width=800, height=400, background_color='black', colormap='viridis').generate(text)
    return wc

def extract_json_from_ai(text):
    """Tries to parse JSON from AI response text."""
    try:
        # Find JSON structure in text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except: pass
    return None

# --- YOUTUBE API ---
def get_channel_id(handle, api_key):
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
        r = youtube.search().list(part="id", q=handle, type="channel", maxResults=1).execute()
        if r['items']: return r['items'][0]['id']['channelId']
    except: return None
    return None

def get_recent_videos(channel_handle, api_key, limit=20):
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
        ch_id = get_channel_id(channel_handle, api_key)
        if not ch_id: return []
        
        ch_req = youtube.channels().list(part="contentDetails,snippet,statistics", id=ch_id).execute()
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
                "Published": v['snippet']['publishedAt'], # Keep ISO for sorting
                "Views": int(v['statistics'].get('viewCount', 0)),
                "Likes": int(v['statistics'].get('likeCount', 0)),
                "Comments": int(v['statistics'].get('commentCount', 0)),
                "Type": "Short" if seconds <= 60 else "Longform",
                "Description": v['snippet']['description'],
                "Thumbnail": v['snippet']['thumbnails']['high']['url']
            })
        return videos
    except Exception as e: return []

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

# --- LEGACY TABS (PRESERVED) ---
def tab_channel_classic(api_key):
    st.header("📊 Channel Analyzer (Classic)")
    uploaded_file = st.file_uploader("Upload CSV", type=['csv'], key="legacy_csv")
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        st.write(df.head())
        if st.button("Analyze Text"):
            res = generate_ai_response(f"{STRATEGIST_PERSONA}\nAnalyze: {df.head().to_string()}", api_key)
            st.write(res)

def tab_metadata_classic(api_key):
    st.header("👁️ Metadata (Classic)")
    url = st.text_input("YT Link:", key="meta_old")
    if url and st.button("Analyze"):
        st.write("Analysis...")

# --- NEW VISUAL TABS ---

def tab_channel_visual(api_key):
    st.header("📊 Channel Analyzer (Visual 2.0)")
    st.info("Upload your YouTube Studio Export CSV to visualize Funnels & Trends.")
    
    uploaded_file = st.file_uploader("Upload CSV File", type=['csv'], key="visual_csv")
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        
        # Try to find relevant columns for funnel
        cols = [c.lower() for c in df.columns]
        
        # 1. FUNNEL CHART
        st.subheader("🔻 Retention Funnel")
        # Simulating funnel data if explicit columns aren't standard, adapting to common exports
        impressions = df['Impressions'].sum() if 'Impressions' in df.columns else 100000
        views = df['Views'].sum() if 'Views' in df.columns else 5000
        likes = df['Likes'].sum() if 'Likes' in df.columns else 500
        
        funnel_data = dict(number=[impressions, views, likes], stage=["Impressions", "Views", "Engagements"])
        fig_fun = px.funnel(funnel_data, x='number', y='stage')
        st.plotly_chart(fig_fun, use_container_width=True)
        
        # 2. TREND LINES
        st.subheader("📈 Performance Trends")
        if 'Video publish time' in df.columns and 'Views' in df.columns:
            df['Date'] = pd.to_datetime(df['Video publish time'])
            fig_line = px.line(df, x='Date', y='Views', markers=True, title="Views Over Time")
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.warning("CSV must have 'Video publish time' and 'Views' for Trend Chart.")

        # 3. AI STRATEGY
        if st.button("🧠 Generate Strategic Report"):
            prompt = f"{STRATEGIST_PERSONA}\nAnalyze this channel data:\n{df.head(20).to_csv()}"
            res = generate_ai_response(prompt, api_key)
            st.markdown(res)

def tab_competitor_visual(api_key):
    st.header("⚔️ Competitor Analysis (Visual 2.0)")
    
    selected_comps = st.multiselect("Select Rivals:", list(COMPETITORS.keys()), max_selections=3, default=["Sidemen"])
    
    if st.button("🚀 Launch Visual Scan"):
        with st.spinner("Scouting & Generating Heatmaps..."):
            all_videos = []
            for comp_name in selected_comps:
                handle = COMPETITORS[comp_name]
                vids = get_recent_videos(handle, api_key, limit=30)
                for v in vids: v['Competitor'] = comp_name
                all_videos.extend(vids)
            
            df = pd.DataFrame(all_videos)
            
            if not df.empty:
                # Process Date for Heatmap
                df['Published_DT'] = pd.to_datetime(df['Published'])
                df['Day'] = df['Published_DT'].dt.day_name()
                df['Hour'] = df['Published_DT'].dt.hour
                
                # 1. VIRAL HEATMAP
                st.subheader("🔥 Viral Heatmap (Upload Habits)")
                fig_heat = px.density_heatmap(df, x="Hour", y="Day", z="Views", 
                                            title="When do they get the most views?",
                                            color_continuous_scale="Viridis",
                                            category_orders={"Day": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]})
                st.plotly_chart(fig_heat, use_container_width=True)
                
                # 2. BUBBLE DOMINANCE
                st.subheader("🔵 Dominance Matrix")
                fig_bub = px.scatter(df, x="Views", y="Likes", size="Comments", color="Competitor",
                                   hover_name="Title", title="Views vs Quality (Likes) vs Hype (Comments)")
                st.plotly_chart(fig_bub, use_container_width=True)

                # 3. AI NARRATIVE
                prompt = f"{STRATEGIST_PERSONA}\nCompare these competitors based on the data:\n{df.head(10).to_csv()}"
                res = generate_ai_response(prompt, api_key)
                st.markdown(res)
            else:
                st.error("No data found.")

def tab_metadata_visual(api_key):
    st.header("👁️ Metadata Audit (Visual 2.0)")
    
    c1, c2 = st.columns(2)
    img = None
    with c1:
        u = st.text_input("Video URL:", key="vis_meta_url")
        if u:
            vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", u)
            if vid_match:
                img = download_image_from_url(f"https://img.youtube.com/vi/{vid_match.group(1)}/maxresdefault.jpg")
    with c2:
        up = st.file_uploader("Upload", type=['jpg','png'], key="vis_meta_up")
        if up: img = Image.open(up)

    if img:
        st.image(img, width=300)
        if st.button("🎯 Analyze with Radar Chart"):
            with st.spinner("AI Evaluating..."):
                # Prompt for JSON output
                prompt = f"""
                {STRATEGIST_PERSONA}
                Rate this thumbnail 0-10 on these 5 metrics. 
                Output ONLY valid JSON format like: {{"Legibility": 8, "Emotion": 7, "Contrast": 9, "Curiosity": 6, "Branding": 5}}
                Then add a text summary.
                """
                res = generate_ai_response(prompt, api_key, img)
                
                # Extract JSON
                data = extract_json_from_ai(res)
                if data:
                    st.subheader("📊 Visual Scorecard")
                    fig = create_radar_chart(data)
                    st.plotly_chart(fig, use_container_width=True)
                
                st.write(res.replace("{", "").replace("}", "")) # Show text part roughly

def tab_engagement_visual(api_key):
    st.header("💬 Engagement Room (Visual 2.0)")
    url = st.text_input("Video URL:", key="vis_eng_url")
    
    if st.button("⚡ Analyze Sentiment"):
        with st.spinner("Reading minds..."):
            data = get_video_deep_data(url, api_key)
            if data and data['comments']:
                comments_text = " ".join(data['comments'])
                
                # 1. WORD CLOUD
                st.subheader("☁️ Audience WordCloud")
                wc = create_wordcloud(comments_text)
                fig, ax = plt.subplots(figsize=(10, 5))
                ax.imshow(wc, interpolation='bilinear')
                ax.axis("off")
                st.pyplot(fig)
                
                # 2. SENTIMENT DONUT (AI Estimated)
                prompt = f"""
                Analyze these comments: "{comments_text[:1000]}..."
                Estimate sentiment percentages. Output ONLY JSON: {{"Positive": 60, "Neutral": 30, "Negative": 10}}
                """
                res = generate_ai_response(prompt, api_key)
                s_data = extract_json_from_ai(res)
                
                if s_data:
                    st.subheader("🍩 Sentiment Donut")
                    fig_don = px.pie(values=list(s_data.values()), names=list(s_data.keys()), hole=0.5, color_discrete_sequence=px.colors.sequential.RdBu)
                    st.plotly_chart(fig_don, use_container_width=True)
                
                st.markdown("### 🧠 AI Summary")
                st.write(generate_ai_response(f"Summarize these comments: {comments_text[:1000]}", api_key))

def tab_downloader_util():
    st.header("📥 Downloader (Utility)")
    url = st.text_input("Paste URL:", key="dl_util")
    if st.button("Get Link"):
        with st.spinner("Processing..."):
            try:
                ydl_opts = {'quiet':True, 'format':'best[ext=mp4]', 'extractor_args':{'youtube':{'player_client':['android']}}}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    st.success(f"Title: {info.get('title')}")
                    st.markdown(f"[Download MP4]({info['url']})")
            except Exception as e: st.error(f"Error: {e}")

# --- MAIN ENTRY ---
def main():
    try:
        YT_KEY = st.secrets["api"]["youtube_key"]
        GEMINI_KEY = st.secrets["api"]["gemini_key"]
    except: st.stop()

    if check_login():
        # DUAL TABS SYSTEM
        tabs = st.tabs([
            "📊 Channel (Classic)", "📊 Channel (Visual 2.0)", 
            "⚔️ Competitors (Visual 2.0)", 
            "👁️ Metadata (Visual 2.0)", 
            "💬 Engagement (Visual 2.0)",
            "📥 Downloader"
        ])
        
        with tabs[0]: tab_channel_classic(GEMINI_KEY)
        with tabs[1]: tab_channel_visual(GEMINI_KEY)
        with tabs[2]: tab_competitor_visual(YT_KEY)
        with tabs[3]: tab_metadata_visual(GEMINI_KEY)
        with tabs[4]: tab_engagement_visual(YT_KEY)
        with tabs[5]: tab_downloader_util()

if __name__ == "__main__":
    main()
