"""
Main Flask App
---------------
This is the entry point. It provides a web page where the user can:

MODE 1: Paste a script -> AI finds a matching photo per scene (via
        Pexels), generates voiceover, and builds a video
MODE 2: Upload their OWN video file (skip generation entirely)
MODE 3: Either of the above, PLUS upload their own audio file, which
        gets attached to the final video (replacing the AI voiceover
        if there was one)

The user can also turn OFF the AI voiceover for a silent video, and
can choose between English (Male/Female) and Urdu (Male/Female)
narration voices.

FINAL AUDIO LOGIC (what actually plays in the final video):
- Own video uploaded + own audio uploaded  -> own audio is attached
  onto the own video (replacing its original audio).
- Own video uploaded + NO own audio        -> own video's original
  audio is kept as-is.
- Script given + AI voiceover ON  + no own audio -> AI voiceover plays.
- Script given + AI voiceover ON  + own audio given -> own audio
  REPLACES the AI voiceover.
- Script given + AI voiceover OFF + own audio given -> own audio plays
  over the silent AI-generated video.
- Script given + AI voiceover OFF + no own audio -> video is silent.

STANDALONE AUDIO ROUTES (separate buttons, work without generating a video):
- /generate_audio_from_script  -> turns just a script into a downloadable audio file
- /extract_audio_from_video    -> pulls the audio track out of an uploaded video

EXTRA OUTPUTS from the main /generate route (in addition to the final video):
- If AI voiceover was generated from a script, a standalone "voice
  note" audio file is also produced and offered as a separate download.
- If the user uploaded their own video, its original audio track is
  extracted into its own standalone audio file and also offered as a
  separate download.

--------------------------------------------------------------------
EXE PACKAGING NOTES (added, does not change any behavior above):
This app can be bundled into a single .exe with PyInstaller so end
users don't need Python or any pip packages installed. Two helper
functions make this possible:

- resource_path(): finds bundled READ-ONLY files (like templates/)
  correctly whether running as a normal .py script or as a frozen
  PyInstaller .exe (which unpacks bundled files into a temp folder
  referenced by sys._MEIPASS).
- get_base_dir(): decides where to put WRITABLE runtime data
  (uploads/, outputs/, static/audio/, static/images/). When frozen,
  this is the folder next to the .exe file (NOT the temp bundle,
  which is read-only and gets deleted after the app closes).

The app still needs an internet connection at runtime (Pexels, edge-tts,
gTTS, and translation are all online services) - packaging as an .exe
only removes the need to install Python/pip packages, it does not make
the app work fully offline.
--------------------------------------------------------------------
"""

import os
import sys
import shutil
import threading
import webbrowser
import uuid
from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename

from modules.script_processor import process_script
from modules.voiceover import generate_all_voiceovers
from modules.image_generator import generate_all_images
from modules.video_builder import build_final_video, build_full_voiceover_track
from modules.video_audio_merger import merge_video_audio, extract_audio


# ---------------------------------------------------------------------
# EXE-PACKAGING HELPERS
# ---------------------------------------------------------------------

def resource_path(relative_path):
    """
    Get the absolute path to a bundled, READ-ONLY resource (like the
    templates/ folder). Works both when running normally as a .py file
    and when running as a PyInstaller-frozen .exe (which extracts
    bundled files into a temporary folder at sys._MEIPASS).
    """
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def get_base_dir():
    """
    Get the folder where WRITABLE runtime data (uploads, outputs,
    generated audio/images) should live. When running as a frozen
    .exe, this is the folder the .exe file sits in (so generated files
    persist and are easy to find) - NOT the temporary bundle folder,
    which is read-only and gets wiped when the app closes.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


IS_FROZEN = getattr(sys, "frozen", False)
BASE_DIR = get_base_dir()

# static_folder=None disables Flask's automatic "/static" file serving,
# which we don't use (all our CSS/JS is inline in index.html, and file
# downloads go through the explicit /download route instead). This
# avoids any path confusion between the bundled templates and our own
# runtime "static/audio" and "static/images" data folders below.
app = Flask(__name__, template_folder=resource_path("templates"), static_folder=None)

AUDIO_FOLDER = os.path.join(BASE_DIR, "static", "audio")
IMAGE_FOLDER = os.path.join(BASE_DIR, "static", "images")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

VOICE_OPTIONS = {
    "english_female": "en-US-AriaNeural",
    "english_male": "en-US-GuyNeural",
    "english_female_uk": "en-GB-SoniaNeural",
    "urdu_female": "ur-PK-UzmaNeural",
    "urdu_male": "ur-PK-AsadNeural",
}

ALLOWED_VIDEO_EXT = {"mp4", "mov", "avi", "mkv", "webm"}
ALLOWED_AUDIO_EXT = {"mp3", "wav", "m4a", "aac", "ogg"}


def is_allowed_file(filename, allowed_ext):
    """Check the uploaded file has an extension we support."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_ext


@app.route("/")
def home():
    return render_template("index.html", voices=VOICE_OPTIONS)


@app.route("/generate", methods=["POST"])
def generate_video():
    """
    Main endpoint. Handles all three modes, plus the two extra
    standalone-audio outputs (voice note / extracted audio).
    """
    script_text = request.form.get("script", "").strip()
    voice_choice = request.form.get("voice", "english_female")
    pexels_key = request.form.get("pexels_key", "").strip() or None
    include_voiceover = request.form.get("include_voiceover") == "on"
    SILENT_SCENE_DURATION = 4.0

    uploaded_video = request.files.get("video_file")
    uploaded_audio = request.files.get("audio_file")

    has_uploaded_video = uploaded_video and uploaded_video.filename != ""
    has_uploaded_audio = uploaded_audio and uploaded_audio.filename != ""

    if not script_text and not has_uploaded_video:
        return jsonify({"error": "Please paste a script OR upload a video"}), 400

    if not has_uploaded_video and not pexels_key:
        return jsonify({
            "error": "A Pexels API key is required to fetch scene images. "
                     "Get a free key at https://www.pexels.com/api/ and paste "
                     "it into the 'Pexels API key' field."
        }), 400

    job_id = str(uuid.uuid4())[:8]
    job_upload_folder = f"{UPLOAD_FOLDER}/{job_id}"
    job_audio_folder = f"{AUDIO_FOLDER}/{job_id}"
    job_image_folder = f"{IMAGE_FOLDER}/{job_id}"
    os.makedirs(job_upload_folder, exist_ok=True)
    os.makedirs(job_audio_folder, exist_ok=True)
    os.makedirs(job_image_folder, exist_ok=True)

    voiceover_audio_path = None
    extracted_audio_path = None
    video_ext = "mp4"  # default, overwritten below when a video is uploaded

    try:
        if has_uploaded_video:
            if not is_allowed_file(uploaded_video.filename, ALLOWED_VIDEO_EXT):
                return jsonify({"error": "Video file type not supported"}), 400

            video_filename = secure_filename(uploaded_video.filename)
            video_ext = video_filename.rsplit(".", 1)[1].lower()
            saved_video_path = f"{job_upload_folder}/{video_filename}"
            uploaded_video.save(saved_video_path)

            base_video_path = saved_video_path

            try:
                extracted_audio_path = f"{OUTPUT_FOLDER}/extracted_audio_{job_id}.mp3"
                extract_audio(saved_video_path, extracted_audio_path)
            except RuntimeError:
                extracted_audio_path = None
        else:
            scenes = process_script(script_text)

            if include_voiceover:
                voice = VOICE_OPTIONS.get(voice_choice, "en-US-AriaNeural")
                scenes = generate_all_voiceovers(scenes, job_audio_folder, voice)

                voiceover_audio_path = f"{OUTPUT_FOLDER}/voiceover_{job_id}.mp3"
                build_full_voiceover_track(scenes, voiceover_audio_path)
            else:
                for scene in scenes:
                    scene["duration"] = SILENT_SCENE_DURATION

            scenes = generate_all_images(scenes, job_image_folder, pexels_key)

            base_video_path = f"{OUTPUT_FOLDER}/base_{job_id}.mp4"
            build_final_video(scenes, base_video_path)

        # ---- Decide the FINAL video ----
        if has_uploaded_audio:
            # User gave their own audio -> it always wins, gets attached
            # onto whichever base video we have (own video OR script video).
            if not is_allowed_file(uploaded_audio.filename, ALLOWED_AUDIO_EXT):
                return jsonify({"error": "Audio file type not supported"}), 400

            audio_filename = secure_filename(uploaded_audio.filename)
            saved_audio_path = f"{job_upload_folder}/{audio_filename}"
            uploaded_audio.save(saved_audio_path)

            final_output_path = f"{OUTPUT_FOLDER}/video_{job_id}.mp4"
            merge_video_audio(base_video_path, saved_audio_path, final_output_path)

        elif has_uploaded_video:
            # Own video, no separate audio given -> keep the video's
            # original audio as-is. The uploaded file lives in
            # uploads/<job_id>/, but /download only serves files from
            # outputs/, so we copy it there first.
            final_output_path = f"{OUTPUT_FOLDER}/video_{job_id}.{video_ext}"
            shutil.copy2(base_video_path, final_output_path)

        else:
            # Script-based video, already written straight into
            # outputs/ by build_final_video - nothing more to do.
            final_output_path = base_video_path

        response_data = {
            "success": True,
            "video_url": f"/download/{job_id}?path={os.path.basename(final_output_path)}"
        }

        if voiceover_audio_path:
            response_data["voiceover_audio_url"] = f"/download/{job_id}?path={os.path.basename(voiceover_audio_path)}"
        if extracted_audio_path:
            response_data["extracted_audio_url"] = f"/download/{job_id}?path={os.path.basename(extracted_audio_path)}"

        return jsonify(response_data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/generate_audio_from_script", methods=["POST"])
def generate_audio_from_script():
    """
    STANDALONE route: takes only a script + voice choice, generates the
    voiceover, and returns a single downloadable audio file. Does NOT
    generate any images or video.
    """
    script_text = request.form.get("script", "").strip()
    voice_choice = request.form.get("voice", "english_female")

    if not script_text:
        return jsonify({"error": "Please paste a script first"}), 400

    job_id = str(uuid.uuid4())[:8]
    job_audio_folder = f"{AUDIO_FOLDER}/{job_id}"
    os.makedirs(job_audio_folder, exist_ok=True)

    try:
        scenes = process_script(script_text)
        voice = VOICE_OPTIONS.get(voice_choice, "en-US-AriaNeural")
        scenes = generate_all_voiceovers(scenes, job_audio_folder, voice)

        audio_output_path = f"{OUTPUT_FOLDER}/script_audio_{job_id}.mp3"
        build_full_voiceover_track(scenes, audio_output_path)

        return jsonify({
            "success": True,
            "audio_url": f"/download/{job_id}?path={os.path.basename(audio_output_path)}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/extract_audio_from_video", methods=["POST"])
def extract_audio_from_video():
    """
    STANDALONE route: takes only an uploaded video file and pulls its
    audio track out into its own downloadable audio file.
    """
    uploaded_video = request.files.get("video_file")

    if not uploaded_video or uploaded_video.filename == "":
        return jsonify({"error": "Please choose a video file first"}), 400

    if not is_allowed_file(uploaded_video.filename, ALLOWED_VIDEO_EXT):
        return jsonify({"error": "Video file type not supported"}), 400

    job_id = str(uuid.uuid4())[:8]
    job_upload_folder = f"{UPLOAD_FOLDER}/{job_id}"
    os.makedirs(job_upload_folder, exist_ok=True)

    try:
        video_filename = secure_filename(uploaded_video.filename)
        saved_video_path = f"{job_upload_folder}/{video_filename}"
        uploaded_video.save(saved_video_path)

        audio_output_path = f"{OUTPUT_FOLDER}/video_audio_{job_id}.mp3"
        extract_audio(saved_video_path, audio_output_path)

        return jsonify({
            "success": True,
            "audio_url": f"/download/{job_id}?path={os.path.basename(audio_output_path)}"
        })

    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download/<job_id>")
def download_video(job_id):
    filename = request.args.get("path", f"video_{job_id}.mp4")
    path = f"{OUTPUT_FOLDER}/{filename}"
    if not os.path.exists(path):
        return "File not found", 404
    return send_file(path, as_attachment=True, download_name=filename)


def _open_browser():
    """Open the app in the user's default browser automatically."""
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    os.makedirs(AUDIO_FOLDER, exist_ok=True)
    os.makedirs(IMAGE_FOLDER, exist_ok=True)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    if IS_FROZEN:
        # Running as a packaged .exe: open the browser automatically,
        # and turn off Flask's debug/reloader (the reloader tries to
        # re-launch the script, which doesn't work correctly inside a
        # frozen .exe and would just relaunch the whole app in a loop).
        threading.Timer(1.2, _open_browser).start()
        app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
    else:
        # Running normally as a .py file during development: keep the
        # original debug/reloader behavior. Flask's reloader restarts
        # this script in a child process, so we only auto-open the
        # browser in that actual running child (not the parent
        # watcher process), to avoid opening two browser tabs.
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            threading.Timer(1.2, _open_browser).start()
        app.run(debug=True, port=5000)