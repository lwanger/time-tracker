---
marp: true
title: Timer App UI Framework Recommendation
author: Leonard Wanger
paginate: true
---

# Choosing a UI Framework for the Time Tracker Timer

A short, standalone time-tracking app for `time-tracker`

**Goal:** recommend a GUI toolkit for a small single-window timer that shares the
existing `.env` config and time-log CSV.

Leonard Wanger — 2026

---

## What we are building

A tiny desktop utility — *not* a large application:

- One window: client dropdown, elapsed-time readout, Start/Stop, a notes field.
- Launched from the command line; pre-fillable via CLI flags.
- Appends a single row to the shared time-log CSV.

The framework choice should match this modest scope. We do **not** need mobile
targets, theming engines, or a web runtime.

---

## Evaluation criteria

Per the project requirements (`TODO.md`), ranked by importance here:

1. **Low dependencies** — the project deliberately keeps its dependency tree
   small (`uv`, a handful of packages). New runtime weight is the biggest cost.
2. **Cross-platform** — should run on Windows, macOS, and Linux.
3. **Aesthetics** — does the UI look modern and clean?
4. **Native-widget conformance** — do controls match the host OS look & feel?

---

## Candidates

| Framework | Language | Underlying tech |
| --- | --- | --- |
| **tkinter** | Python (stdlib) | Tcl/Tk |
| **Flet** | Python | Flutter engine |
| **Toga** (BeeWare) | Python | Native OS widgets |
| **PySide6 / Qt** | Python | Qt |
| **JavaScript** (Electron / pywebview) | JS + Python | Chromium / system webview |

---

## tkinter

**Tcl/Tk, shipped in the Python standard library.**

- ✅ **Zero new dependencies** — already present with Python.
- ✅ Cross-platform (Windows, macOS, Linux).
- ✅ Tiny footprint; instant startup.
- ✅ `ttk` themed widgets are acceptably native-ish on Windows/macOS.
- ⚠️ Aesthetics are dated out of the box; not as slick as Flutter/Qt.
- ⚠️ Not *truly* native widgets (Tk-drawn), though close enough for a utility.

**Best fit for a small, dependency-light tool.**

---

## Flet

**Flutter, driven from Python.**

- ✅ Beautiful, modern Material Design UI.
- ✅ Cross-platform, even web and mobile targets.
- ✅ Pleasant, reactive Python API.
- ❌ **Heavy dependency** — bundles the Flutter engine (tens of MB).
- ❌ Non-native look on *every* platform (Material everywhere).
- ❌ Overkill for a one-window timer.

---

## Toga (BeeWare)

**Real native OS widgets from Python.**

- ✅ **Truly native** controls per platform — best native conformance.
- ✅ Cross-platform by design.
- ⚠️ Adds a dependency (plus per-platform backends).
- ⚠️ Less mature; rougher edges and packaging quirks, notably on Windows.
- ⚠️ Smaller community and documentation base.

---

## PySide6 / Qt

**The Qt framework with official Python bindings.**

- ✅ Polished, professional widgets; excellent aesthetics.
- ✅ Near-native appearance and a deep widget set.
- ✅ Mature, very well documented.
- ❌ **Large dependency** (~tens of MB).
- ❌ LGPL/commercial licensing to keep in mind.
- ❌ Far more capability than a timer needs.

---

## JavaScript (Electron / pywebview)

**An HTML/CSS/JS front end in a browser runtime.**

- ✅ Ultimate styling flexibility; modern look.
- ✅ Huge ecosystem.
- ❌ **Heaviest option** — Electron bundles Chromium; pywebview adds a JS/Python
  bridge and a second language to the codebase.
- ❌ Non-native widgets (HTML controls).
- ❌ Largest build/runtime footprint and most moving parts.

---

## Decision matrix

Scores: ★★★ best, ★ worst, for *this* small-utility use case.

| Criterion (weight) | tkinter | Flet | Toga | PySide6 | JS |
| --- | :--: | :--: | :--: | :--: | :--: |
| Low dependencies (×3) | ★★★ | ★ | ★★ | ★ | ★ |
| Cross-platform (×2) | ★★★ | ★★★ | ★★★ | ★★★ | ★★★ |
| Aesthetics (×1) | ★★ | ★★★ | ★★ | ★★★ | ★★★ |
| Native conformance (×1) | ★★ | ★ | ★★★ | ★★ | ★ |
| **Weighted total** | **20** | **14** | **17** | **15** | **13** |

*(★★★=3, ★★=2, ★=1; weighted sum.)*

---

## Recommendation: **tkinter**

For a small, single-window timer it wins where it matters most for this project:

- **No new dependencies** — it is already in the standard library, honoring the
  project's "keep dependencies low" priority.
- **Cross-platform** and trivially packaged.
- **Fast** to start and to build.
- `ttk` themed widgets give a clean-enough, near-native look.

The richer toolkits (Flet, PySide6, Electron) buy aesthetics we do not need at
the cost of dependency weight; Toga's native widgets are appealing but add
dependency and maturity risk for little gain at this scale.

---

# Decision: build the timer with **tkinter + ttk**

Next step: implement `timer_app.py`.
