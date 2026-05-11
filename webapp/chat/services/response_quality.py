import re

from .text_cleaning import normalize_text


def is_bad_bot_response(text: str) -> bool:
    """Catch broken, hallucinated, cut-off, or non-Turkish-script model responses."""
    normalized = normalize_text(text)
    bad_phrases = [
        "bilgi edebilirim",
        "daha fazla bilgi gerekecek",
        "kaynaklara dayanarak belirtmek icin",
        "本科",
        "프로그램",
    ]
    has_non_turkish_script = re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]", text)
    looks_cut_off = text.endswith((":", "-", "**", ",")) or text.count("**") % 2 == 1
    return bool(has_non_turkish_script or looks_cut_off or any(phrase in normalized for phrase in bad_phrases))
