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
    """Handles the login gate securely."""
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        return True

    # Login UI
    st.title("🔒 Restricted Access")
    st.markdown("Please log in to access the FrontThree Tools.")

    with st.form("login_form"):
        username_input = st.text_input("Username")
        password_input = st.text_input("Password", type="password") 
        submit_button = st.form_submit_button("Login")

        if submit_button:
            try:
                # Check against Streamlit Secrets
                real_user = st.secrets["login"]["username"]
                real_pass = st.secrets["login"]["password"]

                # Validation
                if username_input == real_user and password_input == real_pass:
                    st.session_state["authenticated"] = True
                    st.success("✅ Access Granted. Loading...")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ Access Denied: Incorrect credentials.")
            except KeyError:
                st.error("🚨 System Error: Secrets are not configured correctly in Streamlit Cloud.")
                st.info("Please check your [login] section in the settings.")
            except Exception as e:
                st.error(f"❌ An unexpected error occurred: {e}")
    
    return False

# --- API HELPER FUNCTIONS ---

def get_video_stats_batch(video_ids, api_key):
    """Fetches statistics for a list of video IDs."""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        all_items = []
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i+50]
            request = youtube.videos().list(
                part="snippet,statistics",
                id=",".join(chunk)
            )
            response = request.execute()
            all_items.extend(response.get('items', []))
        return all_items
    except Exception as e:
        st.error(f"YouTube API Error: {e}")
        return []

def get_video_comments(video_id, api_key, max_limit=300):
    """Fetches comments with pagination up to max_limit."""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        comments = []
        next_page_token = None
        
        while len(comments) < max_limit:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=100,
                textFormat="plainText",
                pageToken=next_page_token
            )
            response = request.execute()
            
            for item in response['items']:
                text = item['snippet']['topLevelComment']['snippet']['textDisplay']
                comments.append(text)
            
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
                
        return comments
    except Exception as e:
        st.error(f"Error fetching comments: {e}")
        return comments

def download_thumbnail_bytes(url):
    """Downloads thumbnail image to memory."""
    try:
        ydl_opts = {'quiet': True, 'writethumbnail': True, 'skip_download': True, 'outtmpl': '-'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            thumb_url = info['thumbnail']
            response = requests.get(thumb_url)
            safe_title = re.sub(r'[\\/*?:"<>|]', "", info['title'])
            return response.content, f"{safe_title[:30]}.jpg"
    except Exception as e:
        return None, str(e)

# --- AI WRAPPER (ROBUST VERSION) ---
def ask_gemini(prompt, api_key):
    """Tries Flash first, falls back to Pro, handles library errors."""
    genai.configure(api_key=api_key)
    
    models_to_try = ['gemini-1.5-flash', 'gemini-pro']
    
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            return model.generate_content(prompt).text
        except Exception:
            continue # Try next model silently
            
    return "❌ AI Error: Could not connect to Gemini. Please delete and redeploy the app to update libraries."

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
            ids = list(set(re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11})", urls_input)))
            
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
                    st.success(f"✅ Loaded data for {len(clean_data)} videos!")
            else:
                st.warning("No valid YouTube URLs found.")

        # Chat Interface
        if st.session_state.analytics_data is not None:
            st.dataframe(st.session_state.analytics_data, hide_index=True)
            
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
                        context = st.session_state.analytics_data.to_string()
                        full_prompt = (
                            f"You are a YouTube Analytics expert. Here is my video data:\n{context}\n\n"
                            f"Question: {prompt}\nAnswer in English. Be concise and data-driven."
                        )
                        response = ask_gemini(full_prompt, GEMINI_KEY)
                        st.markdown(response)
                        st.session_state.messages.append({"role": "assistant", "content": response})

    # ==========================================
    # TAB 2: DOWNLOADER CENTER
    # ==========================================
    with tab2:
        st.header("📥 Media Downloader")
        st.info("ℹ️ Note: Cloud downloads are limited to the best available MP4 with audio (usually 720p). For 1080p/4K, this tool must be run locally.")
        
        dl_urls = st.text_area("Paste URLs to download assets:", key="dl_area")
        video_ids = list(set(re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11})", dl_urls)))

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
                    
                    st.success("ZIP Ready!")
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
            if st.button("Get Download Links"):
                if video_ids:
                    st.info("Generating direct links...")
                    for vid_id in video_ids:
                        url = f"https://www.youtube.com/watch?v={vid_id}"
                        try:
                            with yt_dlp.YoutubeDL({'quiet':True}) as ydl:
                                info = ydl.extract_info(url, download=False)
                                title = info.get('title', 'Video')
                                
                                # Find best MP4 with Audio
                                best_url = None
                                best_res = 0
                                for f in info['formats']:
                                    if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4':
                                        h = f.get('height', 0)
                                        if h > best_res:
                                            best_res = h
                                            best_url = f['url']
                                
                                if best_url:
                                    st.markdown(f"🎥 **{title}** ({best_res}p): [Click to Download]({best_url})")
                                else:
                                    st.warning(f"No direct MP4 link found for {title}")
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
            vid_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", sv_url)
            if vid_id_match:
                with st.spinner("Fetching UP TO 300 comments..."):
                    comments = get_video_comments(vid_id_match.group(1), YT_KEY, max_limit=300)
                
                if comments:
                    st.success(f"Analyzed {len(comments)} comments.")
                    text_data = "\n".join(comments)
                    
                    # Limit text size for AI safety
                    if len(text_data) > 30000:
                         text_data = text_data[:30000] + "\n...(truncated)"

                    prompts = {
                        "Summarize Comments": f"Summarize sentiment and main points:\n{text_data}",
                        "Generate Video Ideas": f"Suggest 5 future video titles based on this feedback:\n{text_data}",
                        "Detect Unanswered Questions": f"List specific questions asking for help:\n{text_data}",
                        "SEO Optimization": f"Create SEO tags and description based on these topics:\n{text_data}"
                    }
                    
                    with st.spinner("Gemini is thinking..."):
                        response = ask_gemini(prompts[task], GEMINI_KEY)
                        st.markdown("### 🤖 Results")
                        st.markdown(response)
                else:
                    st.warning("No comments found (or comments disabled).")
            else:
                st.error("Invalid URL.")

# --- ENTRY POINT ---
if __name__ == "__main__":
    if check_login():
        main_app()
