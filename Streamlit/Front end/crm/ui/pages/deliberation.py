import altair as alt
import html
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import textwrap
from uuid import uuid4
from urllib.parse import quote

try:
    import matplotlib.pyplot as plt
    from matplotlib_venn import venn2, venn3
except Exception:
    plt = None
    venn2 = None
    venn3 = None

try:
    from crm.ui.components.swipecards_loader import load_streamlit_swipecards
    streamlit_swipecards = load_streamlit_swipecards()
except Exception:
    streamlit_swipecards = None

from crm.clients.deliberation import (
    delib_api_get,
    delib_api_patch,
    delib_api_post,
    render_delib_api_unavailable,
)
from crm.ui.components.questionnaire import render_questionnaire_block

MOBILE_QUESTIONNAIRE_CARD_LIMIT = 5
MOBILE_QUESTIONNAIRE_USE_THIRD_PARTY_SWIPE = True


def _safe_int(value):
    try:
        return int(value)
    except Exception:
        return 0


def _guess_column(columns, candidates):
    normalized_candidates = {str(c).strip().lower() for c in candidates}
    for col in columns:
        col_name = str(col).strip().lower()
        if col_name in normalized_candidates:
            return col
    for col in columns:
        col_name = str(col).strip().lower().replace(" ", "_")
        if col_name in normalized_candidates:
            return col
    return ""


def _clean_vote_csv_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        as_int = int(value)
        if float(value) == float(as_int):
            return as_int
    cleaned = str(value).strip()
    return cleaned or None


def _clean_optional_text_csv_value(value):
    if pd.isna(value):
        return None
    cleaned = str(value).strip()
    if not cleaned or cleaned.lower() in {"nan", "none", "null"}:
        return None
    return cleaned


def _clean_optional_bool_csv_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        as_int = int(value)
        if float(value) == float(as_int):
            if as_int == 1:
                return True
            if as_int == 0:
                return False
        return None
    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y", "1"}:
        return True
    if text in {"false", "f", "no", "n", "0"}:
        return False
    return None


def _clean_id_csv_value(value):
    if pd.isna(value):
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        as_int = int(value)
        if float(value) == float(as_int):
            return str(as_int)
    return str(value).strip()


def _resolve_card_typography(text):
    char_count = len(" ".join(str(text or "").split()))
    if char_count <= 85:
        return {"font_size": 52, "line_height": 62, "max_chars": 24, "max_lines": 6}
    if char_count <= 150:
        return {"font_size": 44, "line_height": 56, "max_chars": 28, "max_lines": 7}
    if char_count <= 230:
        return {"font_size": 38, "line_height": 50, "max_chars": 32, "max_lines": 9}
    return {"font_size": 32, "line_height": 44, "max_chars": 36, "max_lines": 10}


def _wrap_card_text(text, max_chars, max_lines):
    raw = " ".join(str(text or "").split())
    if not raw:
        return ["No statement text provided."]
    lines = textwrap.wrap(raw, width=max_chars, break_long_words=False, break_on_hyphens=False)
    if not lines:
        return ["No statement text provided."]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        lines[-1] = (last[:-1] + "…") if len(last) > 1 else "…"
    return lines


def _build_swipe_card_image(comment, idx, total, compact=False):
    card_text = comment.get("text", "")
    typography = _resolve_card_typography(card_text)
    question_lines = _wrap_card_text(
        card_text,
        max_chars=typography["max_chars"],
        max_lines=typography["max_lines"],
    )
    font_size = typography["font_size"]
    line_height = typography["line_height"]

    title = html.escape(f"Question {idx + 1} / {total}")
    subtitle = html.escape("AGREE · SWIPE RIGHT   •   DISAGREE · SWIPE LEFT   •   PASS · SWIPE DOWN")
    footer = (
        "Reactions: "
        f"👍 {_safe_int(comment.get('agree_count', 0))}   "
        f"👎 {_safe_int(comment.get('disagree_count', 0))}   "
        f"➖ {_safe_int(comment.get('pass_count', 0))}"
    )
    footer_text = html.escape(footer)

    panel_y = 150 if compact else 165
    panel_h = 510 if compact else 420
    text_block_h = ((len(question_lines) - 1) * line_height) + font_size
    start_y = int(panel_y + max(74, (panel_h - text_block_h) / 2) + (font_size * 0.82))
    line_elements = []
    for i, line in enumerate(question_lines):
        y = start_y + (i * line_height)
        line_elements.append(
            f"<text x='80' y='{y}' font-size='{font_size}' font-weight='700' "
            f"fill='#123F5E'>{html.escape(line)}</text>"
        )
    lines_svg = "".join(line_elements)
    subtitle_svg = (
        f"<text x='54' y='124' font-size='18' fill='#3A6786'>{subtitle}</text>"
        if compact
        else f"<text x='54' y='130' font-size='20' fill='#3A6786'>{subtitle}</text>"
    )
    footer_svg = (
        "<rect x='32' y='598' width='656' height='92' rx='24' fill='url(#footerGrad)'/>"
        "<line x1='360' y1='612' x2='360' y2='678' stroke='#9FC5E2' stroke-width='2'/>"
        "<text x='56' y='632' font-size='20' font-weight='700' fill='#123F5E'>DISAGREE · SWIPE LEFT</text>"
        "<text x='392' y='632' font-size='20' font-weight='700' fill='#123F5E'>AGREE · SWIPE RIGHT</text>"
        "<text x='56' y='666' font-size='16' fill='#3A6786'>PASS · SWIPE DOWN</text>"
        f"<text x='340' y='666' font-size='14' fill='#3A6786'>{footer_text}</text>"
        if not compact
        else ""
    )

    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 720 720'>"
        "<defs>"
        "<linearGradient id='bgGrad' x1='0%' y1='0%' x2='100%' y2='100%'>"
        "<stop offset='0%' stop-color='#EAF6FF'/>"
        "<stop offset='55%' stop-color='#D4EBFF'/>"
        "<stop offset='100%' stop-color='#C1E2FF'/>"
        "</linearGradient>"
        "<linearGradient id='headerGrad' x1='0%' y1='0%' x2='100%' y2='0%'>"
        "<stop offset='0%' stop-color='#DDF0FF'/>"
        "<stop offset='100%' stop-color='#C6E5FF'/>"
        "</linearGradient>"
        "<linearGradient id='questionGrad' x1='0%' y1='0%' x2='0%' y2='100%'>"
        "<stop offset='0%' stop-color='#F6FBFF'/>"
        "<stop offset='100%' stop-color='#EAF4FF'/>"
        "</linearGradient>"
        "<linearGradient id='footerGrad' x1='0%' y1='0%' x2='100%' y2='100%'>"
        "<stop offset='0%' stop-color='#D9EEFF'/>"
        "<stop offset='100%' stop-color='#C3E2FF'/>"
        "</linearGradient>"
        "</defs>"
        "<rect width='720' height='720' rx='38' fill='url(#bgGrad)'/>"
        "<circle cx='640' cy='90' r='98' fill='#F4FAFF' opacity='0.45'/>"
        "<circle cx='86' cy='658' r='120' fill='#F4FAFF' opacity='0.4'/>"
        "<rect x='20' y='20' width='680' height='680' rx='34' fill='#F4FAFF' opacity='0.5'/>"
        "<rect x='32' y='32' width='656' height='104' rx='22' fill='url(#headerGrad)'/>"
        f"<text x='54' y='98' font-size='32' font-weight='700' fill='#123F5E'>{title}</text>"
        f"{subtitle_svg}"
        f"<rect x='32' y='{panel_y}' width='656' height='{panel_h}' rx='34' fill='url(#questionGrad)' stroke='#B7D7EF' stroke-width='3'/>"
        f"{lines_svg}"
        f"{footer_svg}"
        "</svg>"
    )
    return "data:image/svg+xml;utf8," + quote(svg)


def _apply_questionnaire_card_only_layout():
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"],
        [data-testid="stSidebar"],
        [data-testid="stSidebarContent"],
        [data-testid="stSidebarHeader"],
        [data-testid="stSidebarNav"],
        [data-testid="stSidebarNavItems"],
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stBaseButton-headerNoPadding"],
        button[kind="headerNoPadding"],
        button[title="View sidebar"],
        button[title="Close sidebar"],
        [data-testid="collapsedControl"],
        aside,
        nav {
          display: none !important;
          visibility: hidden !important;
          width: 0 !important;
          min-width: 0 !important;
          max-width: 0 !important;
        }
        [data-testid="stAppViewContainer"] > .main {
          margin-left: 0 !important;
        }
        [data-testid="stAppViewContainer"] {
          background: linear-gradient(145deg, #EAF6FF 0%, #D4EBFF 52%, #C1E2FF 100%) !important;
        }
        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        #MainMenu,
        footer {
          display: none !important;
        }
        .block-container {
          padding-top: 0.4rem !important;
          padding-bottom: 0.4rem !important;
          padding-left: 0.3rem !important;
          padding-right: 0.3rem !important;
          max-width: 100% !important;
        }
        [data-testid="stVerticalBlock"] > div {
          background: transparent !important;
        }
        [data-testid="stExpander"] details {
          background: #EAF4FF !important;
          border: 1px solid #B7D7EF !important;
          border-radius: 14px !important;
        }
        [data-testid="stExpander"] details > summary {
          background: #F6FBFF !important;
          color: #123F5E !important;
          border-radius: 14px !important;
          padding: 0.4rem 0.7rem !important;
        }
        [data-testid="stExpander"] details > div {
          background: #EAF4FF !important;
          border-radius: 0 0 14px 14px !important;
          padding: 0.45rem 0.6rem 0.7rem 0.6rem !important;
        }
        [data-testid="stExpander"] details * {
          color: #123F5E !important;
        }
        [data-testid="stForm"] {
          background: #EAF4FF !important;
          border: 1px solid #B7D7EF !important;
          border-radius: 14px !important;
          padding: 0.6rem !important;
        }
        .fs-questionnaire-note {
          background: #EAF4FF;
          border: 1px solid #B7D7EF;
          border-radius: 12px;
          padding: 0.5rem 0.7rem;
          margin: 0.35rem 0 0.55rem 0;
          color: #123F5E;
        }
        .fs-questionnaire-note h4 {
          margin: 0;
          font-size: 1.02rem;
          color: #123F5E;
        }
        .fs-questionnaire-note p {
          margin: 0.2rem 0 0 0;
          color: #3A6786;
          font-size: 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _inject_questionnaire_parent_hide_script() -> None:
    components.html(
        """
        <script>
        (function () {
          function hideNav(doc) {
            const selectors = [
              'aside',
              'nav',
              '[data-testid="stSidebar"]',
              '[data-testid="stSidebarNav"]',
              '[data-testid="stSidebarNavItems"]',
              '[data-testid="stSidebarNavLink"]',
              '[data-testid="stPageLink"]',
              '[data-testid="collapsedControl"]',
              '[data-testid="stSidebarCollapsedControl"]',
              '[data-testid="stToolbar"]',
              'header[data-testid="stHeader"]',
              '#MainMenu',
              'footer'
            ];
            selectors.forEach((sel) => {
              doc.querySelectorAll(sel).forEach((el) => {
                el.style.display = 'none';
                el.style.visibility = 'hidden';
                el.style.width = '0px';
                el.style.maxWidth = '0px';
                el.style.minWidth = '0px';
              });
            });
          }

          function apply() {
            try {
              const parentDoc = window.parent && window.parent.document ? window.parent.document : document;
              hideNav(parentDoc);
              const main = parentDoc.querySelector('[data-testid="stAppViewContainer"] > .main');
              if (main) {
                main.style.marginLeft = '0px';
              }
            } catch (e) {
              hideNav(document);
            }
          }

          apply();
          let runs = 0;
          const timer = setInterval(() => {
            apply();
            runs += 1;
            if (runs > 60) clearInterval(timer);
          }, 250);
        })();
        </script>
        """,
        height=0,
    )


def _is_questionnaire_participation_mode():
    questionnaire = str(_get_query_param("questionnaire") or "").strip().lower()
    if questionnaire in {"deliberation", "deliberation_admin"}:
        return True
    if questionnaire:
        return False
    convo_id = str(
        _get_query_param("conversation_id")
        or _get_query_param("conversation")
        or st.session_state.get("delib_conversation_id")
        or ""
    ).strip()
    if not convo_id:
        return False
    mobile = str(_get_query_param("mobile") or "").strip().lower()
    if mobile in {"1", "true", "yes", "on"}:
        return True
    view = str(_get_query_param("view") or "").strip().lower()
    return view == "mobile"


def _get_query_param(name):
    value = None
    try:
        value = st.query_params.get(name)
    except Exception:
        value = None
    if isinstance(value, list):
        return value[0] if value else None
    if value not in (None, ""):
        return value
    try:
        params = st.experimental_get_query_params()
        fallback = params.get(name)
        if isinstance(fallback, list):
            return fallback[0] if fallback else None
        return fallback
    except Exception:
        return value
    return value


def _resolve_participant_id(conversation_id: str, *, questionnaire_mode: bool, sid: str = "") -> str:
    explicit_id = str(_get_query_param("participant_id") or "").strip()
    if explicit_id:
        return explicit_id
    normalized_convo_id = str(conversation_id or "").strip()
    normalized_sid = str(sid or "").strip()
    if questionnaire_mode and normalized_convo_id:
        state_key = f"delib_anon_id_{normalized_convo_id}_{normalized_sid or 'default'}"
    else:
        state_key = "delib_anon_id"
    participant_id = str(st.session_state.get(state_key) or "").strip()
    if not participant_id:
        participant_id = str(uuid4())
        st.session_state[state_key] = participant_id
    return participant_id


def _ensure_questionnaire_query_defaults(conversation_id: str) -> None:
    current_kind = str(_get_query_param("questionnaire") or "").strip().lower()
    if current_kind not in {"deliberation", "deliberation_admin"}:
        current_kind = "deliberation"
    canonical = {
        "questionnaire": current_kind,
        "conversation_id": str(conversation_id or "").strip(),
        "mobile": "1",
        "view": "mobile",
        "embed": "true",
    }
    if not canonical["conversation_id"]:
        return
    changed = False
    try:
        query_params = st.query_params
        for key, expected in canonical.items():
            current = query_params.get(key)
            if isinstance(current, list):
                current = current[0] if current else ""
            if str(current or "").strip() != expected:
                query_params[key] = expected
                changed = True
    except Exception:
        return
    if changed:
        st.rerun()


def _cast_swipe_vote(convo_id, comment_id, choice, headers):
    result = delib_api_post(
        "/vote",
        {
            "conversation_id": convo_id,
            "comment_id": comment_id,
            "choice": choice,
        },
        headers=headers,
    )
    return result is not None


def _render_swipe_component(
    comments,
    convo_id,
    headers,
    compact=False,
    participant_scope="",
):
    if streamlit_swipecards is None:
        if compact:
            st.warning("Swipe cards are unavailable in this environment. Using button cards.")
            _render_mobile_questionnaire_cards(
                comments,
                convo_id,
                headers,
                participant_scope=participant_scope,
            )
            return {"current_comment_id": None, "total_swiped": 0, "deck_ok": True}
        st.warning(
            "Swipe component is unavailable in this environment. "
            "Use classic mode below."
        )
        _render_classic_vote_list(comments, convo_id, headers)
        return {"current_comment_id": None, "total_swiped": 0, "deck_ok": True}

    mode_suffix = "compact" if compact else "full"
    scope_token = str(participant_scope or "anon").strip() or "anon"
    casted_key = f"delib_swipe_casted_ids_{convo_id}_{mode_suffix}_{scope_token}"
    reset_nonce_key = f"delib_swipe_nonce_{convo_id}_{mode_suffix}_{scope_token}"
    nonce = int(st.session_state.get(reset_nonce_key, 0) or 0)

    cards = []
    for idx, comment in enumerate(comments):
        cards.append(
            {
                "name": " " if compact else f"Question {idx + 1}/{len(comments)}",
                "description": " ",
                "image": _build_swipe_card_image(
                    comment, idx, len(comments), compact=compact
                ),
            }
        )

    result = streamlit_swipecards(
        cards=cards,
        display_mode="cards",
        view="mobile",
        show_border=False,
        last_card_message="You have reviewed all statements.",
        colors={
            "like_bg": "#EAF4FF",
            "like_fg": "#123F5E",
            "pass_bg": "#EAF4FF",
            "pass_fg": "#123F5E",
            "back_bg": "#EAF4FF",
            "back_fg": "#123F5E",
            "btn_border": "#B7D7EF",
            "card_bg": "#EAF4FF",
            "background_color": "#F1F8FF",
            "text_color": "#123F5E",
        },
        key=f"delib_swipe_component_{convo_id}_{mode_suffix}_{scope_token}_{nonce}",
    )

    casted_ids = set(st.session_state.get(casted_key, []))
    swiped_cards = (
        result.get("swipedCards", [])
        if isinstance(result, dict)
        else []
    )
    stale_key = f"delib_swipe_stale_fix_{convo_id}_{mode_suffix}_{scope_token}"
    stale_runs = int(st.session_state.get(stale_key, 0) or 0)
    # Recover from stale component payloads that can arrive pre-filled on first render.
    if comments and len(swiped_cards) >= len(comments) and len(casted_ids) < len(comments):
        if stale_runs < 1:
            st.session_state[stale_key] = stale_runs + 1
            st.session_state[reset_nonce_key] = nonce + 1
            st.rerun()
        return {"current_comment_id": None, "total_swiped": len(casted_ids), "deck_ok": False}
    st.session_state[stale_key] = 0
    total_swiped = len(swiped_cards)
    current_comment_id = None
    if comments and total_swiped < len(comments):
        active_comment = comments[total_swiped]
        if isinstance(active_comment, dict):
            current_comment_id = active_comment.get("id")

    if not compact:
        st.progress((total_swiped / len(comments)) if comments else 0.0)
        hint_cols = st.columns(3)
        hint_cols[0].markdown("**AGREE**  \nSWIPE RIGHT")
        hint_cols[1].markdown("**DISAGREE**  \nSWIPE LEFT")
        hint_cols[2].markdown("**PASS**  \nSWIPE DOWN")
        st.caption("Each card shows one question/comment only.")
        st.caption(f"{total_swiped}/{len(comments)} reactions recorded")

    new_votes_cast = False
    for action_item in swiped_cards:
        idx = action_item.get("index")
        action = action_item.get("action")
        if not isinstance(idx, int) or idx < 0 or idx >= len(comments):
            continue
        if action == "right":
            choice = 1
        elif action == "left":
            choice = -1
        elif action == "down":
            choice = 0
        else:
            continue
        comment_id = str(comments[idx].get("id") or "").strip()
        if not comment_id or comment_id in casted_ids:
            continue
        if _cast_swipe_vote(convo_id, comment_id, choice, headers):
            casted_ids.add(comment_id)
            new_votes_cast = True
    if new_votes_cast:
        st.session_state[casted_key] = sorted(casted_ids)

    if not compact and st.button(
        "Reset swipe progress",
        key=f"delib_swipe_reset_{convo_id}_{scope_token}",
        help="Reset local swipe progress for this conversation.",
    ):
        st.session_state[casted_key] = []
        st.session_state[reset_nonce_key] = nonce + 1
        st.rerun()

    return {"current_comment_id": current_comment_id, "total_swiped": total_swiped, "deck_ok": True}


def _render_mobile_questionnaire_cards(comments, convo_id, headers, participant_scope=""):
    mode_suffix = "compact"
    scope_token = str(participant_scope or "anon").strip() or "anon"
    casted_key = f"delib_swipe_casted_ids_{convo_id}_{mode_suffix}_{scope_token}"
    casted_ids = set(st.session_state.get(casted_key, []))
    total_comments = len(comments)
    remaining_comments = []
    for comment in comments:
        comment_id = str(comment.get("id") or "").strip()
        if comment_id and comment_id not in casted_ids:
            remaining_comments.append(comment)

    reviewed_count = total_comments - len(remaining_comments)
    st.progress((reviewed_count / total_comments) if total_comments else 0.0)
    st.caption(f"{reviewed_count}/{total_comments} reactions recorded")
    st.caption("Use actions below: AGREE (right), DISAGREE (left), PASS (down).")

    if not remaining_comments:
        st.success("You have reviewed all statements.")
        if st.button("Restart cards", key=f"delib_mobile_restart_{convo_id}_{scope_token}"):
            st.session_state[casted_key] = []
            st.rerun()
        return

    current_comment = remaining_comments[0]
    current_id = str(current_comment.get("id") or "").strip()
    card_image = _build_swipe_card_image(
        current_comment,
        idx=reviewed_count,
        total=total_comments,
        compact=True,
    )
    st.image(card_image, use_container_width=True)

    action_cols = st.columns(3)
    agree = action_cols[0].button(
        "AGREE\nSWIPE RIGHT",
        key=f"delib_mobile_agree_{convo_id}_{current_id}",
        use_container_width=True,
    )
    disagree = action_cols[1].button(
        "DISAGREE\nSWIPE LEFT",
        key=f"delib_mobile_disagree_{convo_id}_{current_id}",
        use_container_width=True,
    )
    passed = action_cols[2].button(
        "PASS\nSWIPE DOWN",
        key=f"delib_mobile_pass_{convo_id}_{current_id}",
        use_container_width=True,
    )

    choice = None
    if agree:
        choice = 1
    elif disagree:
        choice = -1
    elif passed:
        choice = 0
    if choice is None:
        return
    if _cast_swipe_vote(convo_id, current_id, choice, headers):
        casted_ids.add(current_id)
        st.session_state[casted_key] = sorted(casted_ids)
        st.rerun()


def _render_classic_vote_list(comments, convo_id, headers):
    for comment in comments:
        st.markdown(f"**{comment['text']}**")
        counts = (
            f"👍 {comment['agree_count']}  "
            f"👎 {comment['disagree_count']}  "
            f"➖ {comment['pass_count']}"
        )
        st.caption(counts)
        cols = st.columns(3)
        if cols[0].button(
            "Agree",
            key=f"delib-{comment['id']}-agree",
            help="Vote Agree on this comment.",
        ):
            delib_api_post(
                "/vote",
                {
                    "conversation_id": convo_id,
                    "comment_id": comment["id"],
                    "choice": 1,
                },
                headers=headers,
            )
        if cols[1].button(
            "Disagree",
            key=f"delib-{comment['id']}-disagree",
            help="Vote Disagree on this comment.",
        ):
            delib_api_post(
                "/vote",
                {
                    "conversation_id": convo_id,
                    "comment_id": comment["id"],
                    "choice": -1,
                },
                headers=headers,
            )
        if cols[2].button(
            "Pass",
            key=f"delib-{comment['id']}-pass",
            help="Skip/Pass on this comment (neutral / no vote).",
        ):
            delib_api_post(
                "/vote",
                {
                    "conversation_id": convo_id,
                    "comment_id": comment["id"],
                    "choice": 0,
                },
                headers=headers,
            )
        st.divider()


def _render_questionnaire_comment_form(convo_id, headers):
    st.markdown(
        """
        <div class="fs-questionnaire-note">
          <h4>Add comment</h4>
          <p>No registration required.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form(f"delib_questionnaire_comment_form_{convo_id}", clear_on_submit=True):
        new_comment = st.text_area(
            "Your comment",
            key=f"delib_questionnaire_comment_text_{convo_id}",
            height=90,
            placeholder="Share your view...",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Submit anonymous comment")
    if submitted:
        text = (new_comment or "").strip()
        if not text:
            st.warning("Comment cannot be empty.")
        elif len(text) < 2:
            st.warning("Comment should be at least 2 characters.")
        else:
            result = delib_api_post(
                f"/conversations/{convo_id}/comments",
                {"text": text},
                headers=headers,
            )
            if result:
                status = str(result.get("status", "")).lower()
                notice_key = f"delib_questionnaire_comment_notice_{convo_id}"
                focus_key = f"delib_questionnaire_focus_comment_{convo_id}"
                if status == "pending":
                    st.session_state[notice_key] = "pending"
                else:
                    st.session_state[notice_key] = "approved"
                    created_comment_id = str(result.get("id") or "").strip()
                    if created_comment_id:
                        st.session_state[focus_key] = created_comment_id
                st.rerun()


def _render_questionnaire_like_dislike_buttons(
    comments,
    convo_id,
    headers,
    focus_comment_id=None,
):
    anon_comments = [c for c in comments if not bool(c.get("is_seed", False))]
    if not anon_comments:
        st.info("No anonymous participant comments yet.")
        return

    if focus_comment_id:
        focused = [c for c in anon_comments if c.get("id") == focus_comment_id]
        if focused:
            anon_comments = focused

    max_items = 1 if focus_comment_id else min(len(anon_comments), 20)
    for comment in anon_comments[:max_items]:
        comment_id = comment.get("id")
        text = str(comment.get("text") or "").strip()
        if not comment_id or not text:
            continue
        st.markdown(text)
        st.caption(
            f"👍 {_safe_int(comment.get('agree_count', 0))}   "
            f"👎 {_safe_int(comment.get('disagree_count', 0))}"
        )
        cols = st.columns([1, 1, 4])
        like_clicked = cols[0].button(
            "👍 Like",
            key=f"delib_q_like_{convo_id}_{comment_id}",
        )
        dislike_clicked = cols[1].button(
            "👎 Dislike",
            key=f"delib_q_dislike_{convo_id}_{comment_id}",
        )
        if like_clicked:
            if _cast_swipe_vote(convo_id, comment_id, 1, headers):
                st.session_state[f"delib_questionnaire_focus_comment_{convo_id}"] = comment_id
                st.rerun()
        if dislike_clicked:
            if _cast_swipe_vote(convo_id, comment_id, -1, headers):
                st.session_state[f"delib_questionnaire_focus_comment_{convo_id}"] = comment_id
                st.rerun()
        st.divider()


def _render_csv_data_entry_workspace(convo_id: str) -> None:
    st.markdown("### Seed comments from CSV column")
    st.caption("Upload a CSV and pick a column to turn each row into a comment.")
    csv_upload = st.file_uploader("CSV", type=["csv"], key="delib_seed_csv_upload")
    if csv_upload is not None:
        try:
            df_seed = pd.read_csv(csv_upload)
        except Exception as exc:
            st.error(f"Could not read CSV: {exc}")
            df_seed = pd.DataFrame()
        if not df_seed.empty:
            st.dataframe(df_seed.head(10), use_container_width=True)
            col = st.selectbox(
                "Column to use as comment text",
                options=[""] + df_seed.columns.tolist(),
                key="delib_seed_csv_col",
            )
            max_rows = st.number_input(
                "Max rows to seed",
                min_value=1,
                max_value=5000,
                value=200,
                step=50,
                key="delib_seed_csv_max_rows",
            )
            if st.button(
                "Seed from CSV",
                key="delib_seed_csv_btn",
                help="Create seed comments from the selected CSV column.",
            ):
                if not col:
                    st.warning("Select a column.")
                else:
                    values = [
                        str(v).strip()
                        for v in df_seed[col].head(int(max_rows)).tolist()
                        if str(v).strip() and str(v).strip().lower() not in {"nan", "none"}
                    ]
                    values = list(dict.fromkeys(values))
                    if not values:
                        st.warning("No valid values found in that column.")
                    else:
                        result = delib_api_post(
                            f"/conversations/{convo_id}/seed-comments:bulk",
                            {"comments": values},
                        )
                        if result:
                            st.success(
                                f"Seeded {result.get('created', 0)} comments from CSV."
                            )

    st.markdown("### One-file CSV import (question + comments + reactions)")
    st.caption(
        "Upload one CSV containing comment records and vote reactions. "
        "Useful columns: conversation_id, participant_id, participant_cluster, "
        "comment_id, comment_text, is_seed, comment_created_at, vote, reaction_created_at."
    )
    combined_upload = st.file_uploader(
        "Combined deliberation CSV",
        type=["csv"],
        key="delib_combined_csv_upload",
    )
    if combined_upload is None:
        return
    try:
        df_combined = pd.read_csv(combined_upload)
    except Exception as exc:
        st.error(f"Could not read combined CSV: {exc}")
        df_combined = pd.DataFrame()
    if df_combined.empty:
        return

    st.dataframe(df_combined.head(10), use_container_width=True)
    columns = df_combined.columns.tolist()
    options = [""] + columns

    conversation_default = _guess_column(
        columns,
        {"conversation_id", "conversation", "conversationid"},
    )
    participant_default = _guess_column(
        columns,
        {"participant_id", "participant", "voter_id", "user_id"},
    )
    participant_cluster_default = _guess_column(
        columns,
        {"participant_cluster", "cluster_id", "cluster", "segment"},
    )
    comment_id_default = _guess_column(
        columns,
        {"comment_id", "statement_id", "seed_id"},
    )
    comment_text_default = _guess_column(
        columns,
        {"comment_text", "comment", "text", "statement"},
    )
    is_seed_default = _guess_column(columns, {"is_seed", "seed"})
    comment_created_default = _guess_column(
        columns,
        {"comment_created_at", "comment_created", "created_at"},
    )
    vote_default = _guess_column(
        columns,
        {"vote", "choice", "reaction"},
    )
    reaction_created_default = _guess_column(
        columns,
        {"reaction_created_at", "vote_created_at", "voted_at"},
    )

    map_cols = st.columns(4)
    with map_cols[0]:
        conversation_col = st.selectbox(
            "Conversation ID column (optional)",
            options=options,
            index=options.index(conversation_default)
            if conversation_default in options
            else 0,
            key="delib_combined_conversation_col",
        )
        participant_col = st.selectbox(
            "Participant ID column",
            options=options,
            index=options.index(participant_default)
            if participant_default in options
            else 0,
            key="delib_combined_participant_col",
        )
        participant_cluster_col = st.selectbox(
            "Participant cluster column (optional)",
            options=options,
            index=options.index(participant_cluster_default)
            if participant_cluster_default in options
            else 0,
            key="delib_combined_participant_cluster_col",
        )
    with map_cols[1]:
        comment_id_col = st.selectbox(
            "Comment ID column *",
            options=options,
            index=options.index(comment_id_default)
            if comment_id_default in options
            else 0,
            key="delib_combined_comment_id_col",
        )
        comment_text_col = st.selectbox(
            "Comment text column (optional)",
            options=options,
            index=options.index(comment_text_default)
            if comment_text_default in options
            else 0,
            key="delib_combined_comment_text_col",
        )
    with map_cols[2]:
        is_seed_col = st.selectbox(
            "is_seed column (optional)",
            options=options,
            index=options.index(is_seed_default) if is_seed_default in options else 0,
            key="delib_combined_is_seed_col",
        )
        comment_created_col = st.selectbox(
            "comment_created_at column (optional)",
            options=options,
            index=options.index(comment_created_default)
            if comment_created_default in options
            else 0,
            key="delib_combined_comment_created_col",
        )
    with map_cols[3]:
        vote_col = st.selectbox(
            "Vote column (optional)",
            options=options,
            index=options.index(vote_default) if vote_default in options else 0,
            key="delib_combined_vote_col",
        )
        reaction_created_col = st.selectbox(
            "reaction_created_at column (optional)",
            options=options,
            index=options.index(reaction_created_default)
            if reaction_created_default in options
            else 0,
            key="delib_combined_reaction_created_col",
        )

    controls = st.columns([1, 1])
    with controls[0]:
        max_combined_rows = st.number_input(
            "Max rows to import",
            min_value=1,
            max_value=50000,
            value=5000,
            step=100,
            key="delib_combined_max_rows",
        )
    with controls[1]:
        run_analysis_after_combined = st.checkbox(
            "Run analysis after one-file import",
            value=True,
            key="delib_combined_run_analysis",
        )

    if not st.button(
        "Import one-file CSV",
        key="delib_combined_import_btn",
        help="Import comments + reactions from a single CSV file.",
    ):
        return
    if not comment_id_col:
        st.warning("Select a Comment ID column.")
        return

    subset = df_combined.head(int(max_combined_rows))
    rows = []
    for source in subset.to_dict(orient="records"):
        comment_id = _clean_id_csv_value(source.get(comment_id_col))
        if not comment_id:
            continue
        row_payload = {"comment_id": comment_id}
        if conversation_col:
            conversation_value = _clean_optional_text_csv_value(source.get(conversation_col))
            if conversation_value:
                row_payload["conversation_id"] = conversation_value
        if participant_col:
            participant_value = _clean_id_csv_value(source.get(participant_col))
            if participant_value:
                row_payload["participant_id"] = participant_value
        if participant_cluster_col:
            participant_cluster_value = _clean_optional_text_csv_value(
                source.get(participant_cluster_col)
            )
            if participant_cluster_value:
                row_payload["participant_cluster"] = participant_cluster_value
        if comment_text_col:
            comment_text_value = _clean_optional_text_csv_value(source.get(comment_text_col))
            if comment_text_value:
                row_payload["comment_text"] = comment_text_value
        if is_seed_col:
            is_seed_value = _clean_optional_bool_csv_value(source.get(is_seed_col))
            if is_seed_value is not None:
                row_payload["is_seed"] = is_seed_value
        if comment_created_col:
            comment_created_value = _clean_optional_text_csv_value(
                source.get(comment_created_col)
            )
            if comment_created_value:
                row_payload["comment_created_at"] = comment_created_value
        if vote_col:
            vote_value = _clean_vote_csv_value(source.get(vote_col))
            if vote_value is not None:
                row_payload["vote"] = vote_value
        if reaction_created_col:
            reaction_created_value = _clean_optional_text_csv_value(
                source.get(reaction_created_col)
            )
            if reaction_created_value:
                row_payload["reaction_created_at"] = reaction_created_value
        rows.append(row_payload)

    if not rows:
        st.warning("No valid rows found for import.")
        return

    result = delib_api_post(
        f"/conversations/{convo_id}/dataset:bulk",
        {"rows": rows},
    )
    if not result:
        return

    mismatch_rows = int(result.get("conversation_mismatch_rows", 0) or 0)
    st.success(
        "Imported one-file dataset: "
        f"{result.get('comments_created', 0)} comments created, "
        f"{result.get('comments_updated', 0)} comments updated, "
        f"{result.get('votes_imported', 0)} votes imported, "
        f"{result.get('skipped_rows', 0)} rows skipped."
    )
    if mismatch_rows > 0:
        st.caption(
            f"Note: {mismatch_rows} row(s) had a different conversation_id in the file; "
            "they were still imported into the selected conversation."
        )
    if run_analysis_after_combined:
        refreshed = delib_api_post(
            f"/conversations/{convo_id}/analyze",
            {},
        )
        if refreshed:
            st.success("Reports has been refreshed with the imported dataset.")


def render_deliberation(public_only: bool):
    questionnaire_mode = _is_questionnaire_participation_mode()

    if questionnaire_mode:
        _apply_questionnaire_card_only_layout()
        _inject_questionnaire_parent_hide_script()
        sid = str(_get_query_param("sid") or "").strip()
        convo_id = str(
            _get_query_param("conversation_id")
            or _get_query_param("conversation")
            or st.session_state.get("delib_conversation_id")
            or ""
        ).strip()
        if not convo_id:
            st.error("Missing conversation_id in participant link.")
            return
        st.session_state["delib_conversation_id"] = convo_id
        _ensure_questionnaire_query_defaults(convo_id)
        participant_id = _resolve_participant_id(convo_id, questionnaire_mode=True, sid=sid)
        participant_scope = f"{participant_id}_{sid}" if sid else participant_id
        headers = {"X-Participant-Id": participant_id}
        convo_cache_key = f"delib_questionnaire_convo_cache_{convo_id}"
        convo = delib_api_get(f"/conversations/{convo_id}", show_error=False)
        if convo:
            st.session_state[convo_cache_key] = convo
        else:
            convo = st.session_state.get(convo_cache_key)
            if not convo:
                render_delib_api_unavailable()
                return
        q_notice_key = f"delib_questionnaire_comment_notice_{convo_id}"
        q_notice = st.session_state.pop(q_notice_key, None)
        if q_notice == "pending":
            st.info("Comment submitted. It is awaiting moderation before it appears in the feed.")
        elif q_notice == "approved":
            st.success("Comment submitted and added to the feed.")
        comments_cache_key = f"delib_questionnaire_comments_cache_{convo_id}"
        fetched_comments = delib_api_get(
            f"/conversations/{convo_id}/comments?status=approved",
            show_error=False,
        )
        if fetched_comments is not None:
            comments = fetched_comments
            st.session_state[comments_cache_key] = comments
        else:
            comments = st.session_state.get(comments_cache_key) or []
            if not comments:
                render_delib_api_unavailable()
                return
        if not comments:
            st.info("No approved comments yet.")
        else:
            comments = comments[:MOBILE_QUESTIONNAIRE_CARD_LIMIT]
            st.caption(f"Mobile deck size: {len(comments)}/{MOBILE_QUESTIONNAIRE_CARD_LIMIT} cards")
            if MOBILE_QUESTIONNAIRE_USE_THIRD_PARTY_SWIPE:
                swipe_state = _render_swipe_component(
                    comments,
                    convo_id,
                    headers,
                    compact=True,
                    participant_scope=participant_scope,
                )
                if not bool((swipe_state or {}).get("deck_ok", True)):
                    st.info("Swipe deck recovered in stable mode.")
                    _render_mobile_questionnaire_cards(
                        comments,
                        convo_id,
                        headers,
                        participant_scope=participant_scope,
                    )
            else:
                _render_mobile_questionnaire_cards(
                    comments,
                    convo_id,
                    headers,
                    participant_scope=participant_scope,
                )
        if convo.get("allow_comment_submission", True):
            _render_questionnaire_comment_form(convo_id, headers)
        return

    conversations = delib_api_get("/conversations", show_error=False)
    if conversations is None:
        render_delib_api_unavailable()
        return
    conversations = conversations or []
    participant_id = _resolve_participant_id("", questionnaire_mode=False)
    headers = {"X-Participant-Id": participant_id}

    st.subheader("Deliberation Workspace")
    st.caption("Plan, launch, moderate, and analyze each conversation from one workflow.")
    convo_lookup = {}
    convo_options = {}
    for convo in conversations:
        convo_id = str(convo.get("id") or "").strip()
        topic = str(convo.get("topic") or "").strip() or "Untitled conversation"
        if not convo_id:
            continue
        label = topic
        if label in convo_options:
            label = f"{topic} [{convo_id[:8]}]"
        convo_lookup[convo_id] = convo
        convo_options[label] = convo_id

    def _render_conversation_workspace() -> None:
        st.markdown("### Conversation control center")
        st.caption("Select one active conversation, then run setup, participation, moderation, and insights.")
        convo_labels = list(convo_options.keys())
        selected_index = 0
        active_convo_id = str(st.session_state.get("delib_conversation_id") or "").strip()
        if active_convo_id:
            for i, label in enumerate(convo_labels, start=1):
                if convo_options.get(label) == active_convo_id:
                    selected_index = i
                    break
        selected_title = st.selectbox(
            "Active conversation",
            [""] + convo_labels,
            index=selected_index,
            key="delib_conversation_picker",
            help="Pick the active conversation once, then continue in other tabs.",
        )
        if selected_title:
            st.session_state["delib_conversation_id"] = convo_options[selected_title]

        convo_id = str(st.session_state.get("delib_conversation_id") or "").strip()
        convo = convo_lookup.get(convo_id)
        if convo:
            topic = str(convo.get("topic") or "Untitled conversation")
            st.success(f"Active conversation: {topic}")
            status_tokens = [
                "Open" if convo.get("is_open", True) else "Closed",
                (
                    "Comments enabled"
                    if convo.get("allow_comment_submission", True)
                    else "Comments disabled"
                ),
                (
                    "Moderation required"
                    if convo.get("moderation_required", False)
                    else "Moderation optional"
                ),
            ]
            st.caption(" | ".join(status_tokens))
            description = str(convo.get("description") or "").strip()
            if description:
                st.write(description)
            approved_preview = (
                delib_api_get(
                    f"/conversations/{convo_id}/comments?status=approved",
                    show_error=False,
                )
                or []
            )
            pending_preview = (
                delib_api_get(
                    f"/conversations/{convo_id}/comments?status=pending",
                    show_error=False,
                )
                or []
            )
            metric_cols = st.columns(3)
            metric_cols[0].metric("Approved comments", len(approved_preview))
            metric_cols[1].metric("Pending moderation", len(pending_preview))
            metric_cols[2].metric(
                "Participation",
                "Open" if convo.get("is_open", True) else "Closed",
            )
            if public_only:
                st.caption("Continue in Join Conversation and Results tabs.")
            else:
                st.caption(
                    "Recommended flow: Overview -> Setup -> Moderation -> Insights."
                )
        elif conversations:
            st.info("Select an active conversation to unlock participation and reports.")
        elif public_only:
            st.info("No conversations are available right now.")
        else:
            st.info("No conversations yet. Create one in Setup.")

        if public_only:
            return

        st.markdown("---")
        st.markdown("### Conversation manager")
        active_items = [
            c
            for c in conversations
            if bool(c.get("is_open", True))
        ]
        past_items = [
            c
            for c in conversations
            if not bool(c.get("is_open", True))
        ]
        manager_active_tab, manager_past_tab, manager_create_tab = st.tabs(
            ["Active conversations", "Past conversations", "Create conversation"]
        )
        with manager_active_tab:
            if not active_items:
                st.caption("No active conversations.")
            for item in active_items:
                cid = str(item.get("id") or "").strip()
                topic = str(item.get("topic") or "Untitled conversation")
                if not cid:
                    continue
                row_cols = st.columns([6, 1, 1])
                row_cols[0].markdown(f"**{topic}**  \n`{cid}`")
                if row_cols[1].button("Use", key=f"delib_mgr_use_active_{cid}"):
                    st.session_state["delib_conversation_id"] = cid
                    st.rerun()
                if row_cols[2].button("Close", key=f"delib_mgr_close_{cid}"):
                    result = delib_api_patch(f"/conversations/{cid}", {"is_open": False})
                    if result:
                        st.success(f"Closed: {topic}")
                        st.rerun()
        with manager_past_tab:
            if not past_items:
                st.caption("No past conversations.")
            for item in past_items:
                cid = str(item.get("id") or "").strip()
                topic = str(item.get("topic") or "Untitled conversation")
                if not cid:
                    continue
                row_cols = st.columns([6, 1, 1])
                row_cols[0].markdown(f"**{topic}**  \n`{cid}`")
                if row_cols[1].button("Use", key=f"delib_mgr_use_past_{cid}"):
                    st.session_state["delib_conversation_id"] = cid
                    st.rerun()
                if row_cols[2].button("Reopen", key=f"delib_mgr_reopen_{cid}"):
                    result = delib_api_patch(f"/conversations/{cid}", {"is_open": True})
                    if result:
                        st.success(f"Reopened: {topic}")
                        st.rerun()
        with manager_create_tab:
            st.caption("Quick-create a new conversation. Advanced settings remain in Setup.")
            quick_topic = st.text_input("Topic", key="delib_quick_create_topic")
            quick_description = st.text_area(
                "Description",
                key="delib_quick_create_description",
                height=90,
            )
            quick_cols = st.columns(3)
            quick_allow_comments = quick_cols[0].checkbox(
                "Allow comments",
                value=True,
                key="delib_quick_allow_comments",
            )
            quick_moderation = quick_cols[1].checkbox(
                "Moderation required",
                value=False,
                key="delib_quick_moderation",
            )
            quick_open = quick_cols[2].checkbox(
                "Open now",
                value=True,
                key="delib_quick_open",
            )
            if st.button("Create conversation", key="delib_quick_create_btn"):
                topic_value = str(quick_topic or "").strip()
                if len(topic_value) < 3:
                    st.warning("Topic must be at least 3 characters.")
                else:
                    created = delib_api_post(
                        "/conversations",
                        {
                            "topic": topic_value,
                            "description": quick_description,
                            "allow_comment_submission": quick_allow_comments,
                            "allow_viz": True,
                            "moderation_required": quick_moderation,
                            "is_open": quick_open,
                        },
                    )
                    if created:
                        created_id = str(created.get("id") or "").strip()
                        if created_id:
                            st.session_state["delib_conversation_id"] = created_id
                        st.success("Conversation created.")
                        st.rerun()

    def _render_participation_workspace() -> None:
        convo_id = st.session_state.get("delib_conversation_id")
        if not convo_id:
            st.info("Select a conversation first.")
            return

        convo = delib_api_get(f"/conversations/{convo_id}")
        if convo:
            st.subheader(convo["topic"])
            st.caption(convo.get("description") or "")
            if not convo.get("is_open", True):
                st.warning("This conversation is closed.")
        p_notice_key = f"delib_participate_comment_notice_{convo_id}"
        p_notice = st.session_state.pop(p_notice_key, None)
        if p_notice == "pending":
            st.info("Comment submitted. It is awaiting moderation before it appears in the feed.")
        elif p_notice == "approved":
            st.success("Comment submitted and added to the feed.")

        comments = delib_api_get(f"/conversations/{convo_id}/comments?status=approved") or []
        if not comments:
            st.info("No approved comments yet.")
        else:
            _render_swipe_component(
                comments,
                convo_id,
                headers,
                compact=False,
                participant_scope=participant_id,
            )

        if convo and convo.get("allow_comment_submission", True):
            st.markdown("### Submit comment")
            new_comment = st.text_area("Your comment", key="delib_submit_comment")
            if st.button(
                "Submit comment",
                key="delib_submit_comment_btn",
                help="Submit a new comment into this conversation (may require moderation).",
            ):
                text = new_comment.strip()
                if not text:
                    st.warning("Comment cannot be empty.")
                elif len(text) < 2:
                    st.warning("Comment should be at least 2 characters.")
                else:
                    result = delib_api_post(
                        f"/conversations/{convo_id}/comments",
                        {"text": text},
                        headers=headers,
                    )
                    if result:
                        status = str(result.get("status", "")).lower()
                        notice_key = f"delib_participate_comment_notice_{convo_id}"
                        if status == "pending":
                            st.session_state[notice_key] = "pending"
                        else:
                            st.session_state[notice_key] = "approved"
                        st.rerun()
        else:
            st.caption("Comment submission is disabled for this conversation.")

    if public_only:
        tab_join, tab_reports = st.tabs(["Join Conversation", "Results"])
        with tab_join:
            _render_conversation_workspace()
            st.markdown("---")
            st.markdown("### Participate")
            _render_participation_workspace()
    else:
        tab_overview, tab_setup, tab_moderate, tab_reports, tab_data_entry = st.tabs(
            [
                "Overview",
                "Setup",
                "Moderation",
                "Insights",
                "Data Entry",
            ]
        )
        with tab_overview:
            _render_conversation_workspace()
            st.markdown("---")
            st.markdown("### Workspace guide")
            st.info(
                "Use Setup to configure and share, Moderation to approve pending comments, "
                "and Insights for analytics."
            )

        with tab_setup:
            st.markdown("### Shareable links")
            render_questionnaire_block("all", show_expander=False)

            st.markdown("---")
            st.markdown("### Create new conversation")
            topic = st.text_input(
                "Topic",
                key="delib_topic",
                help="Conversation title participants will see.",
            )
            description = st.text_area(
                "Description",
                key="delib_description",
                help="Context shown above the conversation during participation.",
            )
            allow_comment_submission = st.checkbox(
                "Allow participant comments",
                value=True,
                key="delib_allow_comment",
                help="If enabled, participants can submit new comments (may be moderated).",
            )
            allow_viz = st.checkbox(
                "Allow visualization",
                value=True,
                key="delib_allow_viz",
                help="If enabled, show cluster charts/visualizations in reports.",
            )
            moderation_required = st.checkbox(
                "Moderation required",
                value=False,
                key="delib_moderation",
                help="If enabled, submitted comments require approval before becoming voteable.",
            )
            is_open = st.checkbox(
                "Open for participation",
                value=True,
                key="delib_is_open",
                help="If disabled, participation is closed (read-only).",
            )
            if st.button(
                "Create conversation",
                key="delib_create_convo",
                help="Create a new deliberation conversation (topic + settings).",
            ):
                if len(topic.strip()) >= 3:
                    result = delib_api_post(
                        "/conversations",
                        {
                            "topic": topic,
                            "description": description,
                            "allow_comment_submission": allow_comment_submission,
                            "allow_viz": allow_viz,
                            "moderation_required": moderation_required,
                            "is_open": is_open,
                        },
                    )
                    if result:
                        created_convo_id = str(result.get("id") or "").strip()
                        if created_convo_id:
                            st.session_state["delib_conversation_id"] = created_convo_id
                        st.success("Conversation created.")
                        st.rerun()
                else:
                    st.warning("Topic must be at least 3 characters.")

            convo_id = st.session_state.get("delib_conversation_id")
            if convo_id:
                st.markdown("### Update conversation")
                convo = delib_api_get(f"/conversations/{convo_id}")
                if convo:
                    updated_topic = st.text_input(
                        "Topic (edit)", value=convo.get("topic", ""), key="delib_topic_edit"
                    )
                    updated_description = st.text_area(
                        "Description (edit)",
                        value=convo.get("description") or "",
                        key="delib_description_edit",
                    )
                    updated_allow_comment = st.checkbox(
                        "Allow participant comments (edit)",
                        value=convo.get("allow_comment_submission", True),
                        key="delib_allow_comment_edit",
                    )
                    updated_allow_viz = st.checkbox(
                        "Allow visualization (edit)",
                        value=convo.get("allow_viz", True),
                        key="delib_allow_viz_edit",
                    )
                    updated_moderation = st.checkbox(
                        "Moderation required (edit)",
                        value=convo.get("moderation_required", False),
                        key="delib_moderation_edit",
                    )
                    updated_is_open = st.checkbox(
                        "Open for participation (edit)",
                        value=convo.get("is_open", True),
                        key="delib_is_open_edit",
                    )
                    if st.button(
                        "Save settings",
                        key="delib_save_settings",
                        help="Update conversation settings (open/closed, moderation, etc.).",
                    ):
                        result = delib_api_patch(
                            f"/conversations/{convo_id}",
                            {
                                "topic": updated_topic,
                                "description": updated_description,
                                "allow_comment_submission": updated_allow_comment,
                                "allow_viz": updated_allow_viz,
                                "moderation_required": updated_moderation,
                                "is_open": updated_is_open,
                            },
                        )
                        if result:
                            st.success("Conversation updated.")

                    st.markdown("### Generate demo votes")
                    st.caption(
                        "Use this to quickly populate reports/charts for demos when real votes are low."
                    )
                    demo_cols = st.columns(3)
                    with demo_cols[0]:
                        demo_participants = st.number_input(
                            "Participants",
                            min_value=1,
                            max_value=1000,
                            value=120,
                            step=10,
                            key="delib_demo_participants",
                        )
                    with demo_cols[1]:
                        demo_votes_per = st.number_input(
                            "Votes per participant",
                            min_value=1,
                            max_value=200,
                            value=20,
                            step=1,
                            key="delib_demo_votes_per",
                        )
                    with demo_cols[2]:
                        demo_seed = st.number_input(
                            "Seed",
                            min_value=0,
                            max_value=999999,
                            value=42,
                            step=1,
                            key="delib_demo_seed",
                        )
                    if st.button(
                        "Generate demo votes",
                        key="delib_generate_demo_votes",
                        help="Create simulated participants and votes for the selected conversation.",
                    ):
                        result = delib_api_post(
                            f"/conversations/{convo_id}/simulate-votes",
                            {
                                "participants": int(demo_participants),
                                "votes_per_participant": int(demo_votes_per),
                                "seed": int(demo_seed),
                            },
                        )
                        if result:
                            st.success(
                                f"Generated {result.get('generated_votes', 0)} votes "
                                f"across {result.get('participants', 0)} participants."
                            )

                    st.markdown("### Seed comments (bulk)")
                    seed_text = st.text_area(
                        "One comment per line",
                        key="delib_seed_text",
                        help="Seed statements/questions as separate comments so participants can vote on a shared set.",
                    )
                    if st.button(
                        "Add seed comments",
                        key="delib_seed_submit",
                        help="Bulk add seed comments (one per line).",
                    ):
                        lines = [line.strip() for line in seed_text.splitlines() if line.strip()]
                        if lines:
                            result = delib_api_post(
                                f"/conversations/{convo_id}/seed-comments:bulk",
                                {"comments": lines},
                            )
                            if result:
                                st.success(f"Added {result.get('created', 0)} comments.")
                        else:
                            st.warning("Add at least one comment.")

                    st.caption(
                        "CSV upload/import tools moved to the Data Entry tab."
                    )

            else:
                st.info("Select a conversation to edit settings.")

        with tab_data_entry:
            convo_id = st.session_state.get("delib_conversation_id")
            if not convo_id:
                st.info("Select an active conversation in Overview first.")
            else:
                st.markdown("### Data entry & imports")
                _render_csv_data_entry_workspace(str(convo_id))

    if not public_only:
        with tab_moderate:
            convo_id = st.session_state.get("delib_conversation_id")
            if not convo_id:
                st.info("Select a conversation first.")
            else:
                pending = delib_api_get(
                    f"/conversations/{convo_id}/comments?status=pending"
                ) or []
                if not pending:
                    st.info("No pending comments.")
                else:
                    for comment in pending:
                        st.markdown(f"**{comment['text']}**")
                        cols = st.columns(2)
                        if cols[0].button(
                            "Approve",
                            key=f"delib-{comment['id']}-approve",
                            help="Approve this pending comment so it becomes voteable.",
                        ):
                            delib_api_patch(
                                f"/comments/{comment['id']}", {"status": "approved"}
                            )
                        if cols[1].button(
                            "Reject",
                            key=f"delib-{comment['id']}-reject",
                            help="Reject this pending comment.",
                        ):
                            delib_api_patch(
                                f"/comments/{comment['id']}", {"status": "rejected"}
                            )
                        st.divider()

    with tab_reports:
        convo_id = st.session_state.get("delib_conversation_id")
        if not convo_id:
            st.info("Select a conversation first.")
        else:
            report_tab, csv_tab = st.tabs(["Vote-based report", "CSV clustering"])

            with report_tab:
                if st.button(
                    "Run analysis",
                    key="delib_run_analysis",
                    help="Compute clusters + consensus/polarizing topics from votes.",
                ):
                    report = delib_api_post(f"/conversations/{convo_id}/analyze", {})
                else:
                    report = delib_api_get(f"/conversations/{convo_id}/report")

                if report:
                    metrics = report["metrics"]
                    total_comments = int(metrics.get("total_comments", 0))
                    total_participants = int(metrics.get("total_participants", 0))
                    total_votes = int(metrics.get("total_votes", 0))
                    st.metric("Comments", total_comments)
                    st.metric("Participants", total_participants)
                    st.metric("Votes", total_votes)
                    avg_votes_per_participant = (
                        round(total_votes / total_participants, 2) if total_participants > 0 else 0.0
                    )
                    st.caption(
                        f"Clustering input: {total_participants} participants, {total_votes} votes "
                        f"(avg {avg_votes_per_participant} votes/participant)."
                    )
                    if total_participants < 2:
                        st.warning("Need at least 2 participants with votes to generate opinion clusters.")
                    elif total_votes < 6:
                        st.info(
                            "Vote volume is still low; clustering may look unstable. "
                            "You can import a one-file CSV dataset from Data Entry."
                        )

                    st.subheader("Potential agreement topics")
                    potential_agreements = report.get("potential_agreements", [])
                    if potential_agreements:
                        for topic in potential_agreements:
                            st.markdown(f"- {topic}")
                    else:
                        st.caption("No strong agreement topics yet.")

                    st.subheader("Consensus statements")
                    consensus_df = pd.DataFrame(metrics["consensus"])
                    if consensus_df.empty:
                        st.caption("No consensus statements yet.")
                    else:
                        st.dataframe(consensus_df, use_container_width=True)

                    st.subheader("Polarizing statements")
                    polarizing_df = pd.DataFrame(metrics["polarizing"])
                    if polarizing_df.empty:
                        st.caption("No polarizing statements yet.")
                    else:
                        st.dataframe(polarizing_df, use_container_width=True)

                    st.subheader("Cluster summaries")
                    summaries_df = pd.DataFrame(report.get("cluster_summaries", []))
                    if summaries_df.empty:
                        st.caption("No cluster summaries available yet.")
                    else:
                        st.dataframe(summaries_df, use_container_width=True)

                    st.subheader("Cluster similarity")
                    similarity_df = pd.DataFrame(report.get("cluster_similarity", []))
                    if similarity_df.empty:
                        st.caption("No similarity data available yet.")
                    else:
                        similarity_df["similarity"] = similarity_df["similarity"].round(3)
                        st.dataframe(similarity_df, use_container_width=True)

                    st.subheader("Venn diagram: shared agreement topics")
                    summaries = report.get("cluster_summaries", [])
                    if not summaries or len(summaries) < 2:
                        st.caption("Need at least two clusters with agreement topics.")
                    elif plt is None or (venn2 is None and venn3 is None):
                        st.caption("matplotlib-venn is required for Venn diagrams.")
                    else:
                        summaries = sorted(
                            summaries, key=lambda s: s.get("size", 0), reverse=True
                        )
                        selected = summaries[:3]
                        sets = [set(item.get("top_agree", [])) for item in selected]
                        if not any(sets):
                            st.caption("No overlapping agreement topics yet.")
                        else:
                            labels = [
                                f"{item.get('cluster_id')} ({item.get('size', 0)})"
                                for item in selected
                            ]
                            fig, ax = plt.subplots()
                            if len(selected) == 2 and venn2:
                                venn2(sets, set_labels=labels, ax=ax)
                            elif len(selected) >= 3 and venn3:
                                venn3(sets[:3], set_labels=labels[:3], ax=ax)
                            st.pyplot(fig, clear_figure=True)

                    points_df = pd.DataFrame(report.get("points", []))
                    if not points_df.empty:
                        st.subheader("Opinion clusters")
                        chart = (
                            alt.Chart(points_df)
                            .mark_circle(size=60, opacity=0.7)
                            .encode(
                                x="x:Q",
                                y="y:Q",
                                color="cluster_id:N",
                                tooltip=["cluster_id", "participant_id"],
                            )
                        )
                        st.altair_chart(chart, use_container_width=True)
                    elif total_participants >= 2 and total_votes > 0:
                        st.caption(
                            "No cluster chart points available yet. Ensure votes reference approved comment IDs, "
                            "then click Run analysis."
                        )

            with csv_tab:
                st.subheader("CSV clustering workflow")
                st.caption(
                    "Use Data Entry → One-file CSV import (question + comments + reactions) to import data, then click Run analysis in "
                    "Vote-based report."
                )
                sample_df = pd.DataFrame(
                    [
                        {
                            "participant_id": "anon_001",
                            "comment_id": "comment-uuid-1",
                            "vote": "agree",
                        },
                        {
                            "participant_id": "anon_001",
                            "comment_id": "comment-uuid-2",
                            "vote": "pass",
                        },
                        {
                            "participant_id": "anon_002",
                            "comment_id": "comment-uuid-1",
                            "vote": "disagree",
                        },
                    ]
                )
                st.dataframe(sample_df, use_container_width=True)
