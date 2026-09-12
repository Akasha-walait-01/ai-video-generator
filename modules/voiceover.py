"""
Voiceover Module
-----------------
This module converts each scene's text into a voiceover audio file.

It tries edge-tts FIRST (better quality, more natural voices).
If edge-tts fails (Microsoft sometimes blocks/breaks it), it
automatically falls back to gTTS (Google Text-to-Speech), which
is more stable but slightly more robotic sounding.

AUTO-TRANSLATION SAFEGUARD:
If the script's language doesn't match the chosen voice's language,
the text is automatically translated into the target language that
matches the chosen voice. The ORIGINAL text is still used for image
generation (translation only affects what gets spoken).

Available edge-tts voices:
- en-US-AriaNeural      (English Female)
- en-US-GuyNeural       (English Male)
- en-GB-SoniaNeural     (English Female, UK)
- ur-PK-UzmaNeural      (Urdu Female)
- ur-PK-AsadNeural      (Urdu Male)
"""

import edge_tts
import asyncio
from mutagen.mp3 import MP3
from gtts import gTTS
from deep_translator import GoogleTranslator


def get_target_language(voice: str) -> str:
    """
    Figure out which language the chosen voice speaks, so we know
    what language to translate the script into.
    Supports English, Urdu, Hindi, and Arabic voices.
    """
    if voice.startswith("ur-PK"):
        return "ur"
    if voice.startswith("hi-IN"):
        return "hi"
    if voice.startswith("ar-SA"):
        return "ar"
    return "en"


def translate_text(text: str, target_lang: str) -> str:
    """
    Translate text into target_lang using Google Translate (via
    deep-translator, no API key needed). Falls back to original text
    if translation fails for any reason.
    """
    try:
        translated = GoogleTranslator(source="auto", target=target_lang).translate(text)
        return translated if translated else text
    except Exception as e:
        print(f"Translation failed ({e}), using original text instead")
        return text


async def generate_voiceover_async(text: str, output_path: str, voice: str = "en-US-AriaNeural"):
    """Generate voiceover using edge-tts (async, needs internet)."""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def generate_with_edge_tts(text: str, output_path: str, voice: str = "en-US-AriaNeural"):
    """Try to generate voiceover using edge-tts."""
    asyncio.run(generate_voiceover_async(text, output_path, voice))


def generate_with_gtts(text: str, output_path: str, lang: str = "en"):
    """Fallback voiceover generator using gTTS."""
    tts = gTTS(text=text, lang=lang)
    tts.save(output_path)


def generate_voiceover(text: str, output_path: str, voice: str = "en-US-AriaNeural"):
    """
    Main function used by the rest of the app.
    Tries edge-tts first. If it fails for ANY reason
    (network issue, 403 error, service down), it automatically
    switches to gTTS so the project keeps working.

    IMPORTANT LIMITATION: gTTS does NOT support choosing a male vs
    female voice - it only has one generic voice per language. So if
    edge-tts keeps failing and every scene falls back to gTTS, every
    English voice option will sound identical (and every Urdu voice
    option will sound identical to each other), even though a
    different voice was selected. If you notice all your voices
    sounding the same, check the terminal output for
    "edge-tts failed" messages - that means gTTS is being used instead,
    and the fix is to make edge-tts work reliably (update it to the
    latest version, check your firewall/antivirus isn't blocking the
    wss://speech.platform.bing.com connection).
    """
    try:
        generate_with_edge_tts(text, output_path, voice)
    except Exception as e:
        print(f"edge-tts failed ({e})")
        print("Switching to gTTS backup - NOTE: gTTS cannot do male/female voices, "
              "so this scene will sound generic regardless of which voice was selected.")
        lang = get_target_language(voice)
        generate_with_gtts(text, output_path, lang)


def get_audio_duration(audio_path: str) -> float:
    """Return duration (in seconds) of an mp3 file."""
    audio = MP3(audio_path)
    return audio.info.length


def generate_all_voiceovers(scenes: list, output_folder: str, voice: str = "en-US-AriaNeural") -> list:
    """
    Main function: generates a voiceover mp3 for each scene, translating
    the text first if needed to match the chosen voice's language.
    """
    target_lang = get_target_language(voice)

    for scene in scenes:
        scene_id = scene["scene_id"]
        original_text = scene["text"]

        voiceover_text = translate_text(original_text, target_lang)

        audio_path = f"{output_folder}/scene_{scene_id}.mp3"
        generate_voiceover(voiceover_text, audio_path, voice)

        duration = get_audio_duration(audio_path)

        scene["audio_path"] = audio_path
        scene["duration"] = duration
        scene["voiceover_text"] = voiceover_text

    return scenes


if __name__ == "__main__":
    import os
    os.makedirs("../static/audio", exist_ok=True)

    test_scenes = [
        {"scene_id": 1, "text": "Pakistan is a beautiful country located in South Asia."},
        {"scene_id": 2, "text": "Lahore is the cultural capital of Pakistan."}
    ]

    result = generate_all_voiceovers(test_scenes, "../static/audio", voice="ur-PK-UzmaNeural")
    for scene in result:
        print(f"Scene {scene['scene_id']}")
        print(f"   Original text: {scene['text']}")
        print(f"   Spoken (translated) text: {scene['voiceover_text']}")
        print(f"   Audio: {scene['audio_path']} | Duration: {scene['duration']:.2f}s")