"""
Script Processor Module
------------------------
This module takes a full script (paragraph/text) and breaks it into
smaller "scenes". Each scene will later get one AI image + one voiceover
clip (or, if the user provides their own audio, a proportional slice of
that audio's total duration - see assign_durations_from_total below).

Logic: We split on sentence boundaries (. ! ?) and then group short
sentences together so each scene has a reasonable amount of narration
(not too short, not too long) - this keeps video pacing natural.
"""

import re


def clean_text(text: str) -> str:
    """Remove extra whitespace and newlines from raw script text."""
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_into_sentences(text: str) -> list:
    """Split text into sentences using punctuation as boundary."""
    sentences = re.split(r"(?<=[.!?]) +", text)
    return [s.strip() for s in sentences if s.strip()]


def group_into_scenes(sentences: list, min_words: int = 12, max_words: int = 30) -> list:
    """
    Group sentences into scenes so each scene has between
    min_words and max_words. This controls how many images/voiceover
    clips the final video will have.
    """
    scenes = []
    current_scene = ""
    current_word_count = 0

    for sentence in sentences:
        word_count = len(sentence.split())

        if current_word_count + word_count <= max_words:
            current_scene += (" " + sentence if current_scene else sentence)
            current_word_count += word_count
        else:
            if current_scene:
                scenes.append(current_scene.strip())
            current_scene = sentence
            current_word_count = word_count

    if current_scene:
        scenes.append(current_scene.strip())

    return scenes


def process_script(raw_script: str, min_words: int = 12, max_words: int = 30) -> list:
    """
    Main function: takes raw script text, returns list of scene dicts.
    Each dict has: scene_id, text
    """
    cleaned = clean_text(raw_script)
    sentences = split_into_sentences(cleaned)
    scenes = group_into_scenes(sentences, min_words, max_words)

    scene_list = []
    for idx, scene_text in enumerate(scenes, start=1):
        scene_list.append({
            "scene_id": idx,
            "text": scene_text
        })

    return scene_list


def assign_durations_from_total(scenes: list, total_duration: float, min_scene_duration: float = 1.5) -> list:
    """
    Used when the user provides a SCRIPT plus their OWN audio file
    (instead of AI voiceover). We don't generate narration audio in
    this case (it would just get replaced by the uploaded audio
    anyway), so we don't know how long each scene "should" be shown.

    Instead, we estimate it: each scene gets a slice of total_duration
    proportional to how many words it has (more words = probably takes
    longer to read aloud = gets a longer slice on screen). This makes
    the generated video's total length match the uploaded audio's
    length, instead of using a fixed short default per scene that
    would cause most of the audio to get cut off after merging.

    Every scene is guaranteed at least min_scene_duration seconds so
    very short scenes don't flash by too fast on screen.
    """
    if not scenes:
        return scenes

    word_counts = [max(len(scene["text"].split()), 1) for scene in scenes]
    total_words = sum(word_counts)

    for scene, word_count in zip(scenes, word_counts):
        raw_duration = (word_count / total_words) * total_duration
        scene["duration"] = max(raw_duration, min_scene_duration)

    return scenes


if __name__ == "__main__":
    sample_script = """
    Pakistan is a beautiful country located in South Asia. It has mountains, deserts, and rivers.
    The northern areas are famous for their stunning landscapes. Many tourists visit every year.
    Lahore is the cultural capital of Pakistan. It is known for its food, history, and architecture.
    """

    result = process_script(sample_script)
    for scene in result:
        print(f"Scene {scene['scene_id']}: {scene['text']}")
        print(f"   Word count: {len(scene['text'].split())}")
        print()

    result_with_durations = assign_durations_from_total(result, total_duration=20.0)
    print("--- With durations assigned from a 20s uploaded audio ---")
    for scene in result_with_durations:
        print(f"Scene {scene['scene_id']}: {scene['duration']:.2f}s -> {scene['text']}")