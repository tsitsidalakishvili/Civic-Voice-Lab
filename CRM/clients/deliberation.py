import requests
import streamlit as st

from crm.config import (
    DELIBERATION_API_FALLBACK_URL,
    DELIBERATION_API_TIMEOUT_S,
    DELIBERATION_API_URL,
)


def _parse_timeout_seconds(value, default=20.0):
    try:
        timeout = float(value)
    except Exception:
        timeout = default
    return max(1.0, timeout)


def _delib_api_base_url():
    base = (DELIBERATION_API_URL or "").strip()
    return base.rstrip("/") if base else None


def _is_localhost_base(base: str) -> bool:
    text = (base or "").lower()
    return ("localhost" in text) or ("127.0.0.1" in text)


def _fallback_base_url():
    base = (DELIBERATION_API_FALLBACK_URL or "").strip()
    return base.rstrip("/") if base else None


def _set_last_error(kind: str | None = None, **kwargs):
    try:
        payload = {"kind": kind} if kind else {}
        payload.update(kwargs)
        st.session_state["delib_last_error"] = payload
    except Exception:
        pass


def _candidate_base_urls():
    urls = []
    primary = _delib_api_base_url()
    fallback = _fallback_base_url()
    if primary:
        urls.append(primary)
    if fallback and fallback not in urls:
        urls.append(fallback)
    return urls


def _delib_api_url(path: str, base: str):
    if not base:
        return None
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def _effective_timeout(url: str) -> float:
    timeout = _parse_timeout_seconds(DELIBERATION_API_TIMEOUT_S, default=20.0)
    # Render free services can cold-start in ~50s, so use a safer minimum there.
    if "onrender.com" in url:
        return max(timeout, 70.0)
    return timeout


def _request_json(method, path, payload=None, headers=None, show_error=True):
    bases = _candidate_base_urls()
    if not bases:
        if show_error:
            render_delib_api_unavailable()
        return None
    last_url = None
    last_exc = None
    last_http_status = None
    last_http_detail = None
    for base in bases:
        url = _delib_api_url(path, base)
        if not url:
            continue
        last_url = url
        timeout = _effective_timeout(url)
        try:
            response = requests.request(
                method=method,
                url=url,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            if response.status_code >= 400:
                last_http_status = response.status_code
                try:
                    body = response.json()
                    detail = body.get("detail", body)
                    backend_error = body.get("error")
                    if backend_error:
                        detail = f"{detail} | backend: {backend_error}"
                except Exception:
                    detail = response.text
                last_http_detail = detail
                _set_last_error(
                    "http",
                    status=last_http_status,
                    detail=str(last_http_detail),
                    url=url,
                )
                continue
            try:
                _set_last_error(None)
                return response.json()
            except ValueError:
                _set_last_error(None)
                return {}
        except requests.RequestException as exc:
            last_exc = exc
            _set_last_error("request", detail=str(exc), url=url)
            continue
    if show_error:
        if last_http_status is not None:
            st.error(
                f"Deliberation API error ({last_http_status}): {last_http_detail}"
            )
            return None
        if isinstance(last_exc, requests.Timeout):
            if last_url and "onrender.com" in last_url:
                st.error(
                    "Deliberation API timed out while waking up (Render cold start). "
                    "Please wait ~1 minute and retry."
                )
            else:
                st.error(f"Deliberation API timeout: {last_exc}")
            render_delib_api_unavailable()
        elif last_exc is not None:
            st.error(f"Deliberation API error: {last_exc}")
            render_delib_api_unavailable()
    return None


def render_delib_api_unavailable():
    bases = _candidate_base_urls()
    base = _delib_api_base_url()
    try:
        last_error = st.session_state.get("delib_last_error") or {}
    except Exception:
        last_error = {}
    last_kind = ""
    if isinstance(last_error, dict):
        last_kind = str(last_error.get("kind") or "").strip().lower()
    if bases:
        if last_kind == "http":
            st.warning("Deliberation backend is reachable but returned an application error.")
        else:
            st.warning("Deliberation backend is not reachable.")
        st.caption("Tried:")
        for item in bases:
            st.caption(f"- `{item}`")
        if base and ("localhost" in base or "127.0.0.1" in base):
            st.caption(
                "Streamlit Cloud cannot reach your local machine. "
                "Deploy the deliberation API separately and set `DELIBERATION_API_URL`."
            )
    else:
        st.warning("Deliberation backend is not configured.")
        st.caption("Set `DELIBERATION_API_URL` (or `API_URL`) in `.env`.")
    if isinstance(last_error, dict) and last_error:
        kind = str(last_error.get("kind") or "").strip()
        if kind == "http":
            st.caption(
                "Last API response: "
                f"HTTP {last_error.get('status')} from `{last_error.get('url')}` — "
                f"{last_error.get('detail')}"
            )
            st.caption(
                "The service is reachable but returned an application error "
                "(often backend DB/config issues)."
            )
        elif kind == "request":
            st.caption(
                "Last request error: "
                f"`{last_error.get('detail')}` against `{last_error.get('url')}`"
            )
    st.caption("If running locally, start the service with:")
    st.code(
        "python -m uvicorn deliberation.api.app.main:app --host 0.0.0.0 --port 8010"
    )


def delib_api_get(path, show_error=True):
    return _request_json("GET", path, show_error=show_error)


def delib_api_post(path, payload, headers=None, show_error=True):
    return _request_json("POST", path, payload=payload, headers=headers, show_error=show_error)


def delib_api_patch(path, payload, show_error=True):
    return _request_json("PATCH", path, payload=payload, show_error=show_error)


def delib_api_delete(path, show_error=True):
    return _request_json("DELETE", path, show_error=show_error)
