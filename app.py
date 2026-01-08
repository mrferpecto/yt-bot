import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import isodate
import re
import time
from datetime import datetime, timedelta

# --- CONFIGURATION ---
st.set_page_config(page_title="FrontThree Strategic OS", page_icon="🚀", layout="wide")

# --- PERSONA ---
STRATEGIST_PERSONA = """
You are a Senior YouTube Strategist (15+ years exp). 
You analyze metadata (Titles, Clean Descriptions, Metrics) and Audience Sentiment (Comments).
Your goal is to find patterns in performance. Differentite between Shorts (fast pace, looping) and Longform.
Always be direct, critical, and data-driven.
"""

# --- AUTHENTICATION ---
def check_login():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if st.session_state["authenticated"]: return True

    st.title("🔒 FrontThree Strategic OS")
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

# --- UTILS ---
def parse_duration(duration_iso):
    """Returns seconds from ISO 8601 duration."""
    try:
        dur = isodate.parse_duration(duration_iso)
        return dur.total_seconds()
    except: return 0

def clean_description(desc):
    """Removes URLs and timestamps to save token space for AI."""
    # Remove URLs
    desc = re.sub(r'http\S+', '', desc)
    # Remove Timestamps (e.g. 0:00, 10:25)
    desc = re.sub(r'\d{1,2}:\d{2}', '', desc)
    # Remove multiple newlines
    return re.sub(r'\n+', '\n', desc).strip()[:1000] # Limit to 1000 chars

def get_video_type(seconds):
    return "📱 Short" if seconds <= 60 else "📹 Longform"

# --- API FUNCTIONS ---
def get_channel_id(handle, api_key):
    youtube = build('youtube', 'v3', developerKey=api_key)
    try:
        r = youtube.search().list(part="id", q=handle, type="channel", maxResults=1).execute()
        if r['items']: return r['items'][0]['id']['channelId']
    except: return None
    return None

def get_channel_uploads(channel_id, api_key, limit=50):
    youtube = build('youtube', 'v3', developerKey=api_key)
    # 1. Get Uploads Playlist ID
    ch_req = youtube.channels().list(part="contentDetails,snippet,statistics", id=channel_id).execute()
    uploads_id = ch_req['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    sub_count = ch_req['items'][0]['statistics']['subscriberCount']
    ch_name = ch_req['items'][0]['snippet']['title']
    
    # 2. Get Videos from Playlist
    videos = []
    next_page = None
    
    while len(videos) < limit:
        pl_req = youtube.playlistItems().list(
            part="snippet,contentDetails", 
            playlistId=uploads_id, 
            maxResults=50, 
            pageToken=next_page
        ).execute()
        
        vid_ids = [x['contentDetails']['videoId'] for x in pl_req['items']]
        
        # 3. Get Video Details (Duration, Stats)
        vid_req = youtube.videos().list(part="statistics,contentDetails,snippet", id=",".join(vid_ids)).execute()
        
        for v in vid_req['items']:
            dur_sec = parse_duration(v['contentDetails']['duration'])
            videos.append({
                "ID": v['id'],
                "Title": v['snippet']['title'],
                "Published": v['snippet']['publishedAt'],
                "Views": int(v['statistics'].get('viewCount', 0)),
                "Likes": int(v['statistics'].get('likeCount', 0)),
                "Comments": int(v['statistics'].get('commentCount', 0)),
                "Duration": dur_sec,
                "Type": get_video_type(dur_sec),
                "Thumb": v['snippet']['thumbnails']['high']['url'],
                "Desc": clean_description(v['snippet']['description'])
            })
        
        next_page = pl_req.get('nextPageToken')
        if not next_page: break
        
    return videos, ch_name, sub_count

def get_batch_details(video_ids, api_key):
    youtube = build('youtube', 'v3', developerKey=api_key)
    data = []
    
    # Chunking 50 ids
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        vid_req = youtube.videos().list(part="snippet,statistics,contentDetails", id=",".join(chunk)).execute()
        
        for v in vid_req['items']:
            # Get Top 10 Comments
            comments_text = ""
            try:
                c_req = youtube.commentThreads().list(part="snippet", videoId=v['id'], maxResults=10, textFormat="plainText", order="relevance").execute()
                comments_list = [c['snippet']['topLevelComment']['snippet']['textDisplay'] for c in c_req['items']]
                comments_text = " | ".join(comments_list)
            except: comments_text = "Comments Disabled/Error"

            dur = parse_duration(v['contentDetails']['duration'])

            data.append({
                "ID": v['id'],
                "Title": v['snippet']['title'],
                "Type": get_video_type(dur),
                "Views": int(v['statistics'].get('viewCount', 0)),
                "Likes": int(v['statistics'].get('likeCount', 0)),
                "Comments Count": int(v['statistics'].get('commentCount', 0)),
                "Clean Description": clean_description(v['snippet']['description']),
                "Top Comments Content": comments_text
            })
    return pd.DataFrame(data)

def generate_ai_response(prompt, api_key):
    genai.configure(api_key=api_key)
    try:
        # Auto-fallback logic
        models = ['models/gemini-1.5-flash', 'models/gemini-2.0-flash', 'models/gemini-pro']
        for m in models:
            try:
                model = genai.GenerativeModel(m)
                return model.generate_content(prompt).text
            except: continue
        return "❌ AI Service Unavailable."
    except Exception as e: return f"Error: {e}"

# --- MAIN APP ---
def main_app():
    try:
        YT_KEY = st.secrets["api"]["youtube_key"]
        GEMINI_KEY = st.secrets["api"]["gemini_key"]
    except: st.stop()

    st.sidebar.title("🔥 Strategic OS")
    
    tab_batch, tab_audit, tab_dl = st.tabs(["🧪 Batch Deep Dive", "📡 Channel X-Ray", "📥 Utility"])

    # ==================================================
    # TAB 1: BATCH DEEP DIVE (Multi-Video Comparison)
    # ==================================================
    with tab_batch:
        st.header("🧪 Multi-Video Comparative Analysis")
        st.markdown("Paste multiple links to compare performance, titles, and audience sentiment in one go.")
        
        raw_urls = st.text_area("Paste Video URLs (one per line or comma separated):", height=100)
        
        if "batch_df" not in st.session_state: st.session_state.batch_df = None

        if st.button("⚡ Process Batch"):
            ids = list(set(re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11})", raw_urls)))
            if ids:
                with st.spinner(f"Extracting Metadata & Sentiment for {len(ids)} videos..."):
                    df = get_batch_details(ids, YT_KEY)
                    st.session_state.batch_df = df
                    st.success("✅ Analysis Complete")
            else: st.warning("No valid links found.")

        if st.session_state.batch_df is not None:
            st.divider()
            # Metrics Display
            df = st.session_state.batch_df
            st.dataframe(df, hide_index=True, use_container_width=True)
            
            # Chat Comparison
            st.subheader("💬 Comparative Strategy Chat")
            
            if "batch_chat" not in st.session_state: st.session_state.batch_chat = []
            for m in st.session_state.batch_chat:
                with st.chat_message(m["role"]): st.markdown(m["content"])

            if prompt := st.chat_input("Ex: Compare the titles. Which hook is stronger?"):
                st.session_state.batch_chat.append({"role": "user", "content": prompt})
                with st.chat_message("user"): st.markdown(prompt)
                
                with st.chat_message("assistant"):
                    with st.spinner("Strategist Thinking..."):
                        # Prepare data for AI
                        csv_data = df.to_csv(index=False)
                        full_prompt = f"""
                        {STRATEGIST_PERSONA}
                        
                        TASK: Analyze this dataset of multiple videos. Compare them based on the User Query.
                        
                        DATASET:
                        {csv_data}
                        
                        USER QUERY: {prompt}
                        """
                        res = generate_ai_response(full_prompt, GEMINI_KEY)
                        st.markdown(res)
                        st.session_state.batch_chat.append({"role": "assistant", "content": res})

    # ==================================================
    # TAB 2: CHANNEL X-RAY (The Audit Machine)
    # ==================================================
    with tab_audit:
        st.header("📡 Channel Strategic Audit")
        
        col_inp, col_btn = st.columns([3, 1])
        with col_inp:
            handle = st.text_input("Channel Handle (e.g. @FrontThree):", placeholder="@FrontThree")
        with col_btn:
            st.write("")
            st.write("")
            run_audit = st.button("🚀 Scan Channel")

        if "audit_data" not in st.session_state: st.session_state.audit_data = None
        if "channel_info" not in st.session_state: st.session_state.channel_info = {}

        if run_audit and handle:
            with st.spinner("Accessing YouTube Mainframe..."):
                ch_id = get_channel_id(handle, YT_KEY)
                if ch_id:
                    videos, name, subs = get_channel_uploads(ch_id, YT_KEY, limit=50) # Last 50 videos
                    st.session_state.audit_data = pd.DataFrame(videos)
                    st.session_state.channel_info = {"Name": name, "Subs": subs}
                    st.success(f"✅ Scanned {len(videos)} recent uploads from {name}")
                else: st.error("Channel not found.")

        if st.session_state.audit_data is not None:
            df = st.session_state.audit_data
            
            # Channel Header
            c1, c2, c3 = st.columns(3)
            c1.metric("Channel", st.session_state.channel_info['Name'])
            c2.metric("Subscribers", st.session_state.channel_info['Subs'])
            c3.metric("Videos Analyzed", len(df))

            # TIMEFRAME TABS
            t_7, t_28, t_90, t_life = st.tabs(["Last 7 Days", "Last 28 Days", "Last 90 Days", "Dataset Lifetime"])
            
            # Helper to filter DF
            now = datetime.utcnow()
            def filter_df(days):
                if days == 0: return df
                cutoff = now - timedelta(days=days)
                # Convert Published to datetime
                df['Published_DT'] = pd.to_datetime(df['Published'])
                # Make naive to avoid timezone issues
                df['Published_DT'] = df['Published_DT'].dt.tz_localize(None) 
                return df[df['Published_DT'] > (now - timedelta(days=days))]

            # LOGIC FOR EACH TAB
            for tab, days in zip([t_7, t_28, t_90, t_life], [7, 28, 90, 0]):
                with tab:
                    filtered = filter_df(days)
                    if filtered.empty:
                        st.info("No videos published in this timeframe.")
                    else:
                        # SEPARATE SHORTS vs LONGFORM
                        st.subheader("📊 Performance Matrix")
                        
                        f_long = filtered[filtered['Type'] == "📹 Longform"]
                        f_short = filtered[filtered['Type'] == "📱 Short"]
                        
                        col_l, col_s = st.columns(2)
                        
                        with col_l:
                            st.markdown("### 📹 Longform")
                            if not f_long.empty:
                                st.dataframe(f_long[['Title', 'Views', 'Likes']], hide_index=True)
                                avg_v = f_long['Views'].mean()
                                st.caption(f"Avg Views: {avg_v:,.0f}")
                            else: st.write("No Longform content.")

                        with col_s:
                            st.markdown("### 📱 Shorts")
                            if not f_short.empty:
                                st.dataframe(f_short[['Title', 'Views', 'Likes']], hide_index=True)
                                avg_v = f_short['Views'].mean()
                                st.caption(f"Avg Views: {avg_v:,.0f}")
                            else: st.write("No Shorts content.")

                        # GALLERY VIEW
                        st.subheader("🖼️ Thumbnail Grid")
                        cols = st.columns(5)
                        for index, row in filtered.head(10).iterrows():
                            with cols[index % 5]:
                                st.image(row['Thumb'], use_column_width=True)
                                st.caption(f"{row['Views']/1000:.1f}k • {row['Type']}")

                        # AI ANALYSIS BUTTON
                        if st.button(f"🧠 Analyze Strategy ({days if days > 0 else 'All'} Days)", key=f"btn_{days}"):
                            with st.spinner("Analyzing patterns..."):
                                csv_data = filtered.to_csv(index=False)
                                prompt = f"""
                                {STRATEGIST_PERSONA}
                                TASK: Analyze this channel's performance over the last {days} days (or lifetime).
                                Look for patterns in Titles, Thumbnails (implied by CTR/Views), and Format (Shorts vs Long).
                                DATA:
                                {csv_data}
                                OUTPUT: 3 Strategic Bullet Points + 1 Critical Area for Improvement.
                                """
                                res = generate_ai_response(prompt, GEMINI_KEY)
                                st.info(res)

    # ==================================================
    # TAB 3: UTILITY (Simple Downloader)
    # ==================================================
    with tab_dl:
        st.header("📥 Quick Asset Grabber")
        u = st.text_input("URL:")
        if u:
            vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", u)
            if vid_match:
                vid_id = vid_match.group(1)
                st.image(f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg", width=300)
                st.markdown(f"**Thumbnail:** [Download](https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg)")

if __name__ == "__main__":
    if check_login():
        main_app()
