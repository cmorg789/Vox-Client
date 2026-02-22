"""Login / register dialog – frameless themed dialog."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from vox_sdk import Client
from vox_sdk.models.auth import MFARequiredResponse

from vox_client.state import AppState


def _field_label(text: str) -> QLabel:
    c = AppState.instance().theme.colors
    label = QLabel(text.upper())
    label.setStyleSheet(
        f"color: {c.text_dim}; font-size: 11px; font-weight: 600; letter-spacing: 0.5px;"
    )
    return label


class LoginDialog(QDialog):
    """Login / register form styled as a frameless themed dialog."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._client: Client | None = None
        self._client_url: str | None = None
        self._mfa_ticket: str | None = None
        self._register_mode = False

        # Results exposed after accept()
        self.client: Client | None = None
        self.user_id: int | None = None
        self.token: str | None = None

        c = AppState.instance().theme.colors

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(380, 360)
        self.setStyleSheet(
            f"LoginDialog {{ background-color: {c.bg_panel}; "
            f"border: 1px solid {c.border_bright}; border-radius: 6px; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(4)

        # Title
        self._title_label = QLabel("LOGIN")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setStyleSheet(
            f"color: {c.text_primary}; font-size: 15px; font-weight: 600; "
            f"padding-bottom: 8px; border: none;"
        )
        outer.addWidget(self._title_label)

        # -- Server URL
        outer.addWidget(_field_label("server"))
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("https://vox.example.com")
        outer.addWidget(self._url_input)

        # -- Username
        outer.addWidget(_field_label("username"))
        self._user_input = QLineEdit()
        self._user_input.setPlaceholderText("username")
        outer.addWidget(self._user_input)

        # -- Password
        outer.addWidget(_field_label("password"))
        self._pass_input = QLineEdit()
        self._pass_input.setPlaceholderText("********")
        self._pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        outer.addWidget(self._pass_input)

        # -- Display name (register only, hidden by default)
        self._display_name_label = _field_label("display name")
        self._display_name_input = QLineEdit()
        self._display_name_input.setPlaceholderText("optional")
        self._display_name_label.hide()
        self._display_name_input.hide()
        outer.addWidget(self._display_name_label)
        outer.addWidget(self._display_name_input)

        # -- MFA (hidden until needed)
        self._mfa_label = _field_label("mfa code")
        self._mfa_input = QLineEdit()
        self._mfa_input.setPlaceholderText("000000")
        self._mfa_label.hide()
        self._mfa_input.hide()
        outer.addWidget(self._mfa_label)
        outer.addWidget(self._mfa_input)

        # -- Status
        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet(f"color: {c.text_dim}; padding: 4px 0px; border: none;")
        outer.addWidget(self._status)

        # -- Action + Cancel buttons (right-aligned)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self._cancel_btn = QPushButton("[ CANCEL ]")
        self._cancel_btn.setAutoDefault(False)
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)

        self._action_btn = QPushButton("[ LOGIN ]")
        self._action_btn.setDefault(True)
        self._action_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c.accent_dim}; border: 1px solid {c.accent}; "
            f"color: {c.accent_bright}; border-radius: 4px; padding: 6px 16px; font-weight: 500; }}"
            f"QPushButton:hover {{ background-color: {c.accent}; border-color: {c.accent_bright}; color: white; }}"
            f"QPushButton:pressed {{ background-color: {c.accent_dim}; }}"
            f"QPushButton:disabled {{ color: {c.text_dim}; border-color: {c.border}; background: transparent; }}"
        )
        self._action_btn.clicked.connect(self._on_action_clicked)
        btn_row.addWidget(self._action_btn)

        outer.addLayout(btn_row)

        # -- Toggle link
        self._toggle_btn = QPushButton("no account? register")
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_mode)
        outer.addWidget(self._toggle_btn)

    # -- helpers -------------------------------------------------------------

    def _normalize_url(self, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        return url

    def _get_client(self, url: str) -> Client:
        url = self._normalize_url(url)
        if self._client is None or self._client_url != url:
            self._client = Client(url)
            self._client_url = url
        return self._client

    def _set_status(self, text: str, kind: str = "info") -> None:
        c = AppState.instance().theme.colors
        color_map = {
            "info": c.text_dim,
            "error": c.status_danger,
            "success": c.status_success,
            "warning": c.status_warning,
        }
        color = color_map.get(kind, c.text_dim)
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {color}; padding: 4px 0px;")

    # -- mode toggle ---------------------------------------------------------

    def _toggle_mode(self) -> None:
        self._register_mode = not self._register_mode
        self._mfa_ticket = None
        self._mfa_label.hide()
        self._mfa_input.hide()
        self._status.setText("")

        if self._register_mode:
            self._title_label.setText("REGISTER")
            self._action_btn.setText("[ REGISTER ]")
            self._toggle_btn.setText("have an account? login")
            self._display_name_label.show()
            self._display_name_input.show()
        else:
            self._title_label.setText("LOGIN")
            self._action_btn.setText("[ LOGIN ]")
            self._toggle_btn.setText("no account? register")
            self._display_name_label.hide()
            self._display_name_input.hide()

    # -- slots ---------------------------------------------------------------

    @asyncSlot()
    async def _on_action_clicked(self) -> None:
        if self._register_mode:
            await self._do_register()
        else:
            await self._do_login()

    async def _do_register(self) -> None:
        url = self._url_input.text().strip()
        username = self._user_input.text().strip()
        password = self._pass_input.text().strip()
        display_name = self._display_name_input.text().strip() or None

        if not url or not username or not password:
            self._set_status("all fields required", "error")
            return

        self._action_btn.setEnabled(False)
        self._set_status("registering...", "info")

        try:
            client = self._get_client(url)
            result = await client.auth.register(
                username, password, display_name=display_name
            )
            token = result.token
            user_id = result.user_id
            client.http.token = token
            self._set_status("connected", "success")
            self.client = client
            self.user_id = user_id
            self.token = token
            self.accept()
        except Exception as exc:
            msg = str(exc) or f"connection failed ({type(exc).__name__})"
            self._set_status(msg, "error")
            self._action_btn.setEnabled(True)

    async def _do_login(self) -> None:
        url = self._url_input.text().strip()
        username = self._user_input.text().strip()
        password = self._pass_input.text().strip()
        if not url or not username or not password:
            self._set_status("all fields required", "error")
            return

        self._action_btn.setEnabled(False)
        self._set_status("connecting...", "info")

        try:
            client = self._get_client(url)

            if self._mfa_ticket:
                code = self._mfa_input.text().strip()
                if not code:
                    self._set_status("enter mfa code", "error")
                    self._action_btn.setEnabled(True)
                    return
                result = await client.auth.login_2fa(
                    self._mfa_ticket, "totp", code=code
                )
                client.http.token = result.token
            else:
                result = await client.login(username, password)
                if isinstance(result, MFARequiredResponse):
                    self._mfa_ticket = result.mfa_ticket
                    self._mfa_label.show()
                    self._mfa_input.show()
                    self._set_status("mfa required", "warning")
                    self._action_btn.setEnabled(True)
                    return

            token = result.token
            user_id = result.user_id
            self._set_status("connected", "success")
            self.client = client
            self.user_id = user_id
            self.token = token
            self.accept()
        except Exception as exc:
            msg = str(exc) or f"connection failed ({type(exc).__name__})"
            self._set_status(msg, "error")
            self._action_btn.setEnabled(True)
