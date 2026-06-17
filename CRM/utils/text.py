import pandas as pd


def clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def split_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = str(value).split(",")
    cleaned = []
    for item in items:
        text = clean_text(item)
        if text:
            cleaned.append(text)
    return cleaned


def normalize_str_list(values):
    cleaned = []
    for value in values or []:
        text = clean_text(value)
        if text:
            cleaned.append(text)
    return sorted(set(cleaned))


def format_list_label(values, limit=6):
    items = [str(v).strip() for v in values or [] if str(v).strip()]
    items = sorted(set(items))
    if not items:
        return "None"
    if len(items) > limit:
        return ", ".join(items[:limit]) + f" (+{len(items) - limit} more)"
    return ", ".join(items)


def normalize_supporter_type(value, default_type="Supporter"):
    text = clean_text(value)
    if not text:
        return default_type
    if "member" in text.lower():
        return "Member"
    return "Supporter"


def _normalize_column(name):
    return (
        str(name)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "")
    )


def _get_column(df, candidates):
    normalized = {_normalize_column(col): col for col in df.columns}
    for cand in candidates:
        key = _normalize_column(cand)
        if key in normalized:
            return normalized[key]
    return None


def build_import_rows(df, default_type):
    if df.empty:
        return []
    col_email = _get_column(df, ["email", "primary_email", "e_mail", "e-mail", "email_address"])
    col_email_secondary = _get_column(
        df, ["secondary_email", "alternate_email", "alt_email"]
    )
    if not col_email:
        return []
    col_first = _get_column(df, ["first_name", "firstname", "first"])
    col_last = _get_column(df, ["last_name", "lastname", "last"])
    col_gender = _get_column(df, ["gender", "sex"])
    col_age = _get_column(df, ["age"])
    col_phone = _get_column(df, ["phone", "primary_phone", "mobile"])
    col_phone_secondary = _get_column(df, ["secondary_phone", "alt_phone"])
    col_address = _get_column(df, ["address", "fulladdress", "full_address"])
    col_lat = _get_column(df, ["lat", "latitude"])
    col_lon = _get_column(df, ["lon", "lng", "longitude"])
    col_type = _get_column(df, ["supporter_type", "type", "group"])
    col_effort = _get_column(df, ["effort_hours", "volunteer_hours", "hours", "time_spent"])
    col_events = _get_column(
        df,
        ["events_attended", "events_attended_count", "event_attended", "event_attend_count"],
    )
    col_refs = _get_column(df, ["referral_count", "references", "referrals", "recruits"])
    col_education = _get_column(df, ["education", "education_level"])
    col_skills = _get_column(df, ["skills", "skill_list", "skill"])

    rows = []
    for _, row in df.iterrows():
        email = clean_text(row.get(col_email))
        if not email and col_email_secondary:
            email = clean_text(row.get(col_email_secondary))
        if not email:
            continue
        age_val = pd.to_numeric(row.get(col_age), errors="coerce") if col_age else None
        age = (
            int(age_val)
            if age_val is not None and not pd.isna(age_val) and age_val > 0
            else None
        )
        lat_val = pd.to_numeric(row.get(col_lat), errors="coerce") if col_lat else None
        lon_val = pd.to_numeric(row.get(col_lon), errors="coerce") if col_lon else None
        lat = float(lat_val) if lat_val is not None and not pd.isna(lat_val) else None
        lon = float(lon_val) if lon_val is not None and not pd.isna(lon_val) else None
        supporter_type = clean_text(row.get(col_type)) if col_type else None
        effort_val = pd.to_numeric(row.get(col_effort), errors="coerce") if col_effort else None
        effort_hours = (
            float(effort_val) if effort_val is not None and not pd.isna(effort_val) else None
        )
        events_val = pd.to_numeric(row.get(col_events), errors="coerce") if col_events else None
        events_attended = (
            int(events_val) if events_val is not None and not pd.isna(events_val) else None
        )
        refs_val = pd.to_numeric(row.get(col_refs), errors="coerce") if col_refs else None
        referrals = (
            int(refs_val) if refs_val is not None and not pd.isna(refs_val) else None
        )
        education = clean_text(row.get(col_education)) if col_education else None
        skills = split_list(row.get(col_skills)) if col_skills else []
        rows.append(
            {
                "email": email,
                "firstName": clean_text(row.get(col_first)) if col_first else None,
                "lastName": clean_text(row.get(col_last)) if col_last else None,
                "gender": clean_text(row.get(col_gender)) if col_gender else None,
                "age": age,
                "phone": clean_text(row.get(col_phone))
                if col_phone
                else (clean_text(row.get(col_phone_secondary)) if col_phone_secondary else None),
                "address": clean_text(row.get(col_address)) if col_address else None,
                "lat": lat,
                "lon": lon,
                "effortHours": effort_hours,
                "eventsAttendedCount": events_attended,
                "referralCount": referrals,
                "education": education,
                "skills": skills,
                "supporterType": normalize_supporter_type(supporter_type, default_type),
            }
        )
    return rows
