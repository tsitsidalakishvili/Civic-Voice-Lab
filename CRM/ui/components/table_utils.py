import streamlit as st


def render_table_with_export(
    df,
    *,
    key_prefix: str,
    filename: str,
    column_config: dict | None = None,
    height: int | None = None,
):
    # Kept for backward compatibility with existing call sites.
    _ = key_prefix, filename
    dataframe_kwargs = {
        "use_container_width": True,
        "column_config": column_config or {},
    }
    # Some Streamlit versions reject height=None.
    if isinstance(height, int) and height > 0:
        dataframe_kwargs["height"] = height
    st.dataframe(df, **dataframe_kwargs)
