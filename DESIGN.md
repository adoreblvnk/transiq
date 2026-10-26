---
name: TRANSIQ
description: Technical Editorial Brutalism Design System for Singapore Sheltered Transit Engine
colors:
  paper: "#F8F9FA"
  surface: "#FFFFFF"
  surface-subtle: "#F1F3F5"
  surface-hover: "#E9ECEF"
  surface-active: "#DEE2E6"
  ink: "#111827"
  ink-muted: "#374151"
  ink-faint: "#6B7280"
  border: "#111827"
  border-subtle: "#D1D5DB"
  signal: "#9A3412"
  shelter: "#0F6738"
  shelter-bg: "#DCFCE7"
  rain: "#854D0E"
  rain-bg: "#FEF3C7"
  crowd: "#991B1B"
  crowd-bg: "#FEE2E2"
  transit: "#1D4ED8"
  transit-bg: "#DBEAFE"
typography:
  kpi:
    fontFamily: "IBM Plex Mono, monospace"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.2
  display:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.2
  title:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1.3
  lead:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  mono:
    fontFamily: "IBM Plex Mono, monospace"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.4
  micro:
    fontFamily: "IBM Plex Mono, monospace"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.3
rounded:
  none: "0px"
  sm: "2px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-brutal:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "6px 14px"
  button-primary:
    backgroundColor: "{colors.signal}"
    textColor: "#FFFFFF"
    rounded: "{rounded.sm}"
    padding: "6px 14px"
  card-active:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "12px 14px"
---

# Design System: TRANSIQ

## Overview

**Creative North Star: "The Technical Operations Blueprint"**

TRANSIQ is an authoritative transit operations console designed for Singapore's tropical urban environment. Rather than looking like a generic AI dashboard, a consumer social app, or a standard corporate template, TRANSIQ evokes an authentic architectural and transit engineering drafting tool: visible structural grid lines, crisp 2px ink borders, high-contrast monospace metadata, and tactile offset drop shadows.

The interface prioritizes scanability, spatial clarity, and functional honesty over decorative distraction. Structure itself is the decoration. Every visual element maps directly to an authentic Singapore transit dataset (LTA DataMall, Data.gov.sg, Singapore Land Authority OneMap).

**Key Characteristics:**
- **Permanent High-Contrast Light Editorial Palette**: Pure white surface panels resting on off-white technical drafting paper (`#F8F9FA`) with pitch charcoal ink (`#111827`).
- **Squared Geometry**: Crisp 2px corners (`--radius: 2px`) and hard 1.5px/2px solid borders throughout.
- **Dual-Font System**: `IBM Plex Sans` for readable interface text paired with `IBM Plex Mono` for stop codes, timestamps, query latencies, and tabular metrics.
- **100vh Single-Page Dashboard Architecture**: Fixed-height viewport with pinned top controls, independent directions scrolling, and an unscrollable, persistent Leaflet map canvas.

---

## Colors

The palette is rooted in technical architectural drafting with high-contrast semantic signals meeting WCAG 2.2 AA standards ($\ge 4.5:1$ contrast against light surfaces).

### Primary & Accent
- **Deep Rust Vermilion** (`#9A3412`): Primary operational signal for active CTA buttons, active focus rings, and high-visibility map waypoints ($5.8:1$ contrast on white).
- **Safety Vermilion Hover** (`#7C2D12`): Darker interactive hover state for buttons.
- **Warm Vermilion Subtle** (`#FFEDD5`): Soft accent surface tint.

### Data Semantic Signals
- **Forest Green Shelter** (`#0F6738`): Denotes covered linkways, 100% sheltered walkways, and available seating (`#DCFCE7` background). Contrast: $5.2:1$ on light green, $6.5:1$ on white.
- **Amber Exposure** (`#854D0E`): Denotes unsheltered street walking and moderate transit crowding (`#FEF3C7` background).
- **Crimson Crowd** (`#991B1B`): Denotes crush-load (`LSD`) transit legs and peak platform crowding (`#FEE2E2` background).
- **Royal Transit Blue** (`#1D4ED8`): Denotes scheduled public bus and MRT transit rides (`#DBEAFE` background).

### Neutral & Surfaces
- **Drafting Paper** (`#F8F9FA`): Page baseline background with subtle $24\text{px}$ drafting grid dots.
- **Panel Surface** (`#FFFFFF`): Primary foreground containers and cards.
- **Subtle Surface** (`#F1F3F5`): Secondary panels, table headers, and inactive buttons.
- **Hover Surface** (`#E9ECEF`): Interactive hover feedback state.
- **Hard Ink** (`#111827`): Deep pitch charcoal for typography, headings, and high-contrast borders.
- **Muted Ink** (`#374151`): Secondary metadata, field labels, and descriptions.
- **Faint Ink** (`#6B7280`): Placeholders, disabled states, and auxiliary legends.

---

## Typography

The typography pairing uses **IBM Plex Sans** for clear legibility and **IBM Plex Mono** for technical metadata and tabular figures.

- **Display Font**: IBM Plex Sans, sans-serif
- **Mono Font**: IBM Plex Mono, monospace

### Scale Ramp
- **Display** (`20px`, bold, line-height 1.2): Main view titles and prominent KPI values.
- **Title** (`18px`, bold, line-height 1.3): Card titles and section headers.
- **Lead** (`16px`, semi-bold, line-height 1.4): Active journey duration, modal titles.
- **Body** (`14px`, regular, line-height 1.5): Standard directions, table cells, form inputs.
- **Sub** (`13px`, medium, line-height 1.4): Step descriptions, secondary metadata, dropdown options.
- **Micro** (`12px`, bold/semi-bold, line-height 1.3): Status tags, mode pills, axis marks, telemetry labels. *Strict quality floor: zero functional text below 12px.*

---

## Layout

- **Single-Page Architecture**: Fixed `100vh` viewport (`html, body { height: 100vh; overflow: hidden; }`).
- **Sidebar Split**:
  - **Top Pinned Controls**: Origin, Destination, Swap button, Mode bar, and Active Route Card stay permanently pinned at the top. They never scroll out of view.
  - **Lower Independent Scroll**: The Routes (Directions) list is housed in a dedicated flex container (`.itinerary-scroll`) that scrolls internally.
- **Persistent Map Pane**: Fills 100% height and width. Zoom controls are pinned at `bottomleft` to eliminate overlap with top-left route telemetry.

---

## Elevation & Depth

TRANSIQ enforces a **flat-by-default, hard-offset elevation philosophy**.
- **Zero Blurry Shadows**: All 25px diffuse, fuzzy drop shadows are banned.
- **Neobrutalist Drop Shadow**: Depth is communicated exclusively via solid 2px offset shadows:
  ```css
  box-shadow: 2px 2px 0 var(--border);
  ```
- **Active State Elevation**:
  ```css
  box-shadow: 3px 3px 0 var(--border);
  transform: translate(-1px, -1px);
  ```

---

## Shapes

- **Corner Radius**: Fixed 2px squared geometry (`--radius: 2px`).
- **Borders**: 2px solid ink borders on major panels, cards, and input wrappers (`border: 2px solid var(--border)`).
- **Prohibitions**: Zero rounded pill containers, zero pill buttons, zero circular cards.

---

## Components

### 1. Form Inputs (`.field-input-wrap`)
- A single, unified 42px high container enclosing the location pin icon, text field, and clear button.
- The inner `<input>` has `border: none; outline: none;` to eliminate double-box border collisions.
- Focus is applied strictly to the outer wrapper with a 2px rust outline and offset shadow.

### 2. Custom Brutalist Dropdowns (`.custom-select`)
- Replaces native unstyled OS selects with custom-themed components.
- Structured trigger button with down-arrow chevron (`▼`), hover feedback, and a solid 2px-bordered popup menu with keyboard navigation.

### 3. Single Active Route Card (`.active-route-card`)
- Replaces confusing multi-card stacks with one definitive card displaying the chosen mode's optimal route.
- Displays mode badge, journey time in large monospace, shelter percentage, plain-English seat availability, and transfer count.
- Includes a proportional journey composition bar segmenting walking, transit, and open exposure.

### 4. LayerCake-Inspired Visualizations
- Pure responsive SVG graphics (`viewBox="0 0 800 220"`).
- Congestion View: Hourly volume columns with overlaid 3-hour moving average line.
- Benchmarks View: Horizontal bar comparison chart (Optimized Dual-DB Engine vs Naive SQL Baseline) without numbered category prefixes.

### 5. Toast Notifications (`#toast`)
- Non-intrusive 40px toast notification in the bottom right corner for background operations (e.g. materialized view refresh), auto-dismissing after 3.5 seconds.

---

## Do's and Don'ts

### Do:
- **Do** format transit duration $\ge 60\text{ min}$ as hours and minutes (e.g. `1 hr 20 mins`).
- **Do** use plain English for crowding states (`Seats Available`, `Standing Room`, `Crowded`).
- **Do** display distances in meters below 1,000m and kilometers above 1,000m (`1.5 km`).
- **Do** pin sidebar controls at the top so the active route is never scrolled off-screen.
- **Do** keep Leaflet zoom controls in `bottomleft` to prevent telemetry collisions.

### Don't:
- **Don't** use diffuse fuzzy box shadows (`box-shadow: 0 10px 25px rgba(...)`).
- **Don't** use rounded pill buttons or circular cards (`border-radius: 9999px`).
- **Don't** display flight/graph jargon like "legs"; use "transfers" and "steps".
- **Don't** mention internal software libraries (e.g. "LayerCake") in user-facing subtitles.
- **Don't** prepend numbered prefixes (`1.`, `2.`, `3.`) to category labels in chart axes.
- **Don't** repeat duration twice on the same direction row.
- **Don't** add decorative pulsing animations to static status badges.
