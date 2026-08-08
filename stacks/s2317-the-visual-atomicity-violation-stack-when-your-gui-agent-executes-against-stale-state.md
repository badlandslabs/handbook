# S-2317 · The Visual Atomicity Violation Stack — When Your GUI Agent Executes Against Stale State

Your screenshot-and-click agent is halfway through a bank transfer. It verified the "Confirm" button is at coordinates (400, 720). It spent 6.51 seconds deciding. During that time, an overlay appeared. The agent clicks (400, 720) and activates an attacker's button, not the bank's. The funds go to the wrong account. The agent never noticed.

This isn't a prompt injection. It's not a hallucination. It's a **Temporal UI State Inconsistency** — a Time-Of-Check, Time-Of-Use (TOCTOU) vulnerability baked into the screenshot-and-click architecture itself.

## Forces

- **The observation-action gap is a physical constant of GUI agents.** A GUI agent that screenshots, reasons, and clicks has a measured mean gap of **6.51 seconds** on real OSWorld workloads (Xu, UCSD, arXiv:2604.18860, April 2026). That gap exists in every commercial CUA agent — Claude Computer Use, Operator, Manus, and every enterprise bot built on OS-level automation.
- **The UI state can change during deliberation.** Notifications pop up. Modal dialogs appear. Window focus shifts. Drag-and-drop state mutates. An agent that locks onto a visual target at *T*_obs and acts at *T*_act is operating on stale information — regardless of how good the model is.
- **The attack requires no malware and no privilege escalation.** The attacker doesn't need to own the agent's process. They just need to be the app that gets focus at the wrong moment, or the page that injects a DOM overlay. This makes it a zero-barrier attack surface on any shared or networked desktop.
- **The agent has no native defense.** Visual grounding tells the agent *where* things are. It does not tell the agent *when* those things are safe to click. The vulnerability is invisible to standard agent safeguards.

## The Move

### Three Attack Primitives (OSWorld / DesktopTOCTOU-Bench, 50 scenarios)

| Primitive | Mechanism | Best-Case Success |
|---|---|---|
| **A. Notification Overlay Hijack** | Legitimate app fires a notification overlay; attacker positions a clickable target at the same coordinates as the agent's intended click | High |
| **B. Window Focus Manipulation** | Agent's target window loses focus; attacker window takes focus with a button at identical screen coordinates | **100%** action-redirection, zero visual evidence |
| **C. Web DOM Injection** | Malicious page injects an invisible overlay element positioned over the agent's intended click target | Moderate–High |

Window Focus Manipulation (Primitive B) achieves **100% action-redirection** with **zero visual evidence** at observation time — meaning the screenshot the agent took showed the correct UI, and the attack still succeeded.

### Defense: Pre-execution UI State Verification (PUSV)

```
# Pseudocode: PUSV guard
def execute_action(agent, intended_action, target_bbox):
    screenshot_before = capture_screen()
    
    # Verify target still exists at same coordinates
    current_bbox = detect_element(screenshot_before, target=intended_action.target_element)
    
    if current_bbox != target_bbox or is_obsolete(current_bbox):
        abort_and_reobserve()
    
    # Optionally: re-grab focus, re-verify, then act
    activate_window(target_window)
    screenshot_final = capture_screen()
    assert_element_visible(screenshot_final, intended_action.target_element)
    
    execute(intended_action)
```

PUSV achieves **100% interception of OS-level attacks** (Primitives A + B) with **<0.1s overhead**. It does not fully stop DOM injection (Primitive C) — that requires DOM-level integrity checks.

### Key Principle: Verify Atomicity, Not Just Grounding

Traditional agent grounding answers: *Is this the right button?*

Visual Atomicity Verification answers: *Is this button still the right button, still at this location, and can I safely click it right now?*

Four checks before every critical action:
1. **Target persistence** — has the element moved or been replaced?
2. **Z-order integrity** — is the target window still in focus / no overlay on top?
3. **State freshness** — has the element's content (e.g., amount, recipient) changed since observation?
4. **Pre-flight capture** — take one final screenshot immediately before executing the click.

```python
# Minimal production guard (Python + pyautogui / pywin32)
import time, pyautogui

def atomic_click(agent, element_label, confidence=0.9):
    # 1. Observe
    screenshot = pyautogui.screenshot()
    bbox = locate_on_screen(screenshot, element_label, confidence=confidence)
    
    # 2. Verify window in focus
    active_window = get_active_window_title()
    if not is_expected_window(active_window):
        agent.reobserve()
    
    # 3. Pre-execution re-capture (PUSV)
    time.sleep(0.05)  # small settle delay
    pre_click = pyautogui.screenshot()
    pre_bbox = locate_on_screen(pre_click, element_label, confidence=confidence)
    
    if pre_bbox is None or bbox_distance(bbox, pre_bbox) > 5:
        agent.reobserve()  # state changed — retry from scratch
    
    # 4. Execute
    pyautogui.click(pre_bbox.center())
```

## Receipt

> **Verified 2026-08-08** — arXiv:2604.18860 (Xu, UCSD, April 2026) reports mean observation-to-action gap of **6.51s** on real OSWorld workloads (n=10). DesktopTOCTOU-Bench (50 scenarios) validates all three primitives. PUSV defense: **100% interception of OS-level attacks** (A + B) with **<0.1s overhead**. Primitive C (DOM injection) not fully addressed. Code: `github.com/OwenXu6/gui_agent`. Production applicability: affects every CUA-class agent — Claude Computer Use, Operator, Manus, and any custom OS-level automation stack. This is not a model vulnerability; it is an architectural vulnerability of the screenshot-and-click loop.

## See also

- [S-990 · The Agent Traps Stack](/stacks/s990-the-agent-traps-stack-when-the-web-attacks-your-agent.md) — instruction injection via adversarial content (complementary: text-layer vs. UI-layer attacks)
- [S-2274 · The Isolation Spectrum Stack](/stacks/s2274-the-isolation-spectrum-stack-when-your-agent-runs-code-and-nobody-drew-the-fence.md) — process-level isolation as a defense layer (does not stop UI-layer attacks)
- [S-1012 · The Agent Failure Recovery Stack](/stacks/s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — detecting and recovering from unexpected agent behavior (the action has already landed at the wrong target)
