from typing import Dict, List


def generate_messaging(segments: List[Dict[str, object]], brand: str, locale: str):
    locale_note = f" ({locale})" if locale else ""
    messaging = []
    for segment in segments:
        if not segment.get("confirmed"):
            continue
        name = segment.get("name", "Audience segment")
        topic = name.replace("audience", "").strip().lower() or "audience"
        messaging.append(
            {
                "segmentId": segment["segmentId"],
                "name": name,
                "headlines": [
                    f"{brand}: {topic.title()} outcomes you can trust{locale_note}",
                    f"Built for {topic} priorities",
                    f"Move faster with {brand} for {topic}",
                ],
                "tone": "Clear, evidence-backed, benefit-led",
                "ctas": [
                    "View program details",
                    "Talk to the team",
                    "Join the initiative",
                ],
            }
        )
    return messaging
