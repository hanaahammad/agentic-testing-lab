"""Original cartoon strip (inline SVG) telling how to use the QA agent, one panel per step.

Two characters: YOU (the tester, coral shirt) and the AGENT (a teal robot). Everything is drawn here in code,
no external images, so the page works offline and in any browser.
"""

INK = "#1f2a37"
TEAL, TEAL_D = "#2bb3a3", "#1d8a7d"
CORAL = "#f47a63"
SKIN = "#f3c9a4"
HAIR = "#3b2a22"
PAPER = "#fffdf7"
SKY = "#eaf6f4"
YELLOW = "#ffd166"
RED = "#e5484d"
GREEN = "#2fa36b"
PURPLE = "#7c5cd6"
GREY = "#d7dde4"


def robot(x, y, s=1.0, mood="happy", arm="down", flip=False):
    """The agent. (x, y) = feet centre."""
    mouth = {"happy": "M-9 -63 Q0 -55 9 -63", "think": "M-7 -60 L7 -60", "oops": "M-6 -58 Q0 -64 6 -58"}[mood]
    arms = {
        "down": f'<path d="M-24 -38 q-10 10 -8 24" stroke="{INK}" stroke-width="5" fill="none" stroke-linecap="round"/>'
                f'<path d="M24 -38 q10 10 8 24" stroke="{INK}" stroke-width="5" fill="none" stroke-linecap="round"/>',
        "up": f'<path d="M-24 -38 q-10 10 -8 24" stroke="{INK}" stroke-width="5" fill="none" stroke-linecap="round"/>'
              f'<path d="M24 -40 q14 -6 20 -22" stroke="{INK}" stroke-width="5" fill="none" stroke-linecap="round"/>'
              f'<circle cx="44" cy="-63" r="5" fill="{TEAL}" stroke="{INK}" stroke-width="2.5"/>',
        "front": f'<path d="M-24 -38 q16 6 30 4" stroke="{INK}" stroke-width="5" fill="none" stroke-linecap="round"/>'
                 f'<path d="M24 -38 q4 10 -4 16" stroke="{INK}" stroke-width="5" fill="none" stroke-linecap="round"/>',
    }[arm]
    tr = f"translate({x},{y}) scale({-s if flip else s},{s})"
    return f'''<g transform="{tr}">
  <ellipse cx="0" cy="2" rx="26" ry="5" fill="#000" opacity=".08"/>
  <rect x="-14" y="-12" width="9" height="13" rx="3" fill="{TEAL_D}" stroke="{INK}" stroke-width="2.5"/>
  <rect x="5" y="-12" width="9" height="13" rx="3" fill="{TEAL_D}" stroke="{INK}" stroke-width="2.5"/>
  {arms}
  <rect x="-24" y="-46" width="48" height="38" rx="12" fill="{TEAL}" stroke="{INK}" stroke-width="3"/>
  <circle cx="0" cy="-27" r="7" fill="{YELLOW}" stroke="{INK}" stroke-width="2.5"/>
  <path d="M-3 -27 l2.5 2.5 l4.5 -5" stroke="{INK}" stroke-width="2" fill="none" stroke-linecap="round"/>
  <line x1="0" y1="-92" x2="0" y2="-104" stroke="{INK}" stroke-width="3"/>
  <circle cx="0" cy="-107" r="5" fill="{CORAL}" stroke="{INK}" stroke-width="2.5"/>
  <rect x="-28" y="-94" width="56" height="44" rx="14" fill="{TEAL}" stroke="{INK}" stroke-width="3"/>
  <rect x="-20" y="-86" width="40" height="27" rx="9" fill="{PAPER}" stroke="{INK}" stroke-width="2.5"/>
  <circle cx="-8" cy="-74" r="4.2" fill="{INK}"/><circle cx="8" cy="-74" r="4.2" fill="{INK}"/>
  <circle cx="-6.5" cy="-75.5" r="1.3" fill="#fff"/><circle cx="9.5" cy="-75.5" r="1.3" fill="#fff"/>
  <path d="{mouth}" stroke="{INK}" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <rect x="-33" y="-79" width="6" height="14" rx="3" fill="{TEAL_D}" stroke="{INK}" stroke-width="2"/>
  <rect x="27" y="-79" width="6" height="14" rx="3" fill="{TEAL_D}" stroke="{INK}" stroke-width="2"/>
</g>'''


def person(x, y, s=1.0, arm="down", flip=False):
    """You, the tester. (x, y) = feet centre."""
    arms = {
        "down": f'<path d="M-17 -44 q-8 14 -5 28" stroke="{SKIN}" stroke-width="7" fill="none" stroke-linecap="round"/>'
                f'<path d="M17 -44 q8 14 5 28" stroke="{SKIN}" stroke-width="7" fill="none" stroke-linecap="round"/>',
        "wave": f'<path d="M-17 -44 q-8 14 -5 28" stroke="{SKIN}" stroke-width="7" fill="none" stroke-linecap="round"/>'
                f'<path d="M17 -46 q14 -8 16 -30" stroke="{SKIN}" stroke-width="7" fill="none" stroke-linecap="round"/>'
                f'<circle cx="33" cy="-79" r="6" fill="{SKIN}" stroke="{INK}" stroke-width="2"/>',
        "thumb": f'<path d="M-17 -44 q-8 14 -5 28" stroke="{SKIN}" stroke-width="7" fill="none" stroke-linecap="round"/>'
                 f'<path d="M17 -44 q14 -2 20 -12" stroke="{SKIN}" stroke-width="7" fill="none" stroke-linecap="round"/>'
                 f'<rect x="31" y="-66" width="11" height="10" rx="3" fill="{SKIN}" stroke="{INK}" stroke-width="2"/>'
                 f'<rect x="33" y="-76" width="5" height="12" rx="2.5" fill="{SKIN}" stroke="{INK}" stroke-width="2"/>',
        "point": f'<path d="M-17 -44 q-8 14 -5 28" stroke="{SKIN}" stroke-width="7" fill="none" stroke-linecap="round"/>'
                 f'<path d="M17 -44 q16 -4 30 -14" stroke="{SKIN}" stroke-width="7" fill="none" stroke-linecap="round"/>',
    }[arm]
    tr = f"translate({x},{y}) scale({-s if flip else s},{s})"
    return f'''<g transform="{tr}">
  <ellipse cx="0" cy="2" rx="24" ry="5" fill="#000" opacity=".08"/>
  <path d="M-10 -14 v14 M10 -14 v14" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>
  {arms}
  <path d="M-20 -12 Q-22 -50 0 -52 Q22 -50 20 -12 Z" fill="{CORAL}" stroke="{INK}" stroke-width="3"/>
  <circle cx="0" cy="-70" r="17" fill="{SKIN}" stroke="{INK}" stroke-width="3"/>
  <path d="M-17 -72 Q-16 -92 2 -90 Q18 -89 17 -72 Q10 -82 -2 -80 Q-12 -79 -17 -72 Z" fill="{HAIR}" stroke="{INK}" stroke-width="2.5"/>
  <circle cx="-6" cy="-68" r="2.4" fill="{INK}"/><circle cx="6" cy="-68" r="2.4" fill="{INK}"/>
  <path d="M-6 -60 Q0 -55 6 -60" stroke="{INK}" stroke-width="2.3" fill="none" stroke-linecap="round"/>
  <circle cx="-11" cy="-62" r="3" fill="{CORAL}" opacity=".35"/><circle cx="11" cy="-62" r="3" fill="{CORAL}" opacity=".35"/>
</g>'''


def bubble(x, y, w, text, tail="left", color=PAPER, size=12.5):
    """Speech bubble; (x, y) = top-left. text: str or list of lines."""
    lines = text if isinstance(text, list) else [text]
    h = 14 + 16 * len(lines)
    tx = x + 22 if tail == "left" else x + w - 22
    t = f'<path d="M{tx - 7} {y + h - 1} L{tx + (-10 if tail == "left" else 10)} {y + h + 12} L{tx + 7} {y + h - 1}" ' \
        f'fill="{color}" stroke="{INK}" stroke-width="2.5" stroke-linejoin="round"/>'
    body = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{color}" stroke="{INK}" stroke-width="2.5"/>'
    cover = f'<rect x="{tx - 6}" y="{y + h - 4}" width="12" height="4" fill="{color}"/>'
    words = "".join(f'<text x="{x + w / 2}" y="{y + 21 + 16 * i}" text-anchor="middle" font-size="{size}" '
                    f'font-weight="600" fill="{INK}">{ln}</text>' for i, ln in enumerate(lines))
    return body + t + cover + words


def _panel(inner, bg=SKY):
    return (f'<svg viewBox="0 0 320 194" xmlns="http://www.w3.org/2000/svg" role="img" '
            f'font-family="Nunito, Segoe UI, Arial, sans-serif" width="320" height="194">'
            f'<rect x="0" y="0" width="320" height="194" fill="{bg}"/>'
            f'<rect x="0" y="182" width="320" height="12" fill="#ffffff" opacity=".7"/>'
            f'<line x1="0" y1="182" x2="320" y2="182" stroke="{INK}" stroke-width="1.5" opacity=".25"/>'
            f'{inner}</svg>')


def _check(x, y, c=GREEN, r=9):
    return (f'<circle cx="{x}" cy="{y}" r="{r}" fill="{c}" stroke="{INK}" stroke-width="2"/>'
            f'<path d="M{x - 4} {y} l3 3 l5 -6" stroke="#fff" stroke-width="2.5" fill="none" stroke-linecap="round"/>')


def _cross(x, y, r=9):
    return (f'<circle cx="{x}" cy="{y}" r="{r}" fill="{RED}" stroke="{INK}" stroke-width="2"/>'
            f'<path d="M{x - 3.5} {y - 3.5} l7 7 M{x + 3.5} {y - 3.5} l-7 7" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/>')


def _bug(x, y, s=1.0):
    return f'''<g transform="translate({x},{y}) scale({s})">
  <path d="M-9 -4 l-7 -5 M9 -4 l7 -5 M-10 3 h-8 M10 3 h8 M-9 9 l-7 5 M9 9 l7 5 M-4 -10 l-4 -6 M4 -10 l4 -6"
        stroke="{INK}" stroke-width="2.2" stroke-linecap="round"/>
  <ellipse cx="0" cy="3" rx="10" ry="12" fill="{RED}" stroke="{INK}" stroke-width="2.2"/>
  <line x1="0" y1="-9" x2="0" y2="15" stroke="{INK}" stroke-width="1.6"/>
  <circle cx="-4" cy="0" r="1.8" fill="{INK}"/><circle cx="4" cy="6" r="1.8" fill="{INK}"/>
  <circle cx="0" cy="-10" r="5" fill="{INK}"/></g>'''


# ---------------------------------------------------------------- the 9 panels
def p1_setup():
    cards = ""
    for i, (label, sub, c) in enumerate((("Demo", "scripted", GREY), ("Ollama", "your PC", YELLOW),
                                         ("Claude", "API", "#c9ecff"))):
        x = 168 + i * 50
        cards += (f'<rect x="{x}" y="{96 + (0 if i != 1 else -6)}" width="44" height="54" rx="8" fill="{c}" stroke="{INK}" stroke-width="2.5"/>'
                  f'<text x="{x + 22}" y="{118 + (0 if i != 1 else -6)}" text-anchor="middle" font-size="10.5" font-weight="800" fill="{INK}">{label}</text>'
                  f'<text x="{x + 22}" y="{132 + (0 if i != 1 else -6)}" text-anchor="middle" font-size="7" fill="{INK}">{sub}</text>')
    sel = f'<rect x="215" y="86" width="52" height="68" rx="10" fill="none" stroke="{CORAL}" stroke-width="3" stroke-dasharray="5 4"/>'
    brain = (f'<text x="243" y="78" text-anchor="middle" font-size="11" font-weight="700" fill="{INK}">choose a brain</text>')
    app = (f'<rect x="20" y="20" width="118" height="44" rx="9" fill="{PAPER}" stroke="{INK}" stroke-width="2.5"/>'
           f'<text x="79" y="38" text-anchor="middle" font-size="10" fill="{INK}">App under test</text>'
           f'<text x="79" y="54" text-anchor="middle" font-size="13" font-weight="800" fill="{TEAL_D}">NileBank ▾</text>')
    return _panel(app + brain + cards + sel + person(80, 176, 1.0, "point")
                  + bubble(150, 16, 158, ["Today: NileBank,", "thinking on my PC"], tail="left"))


def p2_story():
    card = (f'<g transform="rotate(-4 205 110)"><rect x="150" y="52" width="122" height="112" rx="8" fill="{PAPER}" stroke="{INK}" stroke-width="2.5"/>'
            f'<text x="162" y="72" font-size="11" font-weight="800" fill="{CORAL}">STORY-104</text>'
            f'<text x="162" y="88" font-size="9.5" fill="{INK}">As a customer I want</text>'
            f'<text x="162" y="100" font-size="9.5" fill="{INK}">to send money…</text>'
            + "".join(f'<rect x="162" y="{112 + 14 * i}" width="16" height="10" rx="3" fill="{YELLOW}" stroke="{INK}" stroke-width="1.5"/>'
                      f'<text x="170" y="{120 + 14 * i}" text-anchor="middle" font-size="7" font-weight="800" fill="{INK}">AC{i + 1}</text>'
                      f'<rect x="184" y="{115 + 14 * i}" width="{70 - 12 * (i % 2)}" height="4" rx="2" fill="{GREY}"/>' for i in range(3))
            + '</g>')
    return _panel(card + robot(90, 176, 1.0, "think", "front")
                  + bubble(18, 14, 130, ["Reading the", "acceptance criteria"], tail="left"))


def p3_design():
    rows = "".join(f'<rect x="150" y="{60 + 26 * i}" width="150" height="20" rx="5" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>'
                   f'<text x="158" y="{74 + 26 * i}" font-size="9.5" font-weight="700" fill="{INK}">TC-104-0{i + 1}</text>'
                   f'<rect x="212" y="{68 + 26 * i}" width="{58 - 9 * i}" height="5" rx="2.5" fill="{GREY}"/>'
                   + (_check(289, 70 + 26 * i, GREEN, 7) if i < 3 else
                      f'<rect x="282" y="{63 + 26 * i}" width="14" height="14" rx="3" fill="#fff" stroke="{INK}" stroke-width="2"/>')
                   for i in range(4))
    return _panel(rows + robot(64, 176, 0.82, "happy", "front")
                  + person(122, 176, 0.92, "thumb", flip=True)
                  + bubble(150, 10, 150, ["You approve which", "tests to automate"], tail="right", color="#fff4d6"))


def p4_scripts():
    laptop = (f'<rect x="150" y="62" width="150" height="96" rx="8" fill="{INK}" stroke="{INK}" stroke-width="2.5"/>'
              f'<rect x="157" y="69" width="136" height="82" rx="4" fill="#0f1720"/>'
              f'<path d="M140 158 h170 l-10 12 h-150 z" fill="{GREY}" stroke="{INK}" stroke-width="2.5"/>')
    code = [("def", "#ff9e64", " test_tc_104_01"), ("  page.goto", "#7dcfff", '("/transfer")'),
            ("  expect", "#9ece6a", "(total)…"), ("def", "#ff9e64", " test_tc_104_02"), ("  assert", "#bb9af7", " r.status == 409")]
    lines = "".join(f'<text x="164" y="{84 + 14 * i}" font-family="Consolas, monospace" font-size="9" fill="{c}">{a}'
                    f'<tspan fill="#c0caf5">{b}</tspan></text>' for i, (a, c, b) in enumerate(code))
    shield = (f'<path d="M282 40 l16 6 v12 q0 12 -16 18 q-16 -6 -16 -18 v-12 z" fill="{GREEN}" stroke="{INK}" stroke-width="2.5"/>'
              f'<path d="M275 56 l5 5 l9 -10" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round"/>')
    return _panel(laptop + lines + shield + robot(78, 176, 1.0, "happy", "front")
                  + bubble(14, 12, 150, ["I write the scripts", "and check them first"], tail="left"))


def p5_run():
    win = (f'<rect x="132" y="34" width="172" height="134" rx="9" fill="{PAPER}" stroke="{INK}" stroke-width="2.5"/>'
           f'<rect x="132" y="34" width="172" height="20" rx="9" fill="{GREY}" stroke="{INK}" stroke-width="2.5"/>'
           f'<circle cx="145" cy="44" r="3.5" fill="{RED}"/><circle cx="156" cy="44" r="3.5" fill="{YELLOW}"/>'
           f'<circle cx="167" cy="44" r="3.5" fill="{GREEN}"/>'
           f'<text x="240" y="48" text-anchor="middle" font-size="9" fill="{INK}">NileBank · buggy build</text>')
    marks = ""
    for i, ok in enumerate((True, True, False, True, False)):
        y = 70 + 19 * i
        marks += (_check(152, y, GREEN, 7) if ok else _cross(152, y, 7)) + \
                 f'<rect x="166" y="{y - 3}" width="{110 - 14 * (i % 3)}" height="6" rx="3" fill="{GREY}"/>'
    play = (f'<circle cx="104" cy="64" r="16" fill="{CORAL}" stroke="{INK}" stroke-width="2.5"/>'
            f'<path d="M99 56 l12 8 l-12 8 z" fill="#fff"/>')
    return _panel(win + marks + play + robot(62, 176, 0.95, "happy", "up")
                  + f'<text x="20" y="30" font-size="12.5" font-weight="800" fill="{INK}">Run! UI + API tests</text>')


def p6_triage():
    bins = ""
    for i, (label, c, icon) in enumerate((("Product bug", "#ffe1e1", "bug"), ("Test bug", "#e4f3ff", "wrench"),
                                          ("Environment", "#eee8ff", "plug"))):
        x = 120 + i * 66
        bins += (f'<path d="M{x} 112 h56 l-6 60 h-44 z" fill="{c}" stroke="{INK}" stroke-width="2.5"/>'
                 f'<text x="{x + 28}" y="190" text-anchor="middle" font-size="9.5" font-weight="800" fill="{INK}">{label}</text>')
        cx, cy = x + 28, 140
        if icon == "bug":
            bins += _bug(cx, cy, 0.9)
        elif icon == "wrench":
            bins += (f'<g transform="rotate(-40 {cx} {cy})"><rect x="{cx - 3.5}" y="{cy - 4}" width="7" height="26" rx="3" fill="#9aa5b1" stroke="{INK}" stroke-width="2"/>'
                     f'<circle cx="{cx}" cy="{cy - 8}" r="9" fill="#9aa5b1" stroke="{INK}" stroke-width="2"/>'
                     f'<rect x="{cx - 3}" y="{cy - 19}" width="6" height="9" fill="{c}"/></g>')
        else:
            bins += (f'<rect x="{cx - 9}" y="{cy - 6}" width="18" height="14" rx="3" fill="#9aa5b1" stroke="{INK}" stroke-width="2"/>'
                     f'<path d="M{cx - 4} {cy - 6} v-7 M{cx + 4} {cy - 6} v-7 M{cx} {cy + 8} v8" stroke="{INK}" stroke-width="2.5" stroke-linecap="round"/>')
    fail = _cross(222, 92, 9) + f'<path d="M222 102 q0 8 -2 14" stroke="{INK}" stroke-width="2" stroke-dasharray="3 3" fill="none"/>'
    return _panel(bins + fail + robot(60, 176, 0.92, "think", "up")
                  + bubble(110, 10, 196, ["Why did it fail? A test bug", "I repair myself, then re-run"], tail="left"))


def p7_issues():
    card = (f'<rect x="138" y="52" width="166" height="92" rx="10" fill="{PAPER}" stroke="{INK}" stroke-width="2.5"/>'
            f'<circle cx="155" cy="72" r="7" fill="none" stroke="{GREEN}" stroke-width="3"/><circle cx="155" cy="72" r="2.5" fill="{GREEN}"/>'
            f'<text x="168" y="76" font-size="10.5" font-weight="800" fill="{INK}">#13 Daily limit not</text>'
            f'<text x="168" y="89" font-size="10.5" font-weight="800" fill="{INK}">cumulative (AC2)</text>'
            f'<rect x="152" y="100" width="40" height="13" rx="6.5" fill="#ffe1e1" stroke="{RED}" stroke-width="1.5"/>'
            f'<text x="172" y="110" text-anchor="middle" font-size="8" font-weight="800" fill="{RED}">critical</text>'
            f'<rect x="197" y="100" width="62" height="13" rx="6.5" fill="#e4f3ff" stroke="#3d7bd9" stroke-width="1.5"/>'
            f'<text x="228" y="110" text-anchor="middle" font-size="8" font-weight="800" fill="#3d7bd9">agent-found</text>'
            f'<rect x="152" y="121" width="128" height="5" rx="2.5" fill="{GREY}"/><rect x="152" y="131" width="96" height="5" rx="2.5" fill="{GREY}"/>')
    later = (f'<text x="221" y="164" text-anchor="middle" font-size="10" font-weight="700" fill="{PURPLE}">fixed → closed by the agent</text>')
    return _panel(card + later + _bug(268, 40, 0.8) + robot(70, 176, 0.95, "happy", "front")
                  + bubble(12, 14, 120, ["Bug filed with", "steps &amp; evidence"], tail="left"))


def p8_explore():
    win = (f'<rect x="20" y="40" width="170" height="124" rx="9" fill="{PAPER}" stroke="{INK}" stroke-width="2.5"/>'
           f'<rect x="20" y="40" width="170" height="20" rx="9" fill="{GREY}" stroke="{INK}" stroke-width="2.5"/>'
           f'<text x="105" y="54" text-anchor="middle" font-size="9" fill="{INK}">/beneficiaries</text>'
           f'<rect x="34" y="72" width="100" height="14" rx="4" fill="#fff" stroke="{INK}" stroke-width="1.8"/>'
           f'<text x="40" y="82" font-family="Consolas, monospace" font-size="8" fill="{RED}">&lt;b&gt;hi&lt;/b&gt;</text>'
           f'<rect x="34" y="94" width="60" height="16" rx="5" fill="{TEAL}" stroke="{INK}" stroke-width="1.8"/>'
           f'<text x="64" y="105" text-anchor="middle" font-size="8.5" font-weight="800" fill="#fff">Save</text>'
           f'<path d="M86 106 l0 16 l4 -4 l4 8 l3 -1.5 l-4 -8 l6 0 z" fill="#fff" stroke="{INK}" stroke-width="1.8"/>'
           f'<rect x="34" y="122" width="120" height="5" rx="2.5" fill="{GREY}"/><rect x="34" y="132" width="90" height="5" rx="2.5" fill="{GREY}"/>')
    glass = (f'<circle cx="214" cy="112" r="14" fill="#ffffff" fill-opacity=".6" stroke="{INK}" stroke-width="3"/>'
             f'<line x1="224" y1="122" x2="234" y2="132" stroke="{INK}" stroke-width="5" stroke-linecap="round"/>')
    return _panel(win + glass + robot(258, 176, 0.92, "happy", "front", flip=True)
                  + bubble(196, 8, 118, ["No script: I click", "and try things"], tail="right", size=11.5))


def p9_artifacts():
    shelf = f'<rect x="136" y="150" width="172" height="8" rx="3" fill="#b98a5e" stroke="{INK}" stroke-width="2.5"/>'
    boxes = ""
    for i, (v, c) in enumerate((("v001", "#ffe1e1"), ("v002", "#fff4d6"), ("v003", "#dff5e8"))):
        x = 142 + i * 56
        boxes += (f'<rect x="{x}" y="96" width="48" height="54" rx="6" fill="{c}" stroke="{INK}" stroke-width="2.5"/>'
                  f'<rect x="{x}" y="96" width="48" height="12" rx="6" fill="#fff" stroke="{INK}" stroke-width="2.5"/>'
                  f'<text x="{x + 24}" y="132" text-anchor="middle" font-size="12" font-weight="800" fill="{INK}">{v}</text>')
    git = (f'<path d="M150 70 H290" stroke="{INK}" stroke-width="3"/>'
           + "".join(f'<circle cx="{166 + 56 * i}" cy="70" r="7" fill="{[CORAL, YELLOW, GREEN][i]}" stroke="{INK}" stroke-width="2.5"/>'
                     for i in range(3))
           + f'<text x="296" y="74" font-size="10" font-weight="800" fill="{INK}">git</text>')
    return _panel(shelf + boxes + git + person(70, 176, 0.95, "wave")
                  + bubble(12, 14, 150, ["Every run is kept,", "nothing overwritten"], tail="left"))


PANELS = [
    ("Set up", "You pick the application and the agent's brain: Demo (free, scripted), Ollama (a model on your PC) "
               "or Claude.", p1_setup, None),
    ("Pick a story", "The agent reads the user story and its acceptance criteria, then walks through the app's "
                     "screens and API like a tester on day one.", p2_story, "stories"),
    ("Design & approve", "It proposes test cases for every criterion. You tick the ones worth automating: the "
                         "human gate.", p3_design, "design"),
    ("Write scripts", "It writes the pytest + Playwright script and checks it (syntax, one test per case, "
                      "no made-up fixtures or numbers) before anything runs.", p4_scripts, "scripts"),
    ("Run", "The tests run against the app, through the screens in a real browser and through the API.", p5_run, "run"),
    ("Triage", "Every failure is sorted: product bug, test bug (the agent repairs its own script) or "
               "environment.", p6_triage, "triage"),
    ("File issues", "Product bugs become issues with steps and evidence; the agent closes them when the fix "
                    "makes the test pass.", p7_issues, "issues"),
    ("Explore live", "No script at all: the agent drives the browser, tries things a customer would, and "
                     "records what breaks.", p8_explore, "explore"),
    ("Keep the evidence", "Each run is saved as a new version (cases, script, results, triage, screenshots) and "
                          "can be committed to git.", p9_artifacts, "artifacts"),
]


def hero():
    """Wide banner: you and the agent side by side."""
    return (f'<svg viewBox="0 0 640 210" xmlns="http://www.w3.org/2000/svg" font-family="Nunito, Segoe UI, Arial, sans-serif" '
            f'width="640" height="210">'
            f'<rect width="640" height="210" rx="18" fill="{SKY}"/>'
            f'<circle cx="560" cy="40" r="60" fill="{YELLOW}" opacity=".35"/><circle cx="70" cy="190" r="70" fill="{TEAL}" opacity=".12"/>'
            f'<rect x="0" y="172" width="640" height="38" fill="#fff" opacity=".7"/>'
            + person(250, 178, 1.15, "wave")
            + robot(390, 178, 1.15, "happy", "up", flip=True)
            + bubble(40, 26, 170, ["I decide what", "matters &amp; approve"], tail="right", color="#fff4d6", size=13.5)
            + bubble(440, 26, 170, ["I design, write, run", "and triage the tests"], tail="left", size=13.5)
            + _bug(320, 70, 1.1)
            + f'<path d="M300 92 q-14 -20 -6 -40 M340 92 q14 -20 6 -40" stroke="{INK}" stroke-width="2" stroke-dasharray="3 4" fill="none" opacity=".5"/>'
            + '</svg>')
