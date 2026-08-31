"""Stable, repeatable scroll positioning for Streamlit interaction reruns."""

from __future__ import annotations

import json


# Every selectable-history page uses the same settling schedule: an immediate
# post-rerun position plus corrections for Streamlit's late form layout. The
# final two passes keep a large multi-action editor anchored even after its
# inputs finish rendering. The tolerance makes completed corrections no-ops.
FOCUS_DELAYS_MS = (80, 260, 520, 900, 1400)


def render_interaction_focus(
    components,
    *,
    nonce,
    target_id: str | None = None,
    target_expander_label: str | None = None,
    top_offset: int = 144,
):
    """Scroll the app viewport to an anchor or an existing expander after a rerun."""
    if (target_id is None) == (target_expander_label is None):
        raise ValueError("Provide exactly one scroll target.")
    if top_offset < 0:
        raise ValueError("The scroll top offset cannot be negative.")
    focus_target = target_id or f"expander:{target_expander_label}"
    script = """
        <script>
        const targetId = __TARGET_ID__;
        const targetExpanderLabel = __TARGET_EXPANDER_LABEL__;
        const focusKey = __FOCUS_KEY__;
        const delays = __DELAYS__;
        // Leave room for Streamlit's fixed header and the target expander's
        // summary, so the newly revealed content begins in the viewport.
        const topOffset = __TOP_OFFSET__;
        const positionTolerance = 2;
        let didNativeScroll = false;

        function findTarget(document) {
            if (targetId) return document.getElementById(targetId);
            return [...document.querySelectorAll('[data-testid="stExpander"]')].find(
                // Streamlit prepends its disclosure-icon label to the summary
                // text, so an exact equality check cannot find the expander.
                (expander) => expander.querySelector('summary')?.innerText.includes(targetExpanderLabel)
            ) || null;
        }

        function findContext() {
            let currentWindow = window;
            for (let level = 0; level < 5 && currentWindow; level += 1) {
                try {
                    const document = currentWindow.document;
                    const target = findTarget(document);
                    if (target) return { currentWindow, document, target };
                    currentWindow = currentWindow.parent;
                } catch (error) {
                    return null;
                }
            }
            return null;
        }

        const initialContext = findContext();
        if (initialContext) initialContext.document.documentElement.dataset.drcFocusKey = focusKey;

        function calibrateFocus() {
            const context = findContext();
            if (!context || context.document.documentElement.dataset.drcFocusKey !== focusKey) return;
            const { currentWindow, document, target } = context;
            const reduceMotion = currentWindow.matchMedia && currentWindow.matchMedia(
                '(prefers-reduced-motion: reduce)'
            ).matches;
            if (target.scrollIntoView) {
                target.scrollIntoView({
                    block: 'start',
                    inline: 'nearest',
                    behavior: reduceMotion || didNativeScroll ? 'auto' : 'smooth',
                });
                didNativeScroll = true;
            }
            const scrollCandidates = [
                ...document.querySelectorAll(
                    'section.stMain, section.main, [data-testid="stAppViewContainer"]'
                ),
            ].filter((element) => element.scrollHeight > element.clientHeight);
            const root = scrollCandidates.sort(
                (left, right) =>
                    (right.scrollHeight - right.clientHeight)
                    - (left.scrollHeight - left.clientHeight)
            )[0] || document.scrollingElement;
            const targetRect = target.getBoundingClientRect();
            const rootTop = root && root !== document.scrollingElement
                ? root.getBoundingClientRect().top
                : 0;
            const offset = targetRect.top - rootTop - topOffset;
            if (Math.abs(offset) <= positionTolerance) return;
            if (root && root !== document.scrollingElement && root.scrollTo) {
                root.scrollTo({ top: root.scrollTop + offset, behavior: 'auto' });
            } else if (currentWindow.scrollTo) {
                currentWindow.scrollTo({ top: currentWindow.scrollY + offset, behavior: 'auto' });
            }
        }

        delays.forEach((delay) => setTimeout(calibrateFocus, delay));
        </script>
    """.replace("__TARGET_ID__", json.dumps(target_id)).replace(
        "__TARGET_EXPANDER_LABEL__", json.dumps(target_expander_label)
    ).replace(
        "__FOCUS_KEY__", json.dumps(f"{focus_target}:{nonce}")
    ).replace("__DELAYS__", json.dumps(FOCUS_DELAYS_MS)).replace(
        "__TOP_OFFSET__", json.dumps(top_offset)
    )
    # A component iframe is recreated on every interaction rerun, so its script
    # executes even when the user clicks the currently selected matrix cell
    # again. st.html may retain the prior script node and skip re-execution.
    components.html(script, height=0, width=0)


def collapse_expander(components, *, target_expander_label: str, nonce: int):
    """Close an already-open Streamlit expander after a completed action.

    Streamlit can preserve an expander's browser-side state across a rerun,
    even when its Python ``expanded`` argument changes. Closing the rendered
    disclosure control makes a successful save deterministic without
    disturbing expanders that the user opened for unrelated work.
    """
    script = """
        <script>
        const targetLabel = __TARGET_EXPANDER_LABEL__;
        const nonce = __NONCE__;

        function findExpander() {
            let currentWindow = window;
            for (let level = 0; level < 5 && currentWindow; level += 1) {
                try {
                    const expander = [...currentWindow.document.querySelectorAll('[data-testid="stExpander"]')].find(
                        (item) => item.querySelector('summary')?.innerText.includes(targetLabel)
                    );
                    if (expander) return expander;
                    currentWindow = currentWindow.parent;
                } catch (error) {
                    return null;
                }
            }
            return null;
        }

        function closeExpander() {
            const expander = findExpander();
            const summary = expander?.querySelector('summary');
            const details = expander?.querySelector('details');
            const isOpen = Boolean(details?.open) || summary?.getAttribute('aria-expanded') === 'true';
            if (isOpen && summary) summary.click();
        }

        [80, 260, 520].forEach((delay) => setTimeout(closeExpander, delay));
        </script>
    """.replace("__TARGET_EXPANDER_LABEL__", json.dumps(target_expander_label)).replace(
        "__NONCE__", json.dumps(nonce)
    )
    components.html(script, height=0, width=0)
