"""
AI Script-to-Video Generator — Streamlit App
-----------------------------------------------
Streamlit version of the original Flask app, with the same features:
- Generate a video from a script (Pexels images + AI voiceover)
- Upload your own video instead
- Upload your own audio to attach to either
- Turn AI voiceover on/off
- Choose between English (Male/Female) and Urdu (Male/Female) voices
- Standalone "Generate Audio from Script" and "Extract Audio from
  Video" actions
- Smart final-audio logic (same priority rules as Flask version)
- Smart duration matching when script + own audio are both given
"""

import os
import shutil
import uuid
import streamlit as st

from modules.script_processor import process_script, assign_durations_from_total
from modules.voiceover import generate_all_voiceovers
from modules.image_generator import generate_all_images
from modules.video_builder import build_final_video, build_full_voiceover_track
from modules.video_audio_merger import merge_video_audio, extract_audio, get_audio_duration


st.set_page_config(page_title="AI Script-to-Video Generator", page_icon="🎬", layout="centered")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_FOLDER = os.path.join(BASE_DIR, "static", "audio")
IMAGE_FOLDER = os.path.join(BASE_DIR, "static", "images")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

for folder in (AUDIO_FOLDER, IMAGE_FOLDER, OUTPUT_FOLDER, UPLOAD_FOLDER):
    os.makedirs(folder, exist_ok=True)

VOICE_OPTIONS = {
    "English Female": "en-US-AriaNeural",
    "English Male": "en-US-GuyNeural",
    "English Female (UK)": "en-GB-SoniaNeural",
    "Urdu Female": "ur-PK-UzmaNeural",
    "Urdu Male": "ur-PK-AsadNeural",
}

ALLOWED_VIDEO_EXT = {"mp4", "mov", "avi", "mkv", "webm"}
ALLOWED_AUDIO_EXT = {"mp3", "wav", "m4a", "aac", "ogg"}
SILENT_SCENE_DURATION = 4.0


def is_allowed_file(filename, allowed_ext):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_ext


def save_uploaded_file(uploaded_file, folder) -> str:
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, uploaded_file.name)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path


st.title("🎬 AI Script-to-Video Generator")
st.caption("Turn a script into a narrated AI video, or bring your own footage and audio.")


# --- Step 1: Script -> Video / Audio ---

st.header("1. Generate video from script")

script_text = st.text_area(
    "Script",
    height=180,
    placeholder="Paste your full script here... (leave empty if uploading your own video below)",
)

include_voiceover = st.checkbox("Include AI voiceover", value=True)
st.caption("Turn off for a silent video (images only, e.g. to add your own music/audio in Step 3).")

voice_label = None
if include_voiceover:
    voice_label = st.selectbox("Voiceover voice", list(VOICE_OPTIONS.keys()))

pexels_key = st.text_input(
    "Pexels API key",
    type="password",
    help="Required for scene images. Get a free key at https://www.pexels.com/api/",
)

if st.button("🎙️ Generate Audio from Script", use_container_width=True):
    if not script_text.strip():
        st.error("Please paste a script first.")
    else:
        with st.spinner("Generating audio from your script..."):
            try:
                job_id = str(uuid.uuid4())[:8]
                job_audio_folder = os.path.join(AUDIO_FOLDER, job_id)
                os.makedirs(job_audio_folder, exist_ok=True)

                scenes = process_script(script_text)
                voice_code = VOICE_OPTIONS.get(voice_label, "en-US-AriaNeural")
                scenes = generate_all_voiceovers(scenes, job_audio_folder, voice_code)

                audio_output_path = os.path.join(OUTPUT_FOLDER, f"script_audio_{job_id}.mp3")
                build_full_voiceover_track(scenes, audio_output_path)

                st.session_state["script_audio_path"] = audio_output_path
            except Exception as e:
                st.error(f"Error: {e}")

if st.session_state.get("script_audio_path"):
    st.success("Audio ready!")
    with open(st.session_state["script_audio_path"], "rb") as f:
        audio_bytes = f.read()
    st.audio(audio_bytes, format="audio/mp3")
    st.download_button("Download audio", audio_bytes, file_name="script_audio.mp3", mime="audio/mpeg")

st.divider()


# --- Step 2: Upload your own video ---

st.header("2. Or upload your own video")
st.caption("If you upload a video, the script above is ignored and no AI video is generated.")

video_file = st.file_uploader("Your video file", type=list(ALLOWED_VIDEO_EXT), key="video_uploader")

if st.button("🔊 Extract Audio from Video", use_container_width=True):
    if video_file is None:
        st.error("Please choose a video file first.")
    else:
        with st.spinner("Extracting audio from your video..."):
            try:
                job_id = str(uuid.uuid4())[:8]
                job_upload_folder = os.path.join(UPLOAD_FOLDER, job_id)
                saved_video_path = save_uploaded_file(video_file, job_upload_folder)

                audio_output_path = os.path.join(OUTPUT_FOLDER, f"video_audio_{job_id}.mp3")
                extract_audio(saved_video_path, audio_output_path)

                st.session_state["extracted_audio_path"] = audio_output_path
            except RuntimeError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Error: {e}")

if st.session_state.get("extracted_audio_path"):
    st.success("Audio extracted!")
    with open(st.session_state["extracted_audio_path"], "rb") as f:
        audio_bytes = f.read()
    st.audio(audio_bytes, format="audio/mp3")
    st.download_button("Download extracted audio", audio_bytes, file_name="extracted_audio.mp3", mime="audio/mpeg", key="dl_extracted")

st.divider()


# --- Step 3: Add your own audio ---

st.header("3. Add your own audio")
st.caption("Works with either option above. Replaces the video's current audio track.")

audio_file = st.file_uploader("Your audio file", type=list(ALLOWED_AUDIO_EXT), key="audio_uploader")

st.divider()


# --- Main: Generate Video ---

if st.button("🚀 Generate Video", type="primary", use_container_width=True):
    has_uploaded_video = video_file is not None
    has_uploaded_audio = audio_file is not None

    if not script_text.strip() and not has_uploaded_video:
        st.error("Please paste a script OR upload a video.")
    elif not has_uploaded_video and not pexels_key:
        st.error(
            "A Pexels API key is required to fetch scene images. "
            "Get a free key at https://www.pexels.com/api/"
        )
    else:
        with st.spinner("Processing your video... this can take a few minutes"):
            try:
                job_id = str(uuid.uuid4())[:8]
                job_upload_folder = os.path.join(UPLOAD_FOLDER, job_id)
                job_audio_folder = os.path.join(AUDIO_FOLDER, job_id)
                job_image_folder = os.path.join(IMAGE_FOLDER, job_id)
                os.makedirs(job_upload_folder, exist_ok=True)
                os.makedirs(job_audio_folder, exist_ok=True)
                os.makedirs(job_image_folder, exist_ok=True)

                voiceover_audio_path = None
                extracted_audio_path = None
                video_ext = "mp4"

                saved_audio_path = None
                if has_uploaded_audio:
                    if not is_allowed_file(audio_file.name, ALLOWED_AUDIO_EXT):
                        raise RuntimeError("Audio file type not supported")
                    saved_audio_path = save_uploaded_file(audio_file, job_upload_folder)

                if has_uploaded_video:
                    if not is_allowed_file(video_file.name, ALLOWED_VIDEO_EXT):
                        raise RuntimeError("Video file type not supported")
                    video_ext = video_file.name.rsplit(".", 1)[1].lower()
                    saved_video_path = save_uploaded_file(video_file, job_upload_folder)
                    base_video_path = saved_video_path

                    try:
                        extracted_audio_path = os.path.join(OUTPUT_FOLDER, f"extracted_audio_{job_id}.mp3")
                        extract_audio(saved_video_path, extracted_audio_path)
                    except RuntimeError:
                        extracted_audio_path = None
                else:
                    scenes = process_script(script_text)

                    if has_uploaded_audio:
                        total_duration = get_audio_duration(saved_audio_path)
                        scenes = assign_durations_from_total(scenes, total_duration)
                    elif include_voiceover:
                        voice_code = VOICE_OPTIONS.get(voice_label, "en-US-AriaNeural")
                        scenes = generate_all_voiceovers(scenes, job_audio_folder, voice_code)

                        voiceover_audio_path = os.path.join(OUTPUT_FOLDER, f"voiceover_{job_id}.mp3")
                        build_full_voiceover_track(scenes, voiceover_audio_path)
                    else:
                        for scene in scenes:
                            scene["duration"] = SILENT_SCENE_DURATION

                    scenes = generate_all_images(scenes, job_image_folder, pexels_key)

                    base_video_path = os.path.join(OUTPUT_FOLDER, f"base_{job_id}.mp4")
                    build_final_video(scenes, base_video_path)

                if has_uploaded_audio:
                    final_output_path = os.path.join(OUTPUT_FOLDER, f"video_{job_id}.mp4")
                    merge_video_audio(base_video_path, saved_audio_path, final_output_path)
                elif has_uploaded_video:
                    final_output_path = os.path.join(OUTPUT_FOLDER, f"video_{job_id}.{video_ext}")
                    shutil.copy2(base_video_path, final_output_path)
                else:
                    final_output_path = base_video_path

                st.session_state["final_video_path"] = final_output_path
                st.session_state["voiceover_audio_path_result"] = voiceover_audio_path
                st.session_state["extracted_audio_path_result"] = extracted_audio_path

            except Exception as e:
                st.error(f"Error: {e}")

if st.session_state.get("final_video_path"):
    st.success("Video is ready!")
    with open(st.session_state["final_video_path"], "rb") as f:
        video_bytes = f.read()
    st.video(video_bytes)
    st.download_button(
        "⬇️ Download video",
        video_bytes,
        file_name=os.path.basename(st.session_state["final_video_path"]),
        mime="video/mp4",
    )

    if st.session_state.get("voiceover_audio_path_result"):
        with open(st.session_state["voiceover_audio_path_result"], "rb") as f:
            vo_bytes = f.read()
        st.download_button("⬇️ Download voice note (audio only)", vo_bytes, file_name="voiceover.mp3", mime="audio/mpeg", key="dl_vo")

    if st.session_state.get("extracted_audio_path_result"):
        with open(st.session_state["extracted_audio_path_result"], "rb") as f:
            ex_bytes = f.read()
        st.download_button("⬇️ Download extracted audio from your video", ex_bytes, file_name="extracted_audio.mp3", mime="audio/mpeg", key="dl_ex_main")

st.divider()
st.caption("Built with Streamlit, edge-tts / gTTS, Pexels, and MoviePy")