from base64 import b64encode
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import streamlit as st

BACKGROUND_IMAGE = Path(__file__).with_name("assets") / "userform-background.jpg"
ThemeType = Literal["light", "dark"]


@dataclass(frozen=True, slots=True)
class _ThemePalette:
    image_overlay: str
    header_background: str
    panel_background: str
    panel_border: str
    panel_shadow: str
    sidebar_background: str
    dealer_background: str
    dealer_text: str
    dealer_border: str
    dealer_marker: str
    save_background: str
    save_hover: str
    color_scheme: ThemeType


_LIGHT_PALETTE = _ThemePalette(
    image_overlay="rgba(255, 249, 232, 0.28), rgba(255, 249, 232, 0.28)",
    header_background="rgba(255, 249, 232, 0.78)",
    panel_background="rgba(255, 252, 243, 0.90)",
    panel_border="rgba(139, 30, 30, 0.22)",
    panel_shadow="rgba(72, 44, 18, 0.16)",
    sidebar_background="rgba(242, 229, 196, 0.96)",
    dealer_background="#E8F5E9",
    dealer_text="#173E1A",
    dealer_border="#2E7D32",
    dealer_marker="#2E7D32",
    save_background="#2E7D32",
    save_hover="#256629",
    color_scheme="light",
)
_DARK_PALETTE = _ThemePalette(
    image_overlay="rgba(10, 8, 7, 0.80), rgba(15, 12, 10, 0.88)",
    header_background="rgba(21, 17, 14, 0.84)",
    panel_background="rgba(21, 17, 14, 0.90)",
    panel_border="rgba(222, 180, 113, 0.30)",
    panel_shadow="rgba(0, 0, 0, 0.46)",
    sidebar_background="rgba(16, 13, 11, 0.97)",
    dealer_background="#263F2A",
    dealer_text="#E1F4E3",
    dealer_border="#70C77A",
    dealer_marker="#397D42",
    save_background="#357A3A",
    save_hover="#2D6731",
    color_scheme="dark",
)

_THEME_SYNC_SCRIPT = """
<script>
(() => {
    const targetDocument = document.querySelector('[data-testid="stAppViewContainer"]')
        ? document
        : window.parent.document;
    const targetWindow = targetDocument.defaultView;
    const app = targetDocument.querySelector('[data-testid="stAppViewContainer"]');
    if (!app || !targetWindow) return;

    const upsertMeta = (name, content) => {
        let meta = targetDocument.head.querySelector(`meta[name="${name}"]`);
        if (!meta) {
            meta = targetDocument.createElement('meta');
            meta.name = name;
            targetDocument.head.appendChild(meta);
        }
        if (meta.content !== content) meta.content = content;
    };

    // iOS reads these tags when a Safari page is launched from the home screen.
    // A black status bar avoids the white strip above the dark app shell.
    upsertMeta('apple-mobile-web-app-capable', 'yes');
    upsertMeta('apple-mobile-web-app-status-bar-style', 'black');
    upsertMeta('apple-mobile-web-app-title', 'Doppelkopf');

    const dismissChartTooltips = () => {
        for (const tooltip of targetDocument.querySelectorAll(
            '#vg-tooltip-element, .vg-tooltip'
        )) {
            tooltip.classList.remove('visible');
        }
    };

    const syncTheme = () => {
        const background = targetWindow.getComputedStyle(targetDocument.body).backgroundColor;
        const channels = background.match(/[0-9.]+/g)?.slice(0, 3).map(Number);
        if (!channels || channels.length !== 3) return;
        const linear = channels.map((channel) => {
            const normalized = channel / 255;
            return normalized <= 0.04045
                ? normalized / 12.92
                : ((normalized + 0.055) / 1.055) ** 2.4;
        });
        const luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
        const theme = luminance < 0.35 ? 'dark' : 'light';
        if (app.dataset.dokoTheme !== theme) app.dataset.dokoTheme = theme;
        upsertMeta('theme-color', theme === 'dark' ? '#15110E' : '#FFF9E8');
    };

    let scheduled = false;
    const scheduleSync = () => {
        if (scheduled) return;
        scheduled = true;
        targetWindow.requestAnimationFrame(() => {
            scheduled = false;
            syncTheme();
        });
    };

    targetWindow.__dokoThemeObserver?.disconnect();
    const observer = new targetWindow.MutationObserver(scheduleSync);
    observer.observe(targetDocument.head, {
        characterData: true,
        childList: true,
        subtree: true,
    });
    observer.observe(targetDocument.body, {
        attributes: true,
    });
    targetWindow.__dokoThemeObserver = observer;

    targetWindow.__dokoUiAbortController?.abort();
    const controller = new targetWindow.AbortController();
    targetDocument.addEventListener('pointerdown', dismissChartTooltips, {
        capture: true,
        signal: controller.signal,
    });
    targetDocument.addEventListener('scroll', dismissChartTooltips, {
        capture: true,
        passive: true,
        signal: controller.signal,
    });
    targetDocument.addEventListener('touchmove', dismissChartTooltips, {
        capture: true,
        passive: true,
        signal: controller.signal,
    });
    targetDocument.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') dismissChartTooltips();
    }, { signal: controller.signal });
    targetWindow.addEventListener('popstate', dismissChartTooltips, {
        signal: controller.signal,
    });
    targetWindow.__dokoUiAbortController = controller;

    dismissChartTooltips();
    syncTheme();
})();
</script>
"""


@lru_cache(maxsize=1)
def _encoded_background() -> str:
    return b64encode(BACKGROUND_IMAGE.read_bytes()).decode("ascii")


def _palette_css(selector: str, palette: _ThemePalette) -> str:
    return f"""
        {selector} {{
            color-scheme: {palette.color_scheme};
            --doko-dealer-background: {palette.dealer_background};
            --doko-dealer-text: {palette.dealer_text};
            --doko-dealer-border: {palette.dealer_border};
            --doko-dealer-marker: {palette.dealer_marker};
            --doko-save-background: {palette.save_background};
            --doko-save-hover: {palette.save_hover};
            background-image:
                linear-gradient({palette.image_overlay}),
                var(--doko-background-image);
        }}

        {selector} [data-testid="stHeader"] {{
            background-color: {palette.header_background};
        }}

        {selector} [data-testid="stMainBlockContainer"] {{
            background: {palette.panel_background};
            border-color: {palette.panel_border};
            box-shadow: 0 12px 36px {palette.panel_shadow};
        }}

        {selector} [data-testid="stSidebar"] > div:first-child {{
            background: {palette.sidebar_background};
        }}
    """


@lru_cache(maxsize=2)
def app_theme_css(theme_type: ThemeType) -> str:
    """Return the app shell and legacy-image treatment for one Streamlit theme."""
    app_selector = '[data-testid="stAppViewContainer"]'
    initial_palette = _DARK_PALETTE if theme_type == "dark" else _LIGHT_PALETTE

    return f"""
        <style>
            [data-testid="stAppViewContainer"] {{
                --doko-background-image:
                    url("data:image/jpeg;base64,{_encoded_background()}");
                background-position: center;
                background-repeat: no-repeat;
                background-size: cover;
                background-attachment: fixed;
            }}

            [data-testid="stMainBlockContainer"] {{
                border: 1px solid;
                border-radius: 14px;
                margin-top: 1rem;
                margin-bottom: 2rem;
            }}

            #vg-tooltip-element,
            .vg-tooltip {{
                max-width: min(22rem, calc(100vw - 1rem));
                pointer-events: none !important;
            }}

            #vg-tooltip-element:not(.visible),
            .vg-tooltip:not(.visible) {{
                opacity: 0 !important;
                visibility: hidden !important;
            }}

            {_palette_css(app_selector, initial_palette)}
            {_palette_css(f'{app_selector}[data-doko-theme="light"]', _LIGHT_PALETTE)}
            {_palette_css(f'{app_selector}[data-doko-theme="dark"]', _DARK_PALETTE)}

            @media (max-width: 768px) {{
                [data-testid="stMainBlockContainer"] {{
                    border-radius: 0;
                    margin-top: 0;
                    margin-bottom: 0;
                }}
            }}
        </style>
    """


@lru_cache(maxsize=2)
def app_theme_markup(theme_type: ThemeType) -> str:
    """Return the complete global theme markup and interaction safeguards."""
    return app_theme_css(theme_type) + _THEME_SYNC_SCRIPT


def apply_app_theme() -> None:
    """Apply the selected native theme to the legacy image and custom surfaces."""
    theme_type: ThemeType = "dark" if st.context.theme.type == "dark" else "light"
    st.html(
        app_theme_markup(theme_type),
        unsafe_allow_javascript=True,
    )
