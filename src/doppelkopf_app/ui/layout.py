import streamlit as st


def page_heading(title: str, *, icon: str) -> None:
    """Render a compact but unambiguous page heading."""
    st.subheader(title, icon=icon)
