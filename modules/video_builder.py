"""
Video Builder Module
----------------------
This module takes the list of scenes (each with image_path, audio_path,
and duration) and assembles them into ONE final video with synced
voiceover, using MoviePy.

It also provides build_full_voiceover_track() - joins every scene's
individual voiceover clip into ONE single standalone audio file.

NOTE: Written for MoviePy v2.x.
"""

from moviepy import ImageClip, AudioFileClip, concatenate_videoclips, concatenate_audioclips
from moviepy.video.fx import FadeIn, FadeOut


def build_scene_clip(image_path: str, audio_path: str, duration: float, zoom: bool = True):
    """
    Build one video clip from a single scene's image + audio.
    Adds a slow zoom-in (Ken Burns effect).
    audio_path can be None for a silent scene.
    """
    image_clip = ImageClip(image_path).with_duration(duration)

    if zoom:
        image_clip = image_clip.resized(lambda t: 1 + 0.1 * (t / duration))

    if audio_path:
        audio_clip = AudioFileClip(audio_path)
        image_clip = image_clip.with_audio(audio_clip)

    image_clip = image_clip.with_effects([FadeIn(0.3), FadeOut(0.3)])

    return image_clip


def build_final_video(scenes: list, output_path: str, fps: int = 24):
    """
    Main function: stitches all scene clips into one final .mp4 video file.
    """
    clips = []
    for scene in scenes:
        clip = build_scene_clip(
            image_path=scene["image_path"],
            audio_path=scene.get("audio_path"),
            duration=scene["duration"]
        )
        clips.append(clip)

    final_video = concatenate_videoclips(clips, method="compose")
    final_video.write_videofile(output_path, fps=fps, codec="libx264", audio_codec="aac")

    return output_path


def build_full_voiceover_track(scenes: list, output_path: str) -> str:
    """
    Join every scene's individual voiceover audio clip into ONE single
    audio file, saved as a standalone .mp3, so the narration can be
    downloaded and reused separately from the video.
    """
    audio_paths = [scene["audio_path"] for scene in scenes if scene.get("audio_path")]

    if not audio_paths:
        return None

    audio_clips = [AudioFileClip(p) for p in audio_paths]
    combined = concatenate_audioclips(audio_clips)
    combined.write_audiofile(output_path)

    for clip in audio_clips:
        clip.close()
    combined.close()

    return output_path


if __name__ == "__main__":
    print("This module needs real image + audio files from previous steps.")
    print("Run the full pipeline via app.py to test end-to-end.")