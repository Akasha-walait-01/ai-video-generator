"""
Video Audio Merger Module
---------------------------
1. merge_video_audio()  - attach an audio file onto a video
2. get_audio_duration() - measure any audio file's length
3. extract_audio()      - pull the audio track OUT of an uploaded video
                           and save it as its own audio file
"""

from moviepy import VideoFileClip, AudioFileClip


def get_audio_duration(audio_path: str) -> float:
    """Return the duration (in seconds) of an uploaded audio file."""
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration
    audio_clip.close()
    return duration


def extract_audio(video_path: str, output_audio_path: str) -> str:
    """
    Pull the audio track out of a video file and save it as a
    standalone .mp3 file. Raises a clear error if the video has no
    audio track at all.
    """
    video_clip = VideoFileClip(video_path)

    if video_clip.audio is None:
        video_clip.close()
        raise RuntimeError("This video has no audio track to extract.")

    video_clip.audio.write_audiofile(output_audio_path)
    video_clip.close()

    return output_audio_path


def merge_video_audio(video_path: str, audio_path: str, output_path: str) -> str:
    """
    Takes a video file and an audio file, attaches the audio onto the
    video (trimming both to the shorter duration), saves the result.
    """
    video_clip = VideoFileClip(video_path)
    audio_clip = AudioFileClip(audio_path)

    final_duration = min(video_clip.duration, audio_clip.duration)

    video_clip = video_clip.subclipped(0, final_duration)
    audio_clip = audio_clip.subclipped(0, final_duration)

    final_clip = video_clip.with_audio(audio_clip)
    final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")

    video_clip.close()
    audio_clip.close()
    final_clip.close()

    return output_path


if __name__ == "__main__":
    print("This module needs a real video file and audio file to test.")
    print("Run the full pipeline via app.py to test end-to-end.")