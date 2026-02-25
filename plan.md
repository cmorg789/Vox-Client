# Direct Messages Implementation Plan

## Summary

Add 1-on-1 Direct Message support to Vox Client. Users will access DMs via an icon in the server strip, see a DM conversation list in the channel sidebar area, and chat using the existing message widgets. Users can initiate DMs from the member sidebar context menu and from a mini user profile popup.

## SDK Surface Available

- **REST API**: `client.dms.open()`, `.list()`, `.close()`, `.send_message()`, `.list_messages()`, `.edit_message()`, `.delete_message()`
- **Models**: `DMResponse(dm_id, participant_ids, is_group, name, icon)`, `DMListResponse`
- **Gateway events**: `dm_create`, `dm_update`, `dm_recipient_add/remove`, `dm_read_notify`
- **Message events**: `MessageCreate/Update/Delete` all carry `dm_id` field alongside `feed_id`
- **Typing**: `TypingStart` carries `dm_id`

---

## Step 1: AppState DM Infrastructure (`state.py`)

Add to `AppState`:

- **New state fields:**
  - `_dms: dict[int, DMResponse]` — dm_id → DM conversation cache
  - `current_dm_id: int | None` — currently viewed DM (mutually exclusive with `current_feed_id`)
  - `_dm_mode: bool` — whether we're in DM view vs server view

- **New signals:**
  - `dm_created = pyqtSignal(object)` — new DM opened
  - `dm_updated = pyqtSignal(object)`
  - `dm_list_changed = pyqtSignal()` — generic signal when DM list needs refresh
  - `dm_mode_changed = pyqtSignal(bool)` — True when entering DM mode, False when returning to server

- **New helper methods:**
  - `get_dm_partner_id(dm_id) -> int | None` — return the other participant's user_id
  - `get_dm_display_name(dm_id) -> str` — return the partner's display name for 1-on-1 DMs

- **New data loader:**
  - `load_dm_list()` — fetch DMs via `client.dms.list()` and populate `_dms` cache

- **New gateway handlers:**
  - `dm_create` → update `_dms` cache, emit `dm_created`
  - `dm_update` → update `_dms` cache, emit `dm_updated`
  - Handle `message_create`/`update`/`delete` events with `dm_id` (in addition to `feed_id`)

---

## Step 2: Server Strip DM Button (`server_strip.py`)

- Add a DM button at the **very top** of the server strip, above the server icon
- Use the `account-group.svg` icon (already exists in resources)
- Place a horizontal rule (1px `border` separator) between the DM button and the server icon
- Style follows the existing `_ServerButton` pattern: ghost style default, `accent` border + `accent_bright` icon when active
- Clicking the DM button:
  - Sets `state._dm_mode = True`, emits `dm_mode_changed(True)`
  - Deactivates the server button
- Clicking the server button:
  - Sets `state._dm_mode = False`, emits `dm_mode_changed(False)`
  - Deactivates the DM button
- New signal: `dm_clicked = pyqtSignal()` on `ServerStrip`

---

## Step 3: DM Sidebar Widget (new file: `widgets/dm_sidebar.py`)

A 180px sidebar that replaces the channel sidebar when in DM mode.

**Layout:**
```
┌─────────────────┐
│ DIRECT MESSAGES  │  ← Header with "+" button
├─────────────────┤
│ ○ Username1     │  ← DM conversation items (scrollable)
│ ○ Username2     │
│ ...             │
└─────────────────┘
```

**Components:**
- **Header**: "DIRECT MESSAGES" label (uppercase, `text_dim`, 11px, weight 600) + "+" icon button (opens new DM dialog)
- **DM Item**: Row showing:
  - Presence dot (8px, colored by status: green/yellow/grey)
  - Avatar (24x24px) using `AvatarWidget`
  - Display name (13px, `text_secondary`, active: `accent_bright`)
  - Hover: `bg_hover` background
  - Active: `bg_active` background
  - Close button on hover (small × to close/hide the DM)
- **New DM Dialog**: Simple dialog with a search input to find users by name, results list, and "Open DM" button

**Signals:**
- `dm_selected = pyqtSignal(int)` — emits dm_id when a conversation is clicked

---

## Step 4: MainWindow Integration (`views/main_window.py`)

- **Sidebar switching**: On `dm_mode_changed`:
  - `True`: Hide `_channel_sidebar`, show `_dm_sidebar`, hide `_member_sidebar`
  - `False`: Show `_channel_sidebar`, hide `_dm_sidebar`, show `_member_sidebar`
- **DM selection**: Connect `_dm_sidebar.dm_selected` to `_on_dm_selected()`:
  - Set `state.current_dm_id = dm_id`, clear `state.current_feed_id`
  - Update `_chat_header` with DM partner info
  - Update `_chat_input` placeholder to "Message @username"
  - Load messages via `state.client.dms.list_messages(dm_id)`
- **Feed selection**: When a server channel is selected, clear `current_dm_id`
- **Message sending**: Update `_on_send()` to check if we're in DM mode and use `client.dms.send_message()` instead of `client.messages.send()`
- **Typing indicator**: Update `_on_local_typing()` to send `dm_id` for DM context

---

## Step 5: MessageList Adaptation (`widgets/message_list.py`)

- Add `_current_dm_id: int | None` field
- New method `load_dm_messages(dm_id)` that:
  - Sets `_current_dm_id`, clears `_current_feed_id`
  - Fetches messages via `client.dms.list_messages(dm_id, limit=150)`
  - Renders them using the same `_add_message()` pipeline
- Update `_on_message_received/updated/deleted`:
  - Check `dm_id` on the event in addition to `feed_id`
  - Route DM messages to the correct view
- Update `_load_older_messages` to use DM API when in DM context
- Update `_finish_edit` and `_delete_message` to use DM API when `_current_dm_id` is set

---

## Step 6: ChatHeader Adaptation (`widgets/chat_header.py`)

- New method `set_dm(dm_id)`:
  - Shows partner's display name with `@` prefix
  - Shows presence status as subtitle
  - Hides channel settings icon (not applicable for DMs)

---

## Step 7: ChatInput Adaptation (`widgets/chat_input.py`)

- Minor: `set_channel_name()` already sets the placeholder text — just call it with the DM partner's name

---

## Step 8: Member Sidebar Context Menu (`widgets/member_sidebar.py`)

- Add "Send Message" option to the existing member right-click context menu
- On click: opens/creates a DM with that user via `client.dms.open(recipient_id=user_id)`, switches to DM mode, selects the conversation

---

## Step 9: User Profile Card (new file: `widgets/user_profile_card.py`)

A mini popup that appears when clicking a username in messages or the member sidebar.

**Layout:**
```
┌───────────────────┐
│ [Avatar]  Username│
│           @handle │
│ ○ Online          │
│ [Message] [Close] │
└───────────────────┘
```

- **Styling**: `bg_panel` fill, 1px `border`, radius 6px, ~220px wide
- **"Message" button**: Small accent button, opens/creates DM
- Appears as a popup positioned near the clicked element
- Dismiss on click-outside or Escape

---

## Step 10: Wire Gateway Typing for DMs

- Update `_on_remote_typing` in MainWindow to handle `dm_id` on `TypingStart` events
- Update `_on_local_typing` to send typing with `dm_id` when in DM context
- The gateway `send_typing` only supports `feed_id` currently — extend to send `dm_id` (or use the raw `send()` method)

---

## File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `state.py` | Modify | Add DM state, signals, cache, gateway handlers |
| `server_strip.py` | Modify | Add DM icon button at top |
| `widgets/dm_sidebar.py` | **New** | DM conversation list sidebar |
| `widgets/user_profile_card.py` | **New** | Mini user profile popup |
| `views/main_window.py` | Modify | DM/server mode switching, DM message flow |
| `widgets/message_list.py` | Modify | Support dm_id context for messages |
| `widgets/chat_header.py` | Modify | DM partner display |
| `widgets/chat_input.py` | Minor | Placeholder text for DM context |
| `widgets/member_sidebar.py` | Modify | "Send Message" context menu + click handler |
