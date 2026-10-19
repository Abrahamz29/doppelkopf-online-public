from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import streamlit as st

_COMPONENT_VERSION = "v20"

_HTML = """
<div class="score-entry">
  <label for="score-display">Ergebnis</label>
  <input id="score-display" class="display" type="text" inputmode="none" readonly
    placeholder="Punkte · +/− je Spieler · Re/Kontra · Bock" aria-label="Ergebnis" />
  <div class="name-spacer" aria-hidden="true">&nbsp;</div>
  <div class="keypad">
    <button type="button" data-key="1">1</button>
    <button type="button" data-key="2">2</button>
    <button type="button" data-key="3">3</button>
    <button type="button" data-key="+">+</button>
    <button type="button" data-key="4">4</button>
    <button type="button" data-key="5">5</button>
    <button type="button" data-key="6">6</button>
    <button type="button" data-key="-">−</button>
    <button type="button" data-key="7">7</button>
    <button type="button" data-key="8">8</button>
    <button type="button" data-key="9">9</button>
    <button type="button" data-key="B">B</button>
    <button type="button" data-action="backspace" aria-label="Letzte Eingabe löschen">⌫</button>
    <button type="button" data-key="0">0</button>
    <button type="button" data-key="R">Re</button>
    <button type="button" data-key="K">Kontra</button>
    <button class="save" type="button" data-action="submit">Spiel speichern</button>
  </div>
</div>
"""

_CSS = """
.score-entry { display: grid; gap: .42rem; }
button, input { font: inherit; }
.score-entry label { font-weight: 600; }
.display {
  box-sizing: border-box; width: 100%; min-height: 3rem; padding: .55rem .7rem;
  border: 1px solid var(--st-border-color); border-radius: var(--st-input-radius, .5rem);
  color: var(--st-text-color); background: var(--st-background-color); font-size: 1.15rem;
}
.display:focus { outline: 2px solid var(--st-primary-color); outline-offset: 1px; }
.name-spacer { font-size: .82rem; }
.keypad { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .42rem; }
.keypad button {
  min-height: 3.2rem; border: 1px solid var(--st-border-color);
  border-radius: var(--st-button-radius, .5rem); color: var(--st-text-color);
  background: var(--st-secondary-background-color); font-weight: 700;
}
.keypad button:active { transform: scale(.97); }
.keypad button:disabled { cursor: not-allowed; opacity: .45; }
.keypad button[aria-pressed="true"] {
  border-color:var(--st-green-color, #2e7d32); color:var(--st-green-color, #2e7d32);
}
.keypad .save {
  grid-column: 1 / -1;
}
.keypad .save[data-valid="true"] {
  --save-color:color-mix(in srgb, var(--st-green-color, #2e7d32) 68%, #000);
  grid-column: 1 / -1; color: #fff; background: var(--save-color);
  border-color: var(--save-color);
}
.keypad .save[data-valid="true"]:hover:not(:disabled) {
  --save-color:color-mix(in srgb, var(--st-green-color, #2e7d32) 58%, #000);
}
@media (max-width: 640px) {
  .score-entry {
    gap: .34rem; font-size: clamp(1.2rem, calc(1.02rem + .75vw), 1.22rem);
  }
  .score-entry label { font-size: .86em; line-height: 1.1; }
  .display {
    min-height: 2.7rem; padding: .42rem .58rem; font-size: 1em;
  }
  .name-spacer { min-height: .9rem; font-size: .84em; line-height: 1.1; }
  .keypad { gap: .38rem; }
  .keypad button {
    min-height: 2.9rem; border-radius: .45rem; white-space: nowrap;
  }
  .keypad .save { font-size: .76em; }
}
@media (max-width: 340px) {
  .score-entry { font-size: 1.15rem; }
}
"""

_JS = """
const instances = new WeakMap()

export default function (component) {
  const { parentElement, data, setTriggerValue } = component
  const input = parentElement.querySelector(".display")
  const keypad = parentElement.querySelector(".keypad")
  if (!input || !keypad) return

  let instance = instances.get(parentElement)
  if (!instance) {
    instance = {
      points: "", signs: [], party: "", bocks: 0,
      resetToken: null, submissionAck: null, submitting: false,
    }
    instances.set(parentElement, instance)
  }

  const value = () =>
    `${instance.points}${instance.signs.join("")}${instance.party}${"B".repeat(instance.bocks)}`
  const isComplete = () => {
    if (!instance.points || instance.signs.length !== 4) return false
    const plusCount = instance.signs.filter((sign) => sign === "+").length
    if (Number(instance.points) === 0) {
      return instance.party === "" && plusCount >= 1 && plusCount <= 3
    }
    if (plusCount === 1) return instance.party === "R"
    if (plusCount === 3) return instance.party === "K"
    return plusCount === 2 && (instance.party === "R" || instance.party === "K")
  }
  const isValid = () => {
    if (!isComplete()) return false
    const plusCount = instance.signs.filter((sign) => sign === "+").length
    return plusCount === 2 || BigInt(instance.points) % 3n === 0n
  }
  const render = () => {
    input.value = value()
    const isZero = Number(instance.points) === 0 && instance.points !== ""
    const plusCount = instance.signs.filter((sign) => sign === "+").length
    const soloParty = instance.signs.length === 4
      ? plusCount === 1 ? "R" : plusCount === 3 ? "K" : ""
      : ""
    const compact = window.matchMedia("(max-width: 640px)").matches
    for (const button of keypad.querySelectorAll("button")) {
      if (button.dataset.key === "R" || button.dataset.key === "K") {
        button.disabled = isZero || (soloParty !== "" && button.dataset.key !== soloParty)
        button.setAttribute("aria-pressed", String(instance.party === button.dataset.key))
      }
      if (button.dataset.action === "submit") {
        button.disabled = !isComplete() || instance.submitting
        button.dataset.valid = String(isValid())
        button.textContent = instance.submitting
          ? "Speichert…"
          : compact ? "Speichern" : "Spiel speichern"
      }
    }
  }

  if (instance.resetToken !== data.resetToken) {
    instance = {
      points: "", signs: [], party: "", bocks: 0,
      resetToken: data.resetToken, submissionAck: data.submissionAck, submitting: false,
    }
    instances.set(parentElement, instance)
  } else if (instance.submissionAck !== data.submissionAck) {
    instance.submissionAck = data.submissionAck
    instance.submitting = false
  }
  render()

  for (const button of keypad.querySelectorAll("button")) {
    button.onclick = () => {
      const action = button.dataset.action
      const key = button.dataset.key
      if (action === "backspace") {
        if (instance.bocks > 0) instance.bocks -= 1
        else if (instance.party) instance.party = ""
        else if (instance.signs.length) instance.signs.pop()
        else instance.points = instance.points.slice(0, -1)
      } else if (action === "submit") {
        if (isComplete() && !instance.submitting) {
          instance.submitting = true
          render()
          setTriggerValue("submitted", value())
        }
      } else if (key === "+" || key === "-") {
        if (instance.signs.length < 4) instance.signs.push(key)
      } else if (key === "R" || key === "K") {
        if (instance.points === "" || Number(instance.points) !== 0) instance.party = key
      } else if (key === "B") {
        instance.bocks += 1
      } else if (/^[0-9]$/.test(key ?? "")) {
        instance.points = instance.points === "0" ? key : instance.points + key
        if (Number(instance.points) === 0) instance.party = ""
      }
      render()
      input.focus()
    }
  }
}
"""

_SCORE_ENTRY_COMPONENT = st.components.v2.component(
    f"doppelkopf_score_keypad_{_COMPONENT_VERSION}",
    html=_HTML,
    css=_CSS,
    js=_JS,
)


@dataclass(frozen=True, slots=True)
class ScoreEntryResult:
    submitted: str | None


def score_entry(
    *,
    players: tuple[str, ...],
    reset_token: int,
    submission_ack: int,
    key: str,
    on_submit: Callable[[str], None] | None = None,
) -> ScoreEntryResult:
    """Render a slot-aware score keypad and return one-shot user actions."""
    component_key = f"{key}-{_COMPONENT_VERSION}"

    def handle_submit() -> None:
        if on_submit is None:
            return
        component_state = st.session_state.get(component_key)
        submitted = getattr(component_state, "submitted", None)
        if isinstance(submitted, str):
            on_submit(submitted)

    result: Any = _SCORE_ENTRY_COMPONENT(
        key=component_key,
        data={
            "players": players,
            "resetToken": reset_token,
            "submissionAck": submission_ack,
        },
        on_submitted_change=handle_submit,
    )
    return ScoreEntryResult(
        submitted=getattr(result, "submitted", None),
    )
