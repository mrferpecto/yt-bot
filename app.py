import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
import pandas as pd
import yt_dlp
import zipfile
import io
import time
import re

# --- CONFIGURATION ---
st.set_page_config(page_title="FrontThree Suite", page_icon="⚡", layout="wide")

# --- AUTHENTICATION (FIXED) ---
def check_login():
    """Handles the login gate securely."""
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        return True

    # Login UI
    st.title("🔒 Front Three's YouTube AI Bot")
    st.markdown("Please log in to access the bot.")

    with st.form("login_form"):
        username_input = st.text_input("Username")
        password_input = st.text_input("Password", type="password") # Variable name is 'password_input'
        submit_button = st.form_submit_button("Login")

        if submit_button:
            try:
                # Check against Streamlit Secrets
                real_user = st.secrets["login"]["username"]
                real_pass = st.secrets["login"]["password"]

                # THE FIX: We now compare the correct variables
                if username_input == real_user and password_input == real_pass:
                    st.session_state["authenticated"] = True
                    st.success("✅ Login successful. Logging in...")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Access Denied: Incorrect credentials.")
            except KeyError:
                st.error("🚨 System Error: Secrets are not configured correctly in Streamlit Cloud.")
                st.info("Check your [login] section in the settings.")
            except Exception as e:
                st.error(f"❌ An unexpected error occurred: {e}")
    
    return False

# --- API HELPER FUNCTIONS ---

def get_video_stats_batch(video_ids, api_key):
    """Fetches statistics for a list of video IDs."""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        request = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(video_ids)
        )
        response = request.execute()
        return response.get('items', [])
    except Exception as e:
        st.error(f"YouTube API Error: {e}")
        return []

def get_video_comments(video_id, api_key):
    """Fetches comments for a single video."""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        request = youtube.commentThreads().list(
            part="snippet", videoId=video_id, maxResults=40, textFormat="plainText"
        )
        response = request.execute()
        comments = [item['snippet']['topLevelComment']['snippet']['textDisplay'] for item in response['items']]
        return comments
    except Exception as e:
        st.error(f"Error fetching comments: {e}")
        return []

def download_thumbnail_bytes(url):
    """Downloads thumbnail image to memory."""
    buffer = io.BytesIO()
    ydl_opts = {'quiet': True, 'writethumbnail': True, 'skip_download': True, 'outtmpl': '-'}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            thumb_url = info['thumbnail']
            import requests
            return requests.get(thumb_url).content, f"{info['title'][:50]}.jpg" # Limit filename length
    except Exception as e:
        return None, str(e)

# --- MAIN APPLICATION ---

def main_app():
    # Load API Keys securely
    try:
        YT_KEY = st.secrets["api"]["youtube_key"]
        GEMINI_KEY = st.secrets["api"]["gemini_key"]
    except KeyError:
        st.error("🚨 API Keys are missing in secrets.toml (check [api] section).")
        st.stop()

    # Sidebar
    st.sidebar.success(f"User: {st.secrets['login']['username']}")
    if st.sidebar.button("Logout"):
        st.session_state["authenticated"] = False
        st.rerun()

    st.title("⚡ FrontThree YT Management Suite")

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 Analytics Chat", "📥 Downloader", "🔴 Deep Dive"])

    # ==========================================
    # TAB 1: GLOBAL ANALYTICS & CHAT
    # ==========================================
    with tab1:
        st.header("🧠 Chat with your Data")
        st.markdown("Paste multiple video URLs to analyze patterns.")

        urls_input = st.text_area("Paste Video URLs (comma separated):", height=100)
        
        if "analytics_data" not in st.session_state:
            st.session_state.analytics_data = None

        if st.button("Load Data"):
            ids = re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11})", urls_input)
            ids = list(set(ids)) # Remove duplicates
            
            if ids:
                with st.spinner(f"Analyzing {len(ids)} videos..."):
                    raw_data = get_video_stats_batch(ids, YT_KEY)
                    
                    clean_data = []
                    for item in raw_data:
                        stats = item['statistics']
                        clean_data.append({
                            "Title": item['snippet']['title'],
                            "Views": int(stats.get('viewCount', 0)),
                            "Likes": int(stats.get('likeCount', 0)),
                            "Comments": int(stats.get('commentCount', 0)),
                            "Date": item['snippet']['publishedAt'][:10]
                        })
                    
                    st.session_state.analytics_data = pd.DataFrame(clean_data)
                    st.success("✅ Data Loaded!")
            else:
                st.warning("No valid URLs found.")

        # Chat Interface
        if st.session_state.analytics_data is not None:
            st.dataframe(st.session_state.analytics_data, hide_index=True)
            
            # Chat History
            if "messages" not in st.session_state:
                st.session_state.messages = []

            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            if prompt := st.chat_input("Ask about your data (e.g., 'Best performing title?'):"):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)

                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        # Gemini Call
                        genai.configure(api_key=GEMINI_KEY)
                        model = genai.GenerativeModel('model = genai.GenerativeModel('gemini-1.5-flash')
                        
                        context = st.session_state.analytics_data.to_string()
                        full_prompt = (
                            f"You are a YouTube Analytics expert. Here is my video data:\n{context}\n\n"
                            f"Question: {prompt}\nAnswer in English."
                        )
                        response = model.generate_content(full_prompt)
                        st.markdown(response.text)
                        st.session_state.messages.append({"role": "assistant", "content": response.text})

    # ==========================================
    # TAB 2: DOWNLOADER CENTER
    # ==========================================
    with tab2:
        st.header("📥 Media Downloader")
        dl_urls = st.text_area("Paste URLs to download assets:", key="dl_area")
        video_ids = re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11})", dl_urls)

        col1, col2 = st.columns(2)

        # Thumbnails (Batch ZIP)
        with col1:
            st.subheader("Thumbnails")
            if st.button("Download All Thumbnails (ZIP)"):
                if video_ids:
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w") as zf:
                        progress = st.progress(0)
                        for i, vid_id in enumerate(video_ids):
                            url = f"https://www.youtube.com/watch?v={vid_id}"
                            data, name = download_thumbnail_bytes(url)
                            if data: zf.writestr(name, data)
                            progress.progress((i + 1) / len(video_ids))
                    
                    st.download_button(
                        label="⬇️ Download ZIP",
                        data=zip_buffer.getvalue(),
                        file_name="thumbnails.zip",
                        mime="application/zip"
                    )
                else:
                    st.warning("No URLs found.")

        # Video Links (Direct)
        with col2:
            st.subheader("Video Files (MP4)")
            if st.button("Generate Download Links"):
                if video_ids:
                    st.info("Generating high-speed direct links (Cloud Safe Mode):")
                    for vid_id in video_ids:
                        url = f"https://www.youtube.com/watch?v={vid_id}"
                        try:
                            with yt_dlp.YoutubeDL({'quiet':True}) as ydl:
                                info = ydl.extract_info(url, download=False)
                                # Find best MP4
                                for f in info['formats']:
                                    if f.get('ext') == 'mp4' and f.get('vcodec') != 'none':
                                        st.markdown(f"🎥 **{info['title']}**: [Click to Download]({f['url']})")
                                        break
                        except:
                            st.error(f"Error processing {vid_id}")
                else:
                    st.warning("No URLs found.")

    # ==========================================
    # TAB 3: SINGLE VIDEO DEEP DIVE
    # ==========================================
    with tab3:
        st.header("🔴 Single Video Analysis")
        sv_url = st.text_input("YouTube URL:", placeholder="https://...")
        
        task = st.selectbox("Select Action:", [
            "Summarize Comments", 
            "Generate Video Ideas", 
            "Detect Unanswered Questions", 
            "SEO Optimization"
        ])

        if st.button("Analyze Video"):
            vid_id = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", sv_url)
            if vid_id:
                with st.spinner("Fetching comments..."):
                    comments = get_video_comments(vid_id.group(1), YT_KEY)
                
                if comments:
                    st.success(f"Analyzed {len(comments)} comments.")
                    text_data = "\n".join(comments)
                    
                    # Prompts
                    prompts = {
                        "Summarize Comments": f"Summarize sentiment and main points:\n{text_data}",
                        "Generate Video Ideas": f"Suggest 5 future video titles based on this feedback:\n{text_data}",
                        "Detect Unanswered Questions": f"List specific questions asking for help:\n{text_data}",
                        "SEO Optimization": f"Create SEO tags and description based on these topics:\n{text_data}"
                    }
                    
                    with st.spinner("Gemini is thinking..."):
                        genai.configure(api_key=GEMINI_KEY)
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        response = model.generate_content(prompts[task])
                        st.markdown("### 🤖 Results")
                        st.write(response.text)
                else:
                    st.warning("No comments found.")
            else:
                st.error("Invalid URL.")

# --- ENTRY POINT ---
if __name__ == "__main__":
    if check_login():
        main_app()
