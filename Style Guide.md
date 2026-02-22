# Vox — UI Style Guidelines

## Philosophy

Vox's interface is utilitarian, dense, and terminal-inspired. It uses the Catppuccin color system — a community-driven pastel palette designed for readability and warmth across light and dark contexts. Four flavors give users a choice of contrast levels without sacrificing the cohesive, tool-like aesthetic.

**Core principles:**

- Soothing, not sterile. Catppuccin's pastel tones keep the interface warm without being distracting.
- Terminal DNA. Monospace typography, tight spacing, text-symbol icons, minimal chrome.
- Distinct by color. Roles, statuses, and interactive elements use different hues from the palette — not intensity tiers of a single hue. This ensures accessibility by default.
- Four flavors, one design. The layout, typography, spacing, and components are identical across all four flavors. Only colors change.

---

## Color System

### Catppuccin Palette

Vox uses the Catppuccin color system (MIT licensed). Each flavor provides 26 named colors. The four flavors are:

| Flavor | Type | Vibe |
|---|---|---|
| **Mocha** | Dark (deepest) | The original — cozy, color-rich accents on near-black |
| **Macchiato** | Dark (medium) | Gentle colors, soothing atmosphere |
| **Frappé** | Dark (lightest) | Subdued, muted aesthetic |
| **Latte** | Light | Inverted — dark text on light backgrounds |

### Full Palette Reference

**Accent Colors:**

| Name | Latte | Frappé | Macchiato | Mocha |
|---|---|---|---|---|
| Rosewater | `#dc8a78` | `#f2d5cf` | `#f4dbd6` | `#f5e0dc` |
| Flamingo | `#dd7878` | `#eebebe` | `#f0c6c6` | `#f2cdcd` |
| Pink | `#ea76cb` | `#f4b8e4` | `#f5bde6` | `#f5c2e7` |
| Mauve | `#8839ef` | `#ca9ee6` | `#c6a0f6` | `#cba6f7` |
| Red | `#d20f39` | `#e78284` | `#ed8796` | `#f38ba8` |
| Maroon | `#e64553` | `#ea999c` | `#ee99a0` | `#eba0ac` |
| Peach | `#fe640b` | `#ef9f76` | `#f5a97f` | `#fab387` |
| Yellow | `#df8e1d` | `#e5c890` | `#eed49f` | `#f9e2af` |
| Green | `#40a02b` | `#a6d189` | `#a6da95` | `#a6e3a1` |
| Teal | `#179299` | `#81c8be` | `#8bd5ca` | `#94e2d5` |
| Sky | `#04a5e5` | `#99d1db` | `#91d7e3` | `#89dceb` |
| Sapphire | `#209fb5` | `#85c1dc` | `#7dc4e4` | `#74c7ec` |
| Blue | `#1e66f5` | `#8caaee` | `#8aadf4` | `#89b4fa` |
| Lavender | `#7287fd` | `#babbf1` | `#b7bdf8` | `#b4befe` |

**Text Colors:**

| Name | Latte | Frappé | Macchiato | Mocha |
|---|---|---|---|---|
| Text | `#4c4f69` | `#c6d0f5` | `#cad3f5` | `#cdd6f4` |
| Subtext 1 | `#5c5f77` | `#b5bfe2` | `#b8c0e0` | `#bac2de` |
| Subtext 0 | `#6c6f85` | `#a5adce` | `#a5adcb` | `#a6adc8` |

**Overlay Colors:**

| Name | Latte | Frappé | Macchiato | Mocha |
|---|---|---|---|---|
| Overlay 2 | `#7c7f93` | `#949cbb` | `#939ab7` | `#9399b2` |
| Overlay 1 | `#8c8fa1` | `#838ba7` | `#8087a2` | `#7f849c` |
| Overlay 0 | `#9ca0b0` | `#737994` | `#6e738d` | `#6c7086` |

**Surface & Background Colors:**

| Name | Latte | Frappé | Macchiato | Mocha |
|---|---|---|---|---|
| Surface 2 | `#acb0be` | `#626880` | `#5b6078` | `#585b70` |
| Surface 1 | `#bcc0cc` | `#51576d` | `#494d64` | `#45475a` |
| Surface 0 | `#ccd0da` | `#414559` | `#363a4f` | `#313244` |
| Base | `#eff1f5` | `#303446` | `#24273a` | `#1e1e2e` |
| Mantle | `#e6e9ef` | `#292c3c` | `#1e2030` | `#181825` |
| Crust | `#dce0e8` | `#232634` | `#181926` | `#11111b` |

### Token Mapping

Vox maps Catppuccin's named colors to semantic UI tokens. This mapping is the same for all four flavors — only the underlying hex values change.

**Backgrounds:**

| Vox Token | Catppuccin Color | Usage |
|---|---|---|
| `bg_deep` | Crust | Deepest background, server strip |
| `bg_main` | Base | Primary content area, chat messages |
| `bg_panel` | Mantle | Sidebars, voice tiles, dialogs |
| `bg_input` | Crust | Input fields, code blocks |
| `bg_hover` | Surface 0 | Hover state for interactive elements |
| `bg_active` | Surface 1 | Active/selected state |

**Borders:**

| Vox Token | Catppuccin Color | Usage |
|---|---|---|
| `border` | Surface 0 | Default borders between panels |
| `border_bright` | Surface 1 | Hover/focus borders |

**Text:**

| Vox Token | Catppuccin Color | Usage |
|---|---|---|
| `text_primary` | Text | Main body text, messages |
| `text_secondary` | Subtext 0 | Labels, metadata, inactive items |
| `text_dim` | Overlay 0 | Timestamps, placeholders, disabled text |

**Accent & Interactive:**

| Vox Token | Catppuccin Color | Usage |
|---|---|---|
| `accent` | Mauve | Primary accent — active channel, badges, links |
| `accent_dim` | Surface 2 | Accent backgrounds, toggle fills |
| `accent_bright` | Lavender | Brightest accent — selected items, highlights |

**Roles:**

| Vox Token | Catppuccin Color | Usage |
|---|---|---|
| `role_admin` | Red | Admin / Owner |
| `role_mod` | Peach | Moderator |
| `role_dev` | Blue | Developer / Trusted |
| `role_member` | Subtext 1 | Member / Default |

Each role uses a distinct hue from the palette. This eliminates the contrast issues of the single-hue intensity approach — every role is visually distinct regardless of flavor.

**Status (functional):**

| Vox Token | Catppuccin Color | Usage |
|---|---|---|
| `status_success` | Green | Connected, speaking, online |
| `status_danger` | Red | Muted, error, disconnect |
| `status_warning` | Yellow | Degraded connection, warning |
| `status_idle` | Overlay 1 | User idle |
| `status_offline` | Surface 2 | User offline |

**Code & Syntax:**

| Element | Catppuccin Color |
|---|---|
| Inline code text | Green |
| Inline code background | Crust |
| Code block background | Crust |
| Code block border | Surface 0 |

### Palette Loading (Pseudocode)

```
struct Palette {
    // Backgrounds
    bg_deep, bg_main, bg_panel, bg_input, bg_hover, bg_active: Color
    // Borders
    border, border_bright: Color
    // Text
    text_primary, text_secondary, text_dim: Color
    // Accent
    accent, accent_dim, accent_bright: Color
    // Roles
    role_admin, role_mod, role_dev, role_member: Color
    // Status
    status_success, status_danger, status_warning, status_idle, status_offline: Color
}

function load_palette(flavor: "mocha" | "macchiato" | "frappe" | "latte") -> Palette:
    c = catppuccin.get_flavor(flavor).colors

    return Palette {
        bg_deep:     c.crust,
        bg_main:     c.base,
        bg_panel:    c.mantle,
        bg_input:    c.crust,
        bg_hover:    c.surface0,
        bg_active:   c.surface1,
        border:      c.surface0,
        border_bright: c.surface1,
        text_primary:   c.text,
        text_secondary: c.subtext0,
        text_dim:       c.overlay0,
        accent:       c.mauve,
        accent_dim:   c.surface2,
        accent_bright: c.lavender,
        role_admin:  c.red,
        role_mod:    c.peach,
        role_dev:    c.blue,
        role_member: c.subtext1,
        status_success: c.green,
        status_danger:  c.red,
        status_warning: c.yellow,
        status_idle:    c.overlay1,
        status_offline: c.surface2,
    }
```

**Library availability:** Catppuccin palette packages exist for Rust, Go, Python, JavaScript/TypeScript, Lua, Java, and others. Use the official package rather than hardcoding hex values — it ensures you stay in sync with any upstream corrections.

---

## Typography

### Typeface

**JetBrains Mono** — all weights from Light (300) to Bold (700). No other typeface is used anywhere in the interface.

Ensure JetBrains Mono is bundled with the application. Do not fall back to system monospace fonts.

### Size Scale

All sizes in pixels at 1x display scaling. Scale proportionally for HiDPI displays.

| Use | Size | Weight | Color Token |
|---|---|---|---|
| Dialog title | 15px | 600 (SemiBold) | `text_primary` |
| Settings page title | 16px | 600 (SemiBold) | `text_primary` |
| Body text / messages | 13px | 400 (Regular) | `text_primary` |
| Channel names, headers | 13px | 600 (SemiBold) | `text_primary` |
| Sidebar items | 13px | 400 (Regular) | `text_secondary` |
| Dialog body text | 13px | 400 (Regular) | `text_secondary` |
| Button text (standard) | 12px | 500 (Medium) | varies by type |
| Button text (compact) | 11px | 500 (Medium) | varies by type |
| Dropdown / select text | 12px | 400 (Regular) | `text_primary` |
| Metadata (timestamps) | 11px | 400 (Regular) | `text_dim` |
| Labels, field labels | 10–11px | 600 (SemiBold) | `text_dim` |
| Badges, keybinds | 10–11px | 600 (SemiBold) | varies |
| Tooltip text | 11px | 400 (Regular) | `text_secondary` |
| Toast text | 12px | 400 (Regular) | `text_secondary` |
| Input hint / error text | 10px | 400 (Regular) | `text_dim` or `status_danger` |

### Text Treatment

- Section headers and group labels: all uppercase, 0.8–1.0px extra letter spacing. In frameworks without letter-spacing control, accept default tracking.
- Italic: only for system messages (join/leave/voice events).
- Inline code: `status_success` (Green) text on `bg_input` (Crust) background, 12px, 2px horizontal padding.
- Code blocks: `text_primary` text on `bg_input` background, 1px `border` outline, 4px corner radius, 8–10px padding.
- Links: `accent` (Mauve) color, underlined. No color change on hover.
- Mentions: `accent_bright` (Lavender) text with translucent Mauve background (15% opacity, or pre-blend against `bg_main`).
- Dialog field labels: all uppercase, 11px, weight 600, `text_dim`.

---

## Layout

### Panel Structure

Grid-based panels separated by 1px `border` lines. No gaps or shadows.

**Text chat:**
```
┌──────┬──────────┬─────────────────────┬──────────┐
│Server│ Channel  │                     │ Member   │
│Strip │ Sidebar  │    Chat Messages    │ Sidebar  │
│ 52px │  180px   │     flexible        │  200px   │
│      │          │                     │          │
│      │          ├─────────────────────┤          │
│      │          │    Input Area       │          │
└──────┴──────────┴─────────────────────┴──────────┘
```

**Voice:**
```
┌──────┬──────────┬──────────────────────────────┐
│Server│ Channel  │                              │
│Strip │ Sidebar  │      Voice Tile Grid         │
│ 52px │  180px   │         flexible             │
│      │          ├──────────────────────────────┤
│      │          │     Voice Text Chat          │
└──────┴──────────┴──────────────────────────────┘
```

**Video:**
```
┌────────────────────────────────────────────────┐
│  Header                                        │
├───────────────────┬────────────────────────────┤
│   Video Tile      │      Video Tile            │
├───────────────────┼────────────────────────────┤
│   Video Tile      │      Video Tile            │
├────────────────────────────────────────────────┤
│  Toolbar                                       │
└────────────────────────────────────────────────┘
```

**Framework notes:** Qt6 → `QGridLayout` / `QSplitter`. Dear ImGui → `BeginChild()` regions. egui → `SidePanel` / `CentralPanel`.

### Spacing

| Context | Value |
|---|---|
| Panel internal padding | 8–12px |
| Message vertical padding | 4px |
| Channel list item padding | 4px vertical, 12px horizontal |
| Grid gaps (tiles) | 6–8px |
| Input area padding | 8px horizontal, 8px top, 12px bottom |
| Section spacing | 20–24px |
| Dialog internal padding | 16–20px horizontal, 16px vertical |
| Dialog footer button gap | 8px |
| Button icon-label gap | 6px |

Spacing is tight. Dense and efficient, not airy.

### Sizing Reference

| Element | Size |
|---|---|
| Server icon | 36×36px, radius 6px |
| User avatar (sidebar) | 24×24px |
| User avatar (user panel) | 28×28px |
| Voice tile avatar | 48×48px, radius 6px |
| Video tile avatar (camera off) | 64×64px, radius 8px |
| Control button | 24×24px, radius 3px |
| Toggle track | 36×20px, radius 10px |
| Toggle knob | 12×12px, circle |
| Checkbox | 16×16px, radius 3px |
| Radio button | 16×16px, circle |
| Radio inner dot | 6×6px, circle |
| Scrollbar width | 6px |
| Status dot | 8×8px |
| Voice activity dot | 6×6px |
| Toast dot | 6×6px |
| Slider track height | 4px |
| Slider thumb | 12×12px, circle |

---

## Components

### Server Icons

- Size: 36×36px, corner radius 6px.
- Default: `bg_panel` fill, 1px `border` outline, `text_secondary` text.
- Hover: `bg_hover` fill, `border_bright` outline.
- Active: `accent` (Mauve) border, `accent_bright` (Lavender) text. 3px-wide, 20px-tall `accent` indicator bar on left edge.
- Add server: dashed or 1px `accent` outline, `accent` text.

### Channel Items

- Default: `text_secondary` text.
- Hover: `bg_hover` fill, `text_primary` text.
- Active: `bg_active` fill, `accent_bright` text.
- Prefix: `#` for text, `♪` for voice, in `text_dim`.
- Unread badge: `accent_dim` fill, `accent_bright` text, radius 3px.

### Messages

- Timestamp region: fixed 48px, right-aligned, `text_dim`, 11px.
- Author name: colored by role token, weight 600.
- Message text: `text_primary`, weight 400.
- Hover: `bg_hover` fill on entire row.
- Reactions: `bg_input` fill, 1px `border`, `text_secondary` text, radius 3px. Active: `accent_dim` border, translucent accent fill.

### System Messages

- Italic, `text_dim`, 12px.
- Format: `── kira started a voice session in lounge ──`

### Date Dividers

- Centered `text_dim` text, 11px. 1px `border` lines extending to edges.

### Buttons

**Ghost (default):** No fill, 1px `border`, `text_secondary` text. Hover: `bg_hover` fill, `border_bright`, `text_primary`. Active/toggled: `accent` border, `accent_bright` text.

**Solid primary:** `accent_dim` fill, 1px `accent` border, `accent_bright` text. Hover: `accent` fill, white text (Latte: `text_primary` text).

**Solid danger:** Flamingo-tinted dim fill, 1px Red border, Red text. Hover: Red fill, white text. Use for destructive actions.

**Mute/Deafen toggle buttons:** These are toolbar buttons that switch icon and color based on state:
- **Unmuted / Undeafened:** `mdi-microphone` / `mdi-headphones` icon. Standard ghost button style — `text_secondary` icon, 1px `border`, no fill. Hover: `bg_hover` fill, `text_primary` icon.
- **Muted / Deafened:** `mdi-microphone-off` / `mdi-headphones-off` icon. `status_danger` (Red) icon color, 1px `status_danger` border. Hover: tinted Red fill (Red at 10% opacity, or pre-blend).
- The icon swaps and the color shifts from neutral to red on toggle, giving both a shape change and a color change as redundant signals.

**Disabled:** No fill, 1px `border`, `text_dim` text. No hover change. Cursor: not-allowed.

**Sizes:** Compact (4×10px pad, 11px text), Standard (6×16px, 12px), Large (8×24px, 12px weight 600). Radius: 3–4px.

### Input Fields

- Fill: `bg_input`. Border: 1px `border`, focus → `accent`. Text: `text_primary`. Placeholder: `text_dim`. Radius: 4px. Padding: 8×12px.
- Error: `status_danger` border, hint text in `status_danger`.
- Match/success: `status_success` border, hint text in `status_success`.

### Toggles

- Track: 36×20px, `bg_input` fill, 1px `border`, radius 10px.
- Knob: 12×12px, `text_dim`, 3px from left edge.
- On: `accent_dim` track, `accent` border, `accent_bright` knob, knob at 19px from left.

### Checkboxes

- 16×16px, radius 3px, `bg_input` fill, 1px `border`.
- Checked: `accent_dim` fill, `accent` border, `accent_bright` check mark `✓`.

### Radio Buttons

- 16×16px circle, `bg_input` fill, 1px `border`.
- Selected: `accent` border, `accent_bright` 6px inner dot.

### Select / Dropdown

- Trigger: `bg_input` fill, 1px `border`, radius 4px. `▾` arrow in `text_dim`. Hover: `border_bright`. Open: `accent` border.
- Menu: `bg_panel` fill, 1px `border`, radius 4px. Options: `text_secondary`, hover → `bg_hover` + `text_primary`. Selected: `accent_bright` text, `bg_active` fill.
- Divider: 1px `border`, 2px vertical margin.

### Context Menu

- `bg_panel` fill, 1px `border`, radius 4px, min-width 180px, 4px vertical padding.
- Items: `text_secondary`, hover → `bg_hover` + `text_primary`. Shortcut hints: `text_dim`, 10px, right-aligned.
- Danger items: Red text. Hover: tinted red fill.
- Divider: 1px `border`, 4px vertical margin.

### Dialogs

**Overlay:** Full window, `bg_deep` at 70% opacity. Click overlay or Escape to close.

**Dialog box:** `bg_panel` fill, 1px `border`, radius 6px. Centered. Width: 360–420px (confirmation), up to 500px (forms).

**Structure:** Title (15px, 600, `text_primary`) with close button (`mdi-close`, 18px, `text_dim`, hover → `text_primary`) right-aligned in header → optional subtitle (11px, `text_dim`) → body (`text_secondary`) → footer (right-aligned buttons, Cancel ghost + Action solid).

**Close button:** The `mdi-close` icon in the dialog header is a 28×28px hit area, `text_dim` default, `text_primary` on hover, radius 3px, `bg_hover` fill on hover. It functions identically to the Cancel button and Escape key — all three dismiss the dialog.

**Destructive confirmation:** Type-to-confirm pattern. Action button disabled until input matches. On match, transitions to solid danger. The close button and Cancel still dismiss without action regardless of input state.

### Toasts

- `bg_panel` fill, 1px `border`, radius 4px, 8×16px padding.
- Text: `text_secondary`, 12px. Preceded by 6px colored dot.
- Variants: Success → Green dot, Danger → Red dot, Warning → Yellow dot, Info → Mauve dot.
- Bottom-center, appears/disappears instantly, auto-dismiss 3 seconds, stack with 8px gap.

### Tooltips

- `bg_panel` fill, 1px `border`, radius 3px, 4×8px padding. `text_secondary`, 11px.
- Centered above target, 6px gap. 300ms hover delay.
- Include keybind: `Label · Ctrl+Shift+M`

### Badges

- 10px text, weight 600, 2×6px padding, radius 3px.
- Accent: `accent_dim` fill, `accent_bright` text.
- Dim: `bg_hover` fill, `text_secondary` text.
- Success: tinted Green fill, Green text.
- Danger: tinted Red fill, Red text.

### Sliders

- Track: 4px tall, `bg_input` fill, radius 2px.
- Fill: `accent` (Mauve), radius 2px.
- Thumb: 12×12px circle, `accent_bright`, 2px `bg_deep` border.
- Value label: 11px, `text_secondary`, right of track.

### Progress Bars

- Track: 4px, `bg_input`, radius 2px. Fill: `accent`. Complete: Green fill.

### Voice Tiles

- `bg_panel` fill, radius 6px, 1px `border`. Avatar 48×48px, radius 6px.
- Speaking: Green border + subtle glow (framework-dependent, or 2px Green border).
- Muted: 16×16px Red circle with white `×` at avatar corner.
- Voice bars: 4 bars, 3px wide, Green, staggered sine animation.

### Video Tiles

- `bg_main` fill, radius 6px, 1px `border`.
- Speaking: Green border + glow.
- Camera off: centered 64×64px avatar with name label.
- Camera on: video frame fills tile. Name label at bottom-left on translucent `bg_deep` background.
- Framework rendering: Qt6 → `QOpenGLWidget`, Dear ImGui → `ImGui::Image()`, egui → `TextureHandle`.

### Scrollbars

- Track: Surface 0 tint, 6px wide. Thumb: Surface 2, radius 3px.
- Show on hover/scroll only where possible.

---

## Animation

Minimal and functional, never decorative.

| Element | Property | Duration | Easing |
|---|---|---|---|
| Hover transitions | Fill/border | 100–150ms | Ease |
| Focus transitions | Border | 150ms | Ease |
| Button press | Fill | 50ms | Ease |
| Toggle knob | Position | 150ms | Ease |
| Checkbox check | Opacity | 100ms | Ease |
| Voice bars | Scale Y | 800ms/cycle | Sine |
| Connected pulse | Opacity | 2000ms/cycle | Linear |
| Mic level | Width | Realtime | Direct |

**No entrance animations.** No fade/slide on page load, dialog open/close, dropdown open/close, or toast appear/dismiss. Instant.

---

## Iconography

Vox uses **Material Design Icons (MDI)** from Pictogrammers. MDI provides 7200+ icons as SVG paths, making them framework-agnostic — render as SVG, texture, or font glyph depending on your stack.

**License:** MDI is released under the Apache 2.0 license. Include the license in your credits tab.

### Icon Reference

| MDI Name | Code Reference | Usage |
|---|---|---|
| `mdi-pound` | `mdiPound` | Text channel |
| `mdi-volume-high` | `mdiVolumeHigh` | Voice channel |
| `mdi-video` | `mdiVideo` | Video / camera on |
| `mdi-video-off` | `mdiVideoOff` | Camera off |
| `mdi-monitor-share` | `mdiMonitorShare` | Screen share |
| `mdi-cog` | `mdiCog` | Settings |
| `mdi-close` | `mdiClose` | Close dialog / dismiss |
| `mdi-plus` | `mdiPlus` | Add / create |
| `mdi-chevron-right` | `mdiChevronRight` | Expand / indicator |
| `mdi-chevron-down` | `mdiChevronDown` | Dropdown arrow |
| `mdi-microphone` | `mdiMicrophone` | Mic active |
| `mdi-microphone-off` | `mdiMicrophoneOff` | Mic muted |
| `mdi-headphones` | `mdiHeadphones` | Audio on / deafen off |
| `mdi-headphones-off` | `mdiHeadphonesOff` | Deafened |
| `mdi-phone-hangup` | `mdiPhoneHangup` | Disconnect / leave call |
| `mdi-check` | `mdiCheck` | Checkbox check, confirmation |
| `mdi-send` | `mdiSend` | Send message |
| `mdi-pin` | `mdiPin` | Pin message |
| `mdi-reply` | `mdiReply` | Reply to message |
| `mdi-pencil` | `mdiPencil` | Edit message |
| `mdi-delete` | `mdiDelete` | Delete |
| `mdi-content-copy` | `mdiContentCopy` | Copy text |
| `mdi-account-plus` | `mdiAccountPlus` | Invite user |
| `mdi-account-remove` | `mdiAccountRemove` | Kick user |
| `mdi-circle` | `mdiCircle` | Status dot (online) |
| `mdi-circle-half-full` | `mdiCircleHalfFull` | Status dot (idle) |
| `mdi-circle-outline` | `mdiCircleOutline` | Status dot (offline) |

### Icon Sizing

| Context | Size |
|---|---|
| Inline with body text | 16px |
| Sidebar channel prefix | 16px |
| Toolbar buttons | 20px |
| Dialog close button | 18px |
| User panel controls | 18px |
| Large feature icons | 24px |

### Integration

| Framework | Method |
|---|---|
| **Qt6** | Load SVG paths via `QIcon` from SVG files, or use the MDI webfont with `QFont`. |
| **Dear ImGui** | Render SVG paths to textures at startup, or use the MDI webfont loaded via `ImFontAtlas`. |
| **egui** | Use the MDI webfont via `FontDefinitions`, or render SVG to `TextureHandle`. |
| **Web** | Import from `@mdi/js` (tree-shakeable SVG paths) or `@mdi/font` (webfont). SVG paths preferred. |
| **Rust** | Use the `materialdesignicons` crate or embed SVG path data as constants. |

Icons inherit color from their parent context. Do not hardcode icon colors — they should respond to the same token as the text they sit beside.

---

## Theming

### User Configuration

```toml
[appearance]
flavor = "mocha"    # mocha, macchiato, frappe, latte
```

Client loads the named flavor at startup, maps it to the Vox token system, and applies to the framework's styling API. One config key, four complete themes.

### Flavor Selection Guide

| Flavor | Best For |
|---|---|
| Mocha | Low-light environments, OLED displays, deepest contrast |
| Macchiato | General use, balanced contrast |
| Frappé | Users who prefer slightly lighter dark themes |
| Latte | Well-lit rooms, users who prefer light themes |

### Framework Integration

| Framework | Method |
|---|---|
| **Qt6** | Map Vox tokens to `QPalette` roles or generate QSS stylesheet from token values. |
| **Dear ImGui** | Set `ImGuiStyle::Colors[]` from token map. Load at startup. |
| **egui** | Set `Visuals` struct from token map via `Context::set_visuals()`. |
| **GTK4** | Inject token hex values into template CSS string, load via `CssProvider`. |
| **Web** | Set CSS custom properties from token map on `:root`. |

**Rust crate:** `catppuccin` on crates.io provides all flavors with conversions for egui, ratatui, iced, and bevy. Use it directly.

---

## Platform Considerations

### DPI / Display Scaling

All pixel values assume 1x scaling (96 DPI). Frameworks handle scaling:
- Qt6: logical pixels with high-DPI scaling enabled.
- Dear ImGui: scale `ImFontConfig::SizePixels` and `ImGuiStyle` values by DPI factor.
- egui: automatic via `pixels_per_point`.

### Font Loading

Bundle JetBrains Mono. Do not use system fonts.

| Framework | Method |
|---|---|
| Qt6 | `QFontDatabase::addApplicationFont()` |
| Dear ImGui | `ImFontAtlas::AddFontFromFileTTF()` |
| egui | `FontDefinitions` font_data map |

Load Regular (400) and SemiBold (600) at minimum.

### Input Handling

- All elements: mouse click + keyboard navigation (Tab/Enter/Escape).
- Chat input captures keyboard focus on typing.
- Dialogs trap focus within their elements.
- Global voice keybinds (push-to-talk, mute): platform-specific hooks (Windows `RegisterHotKey`, macOS `CGEvent` tap, Linux `XGrabKey`).

### Video Frame Rendering

| Framework | Method |
|---|---|
| Qt6 | `QOpenGLWidget` with YUV shader, or `QImage` + `QPainter` (slower). |
| Dear ImGui | GPU texture upload, `ImGui::Image()`. Reuse handles. |
| egui | `TextureHandle` via `Context::load_texture()`, update per frame. |

Prefer GPU texture upload for ≥720p.

---

## Accessibility

The Catppuccin palette is designed with contrast in mind. Each flavor has been tested by the community across hundreds of applications.

**Why this approach avoids the prior single-hue issues:**
- Text colors (Text, Subtext 0/1, Overlay 0/1/2) are pre-defined with appropriate contrast against background colors (Base, Mantle, Crust).
- Roles use distinct hues (Red, Peach, Blue, Subtext 1) — distinguishable even with color vision deficiency.
- Status indicators use distinct hues (Green, Red, Yellow) with supplementary symbols (voice bars for speaking, `×` for muted, `○`/`●` for online/offline).
- No color-only signaling for critical state. Every status has a shape or symbol backup.

**Additional accessibility measures:**
- Never rely on color alone. Muted state has `×` symbol + Red. Speaking state has animated bars + Green. Online/idle/offline use different shapes (filled/half/hollow circle).
- Role hierarchy is supplemented by font weight: admin 700, mod 600, dev 500, member 400.
- Focus indicators use `accent` border on all interactive elements for keyboard navigation.
- Dialogs trap tab focus.
- Minimum touch target: 24×24px for all interactive elements.

---

## Licensing

**Catppuccin** is released under the **MIT License**. Copyright © 2021-present Catppuccin Org.

**Material Design Icons (MDI)** is released under the **Apache License 2.0**. Copyright © Pictogrammers.

Include both license texts in your application's license/credits tab. Both licenses permit commercial use, modification, and distribution.

---

## Do / Don't

**Do:**
- Use the Catppuccin token names in code and documentation for clarity.
- Use the official palette package for your language rather than hardcoding hex values.
- Keep text small and dense. This is a tool.
- Use uppercase + letter-spacing for labels and section headers.
- Keep borders at 1px. Never thicker (exception: 3px server indicator, 2px speaking border).
- Supplement color with symbols for all status indicators.
- Test with all four flavors before shipping UI changes.
- Bundle the font.

**Don't:**
- Use drop shadows for depth. Use background lightness stepping.
- Use gradients.
- Use corner radii larger than 8px.
- Use color for decoration. Color communicates state or hierarchy.
- Add transitions longer than 150ms.
- Animate dialog/toast/dropdown open/close.
- Use OS-native dialogs. All dialogs render in-app.
- Use emoji in UI chrome.
- Modify the Catppuccin palette values. Use them as-is.
- Mix icon sources. Use MDI exclusively for consistency.
- Use MDI icons at sizes below 14px — they lose clarity.
