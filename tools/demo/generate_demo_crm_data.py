from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "demo" / "generated"
PEOPLE_CSV = OUT_DIR / "demo_people.csv"
SUMMARY_JSON = OUT_DIR / "demo_summary.json"

FIRST_NAMES = [
    "Nino", "Giorgi", "Mariam", "Davit", "Tamar", "Luka", "Ana", "Irakli",
    "Salome", "Levan", "Ketevan", "Nikoloz", "Elene", "Sandro", "Maka", "Zurab",
]
LAST_NAMES = [
    "Demoashvili", "Civicidze", "Tbiliseli", "Kartveli", "Voiceidze", "Labidze",
    "Publicadze", "Freedomidze", "Communityadze", "Mapidze", "Surveyidze", "Consensusidze",
]
LOCATIONS = [
    ("Tbilisi, Saburtalo", "Tbilisi", "georgia_tbilisi_city", "city"),
    ("Tbilisi, Vake", "Tbilisi", "georgia_tbilisi_city", "city"),
    ("Tbilisi, Didube", "Tbilisi", "georgia_tbilisi_city", "city"),
    ("Batumi, Adjara", "Batumi", "georgia_ajara_batumi", "city"),
    ("Kutaisi, Imereti", "Kutaisi", "georgia_imereti_kutaisi", "city"),
    ("Telavi, Kakheti", "Telavi", "georgia_kakheti_telavi", "city"),
    ("Gori, Shida Kartli", "Gori", "georgia_shida_kartli_gori", "city"),
    ("Rustavi, Kvemo Kartli", "Rustavi", "georgia_kvemo_kartli_rustavi", "city"),
    ("Georgia", "Georgia unspecified", "georgia_general", "country"),
]
PROFESSIONS = [
    "Teacher", "Journalist", "Designer", "Doctor", "Student", "Lawyer", "Engineer",
    "Small business owner", "Researcher", "Community organizer", "Translator", "Artist",
]
TIME_AVAILABILITY = [
    "Working hours", "After hours", "Weekends", "Flexible/unspecified",
]
SKILLS = [
    "Public meetings", "Online campaigning", "Translation", "Design", "Research",
    "Event organizing", "Social media", "Fact-checking", "Volunteer coordination",
]


def build_people(count: int = 160) -> list[dict]:
    rows = []
    today = date(2026, 6, 24)
    for index in range(1, count + 1):
        first = FIRST_NAMES[index % len(FIRST_NAMES)]
        last = LAST_NAMES[(index * 3) % len(LAST_NAMES)]
        group = "Member" if index % 9 == 0 else "Supporter"
        location = LOCATIONS[index % len(LOCATIONS)]
        age = 20 + (index * 7) % 48
        gender = "Female" if index % 3 == 0 else "Male"
        skill_a = SKILLS[index % len(SKILLS)]
        skill_b = SKILLS[(index + 4) % len(SKILLS)]
        row = {
            "source": "demo",
            "sourceRow": index,
            "personId": f"demo-person-{index:04d}",
            "idType": "demo",
            "email": f"demo.person.{index:04d}@civicvoicelab.demo",
            "rawEmail": f"demo.person.{index:04d}@civicvoicelab.demo",
            "firstName": first,
            "lastName": last,
            "fullName": f"{first} {last}",
            "phone": f"+995555{index:06d}"[-13:],
            "dateOfBirth": str(today.replace(year=today.year - age)),
            "age": age,
            "gender": gender,
            "supporterType": group,
            "address": location[0],
            "neighborhood": location[1],
            "neighborhoodId": location[2],
            "locationPrecision": location[3],
            "locationConfidence": 0.3 if location[3] == "country" else 0.86,
            "locationReviewNeeded": "False",
            "suggestedLocationMatch": "",
            "profession": PROFESSIONS[index % len(PROFESSIONS)],
            "timeAvailability": TIME_AVAILABILITY[index % len(TIME_AVAILABILITY)],
            "skills": f"{skill_a}, {skill_b}",
            "agreesWithManifesto": "True" if index % 5 != 0 else "False",
            "interestedInMembership": "True" if group == "Member" or index % 4 == 0 else "False",
            "createdAt": str(today - timedelta(days=index % 120)),
            "updatedAt": str(today - timedelta(days=index % 14)),
        }
        rows.append(row)
    return rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    people = build_people()
    with PEOPLE_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(people[0].keys()))
        writer.writeheader()
        writer.writerows(people)
    summary = {
        "people": len(people),
        "supporters": sum(1 for row in people if row["supporterType"] == "Supporter"),
        "members": sum(1 for row in people if row["supporterType"] == "Member"),
        "locations": sorted({row["neighborhood"] for row in people}),
        "output": str(PEOPLE_CSV.relative_to(ROOT)),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
