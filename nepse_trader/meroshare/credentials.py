"""MeroShare credential resolution — and every path a secret could escape by.

The user's password reaches exactly one place: the login request body. Getting
that right means closing four leaks, each of which has bitten real projects:

1. **``repr()`` in a traceback.** Python prints locals-free tracebacks, but any
   library that formats an object (pydantic validation errors, ``logging``'s
   ``%r``, pytest assertion rewriting) will call ``repr``. So
   :class:`MeroShareCredentials` renders redacted under both ``repr`` and
   ``str``, and its ``password`` is only reachable through an explicit
   :meth:`MeroShareCredentials.reveal_password` call that reads as a decision.
2. **An httpx exception carrying the request.** ``httpx.HTTPStatusError`` holds
   ``.request``, whose ``.content`` is the JSON login body. Never let one of
   those propagate out of the client — see ``nepse_trader.meroshare.client``,
   which converts them and passes the message through :func:`redact` first.
3. **A DEBUG log line.** Anything this package logs goes through
   :func:`redact` before it is handed to ``logging``.
4. **A settings dump.** ``Settings`` is a pydantic model whose ``repr`` includes
   ``meroshare_password``. Nothing here logs or serialises a ``Settings``, and
   :func:`redact` also scrubs the settings-sourced password so a caller that
   does it anyway is still covered for the fields we control.

Resolution order is explicit argument → OS keyring → settings/env. ``keyring``
is an optional dependency, imported lazily; when it is absent (or has no
backend) resolution says so and falls through instead of raising.

This is read-only access to the user's own account. Automating a login-gated
portal may conflict with CDSC's terms of service; that is the user's call, and
``meroshare import`` exists for anyone who would rather not store a password.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nepse_trader.config import Settings, get_settings

REDACTED = "***REDACTED***"


class MeroShareCredentialError(Exception):
    """Credentials are missing or unusable. Never contains a credential."""


def redact(text: object, *secrets: str) -> str:
    """Return ``text`` as a string with every non-empty secret masked.

    Used on every message this package logs or raises. Extra ``secrets`` are
    scrubbed on top of the settings-sourced password/username, so a caller can
    pass a value that never reached ``Settings`` (a keyring password, say).
    """
    out = str(text)
    candidates = list(secrets)
    try:
        settings = get_settings()
        candidates.extend(
            [
                settings.meroshare_password,
                settings.meroshare_username,
                settings.meroshare_dp_id,
            ]
        )
    except Exception:  # noqa: BLE001 - redaction must never be the thing that fails
        pass
    for secret in candidates:
        # A one-character password or account identifier is still a
        # credential.  Never make its safety depend on an arbitrary length
        # threshold: the caller may explicitly pass a short secret, and the
        # settings path may contain one too.  Empty values are ignored so an
        # empty password cannot turn every message into a mask.
        if secret:
            out = out.replace(secret, REDACTED)
    return out


class MeroShareCredentials:
    """One account's login triple. Renders redacted under ``repr`` and ``str``.

    Deliberately *not* a dataclass and *not* a pydantic model: both generate a
    field-dumping ``repr``, and pydantic puts input values into
    ``ValidationError`` messages. The password is stored under a private name and
    read only through :meth:`reveal_password`, so an f-string, a ``vars()``
    dump, or a ``dataclasses.asdict`` cannot surface it by accident.
    """

    __slots__ = ("dp_id", "username", "_password", "source")

    def __init__(self, dp_id: str, username: str, password: str, source: str = "settings") -> None:
        self.dp_id = (dp_id or "").strip()
        self.username = (username or "").strip()
        self._password = password or ""
        self.source = source

    def reveal_password(self) -> str:
        """The plaintext password. Every call site is a deliberate decision."""
        return self._password

    @property
    def complete(self) -> bool:
        return bool(self.dp_id and self.username and self._password)

    def missing(self) -> list[str]:
        """Which fields are empty, by name — safe to show the user."""
        return [
            name
            for name, value in (
                ("dp_id", self.dp_id),
                ("username", self.username),
                ("password", self._password),
            )
            if not value
        ]

    def require_complete(self) -> MeroShareCredentials:
        """Self, or raise naming only the *missing field names*."""
        gaps = self.missing()
        if gaps:
            raise MeroShareCredentialError(
                "MeroShare credentials incomplete: missing "
                + ", ".join(gaps)
                + ". Set NEPSE_MEROSHARE_DP_ID / _USERNAME / _PASSWORD, or use "
                "`meroshare import` to load a CSV export instead."
            )
        return self

    def redact(self, text: object) -> str:
        """:func:`redact`, plus every account identifier on this instance."""
        return redact(text, self._password, self.username, self.dp_id)

    def __repr__(self) -> str:
        # dp_id and username are not secrets in the password sense, but they
        # identify the account, and the redaction test asserts the username
        # never appears in a repr either. So: nothing but the shape.
        return (
            f"MeroShareCredentials(dp_id={REDACTED}, username={REDACTED}, "
            f"password={REDACTED}, source={self.source!r}, complete={self.complete})"
        )

    __str__ = __repr__

    def __format__(self, spec: str) -> str:
        # Closes f"{creds}" and f"{creds:>40}" alike.
        return format(self.__repr__(), spec)


def keyring_available() -> tuple[bool, str]:
    """Whether the optional ``keyring`` module imports. ``(ok, reason)``."""
    try:
        import keyring  # noqa: F401
    except ImportError:
        return False, (
            "the optional 'keyring' package is not installed "
            "(pip install keyring) — falling back to env/.env"
        )
    return True, ""


def _password_from_keyring(service: str, username: str) -> tuple[str, str]:
    """Fetch a password from the OS keyring. Returns ``(password, reason)``.

    An empty password with a reason means "not available, fall through". A
    keyring backend failure (locked keyring, no D-Bus, headless box) is a
    fall-through too, not an error: the env path may still work.
    """
    ok, reason = keyring_available()
    if not ok:
        return "", reason
    if not username:
        return "", "keyring lookup needs a username; none configured"
    import keyring
    from keyring.errors import KeyringError

    try:
        secret = keyring.get_password(service, username)
    except KeyringError as exc:
        return "", f"keyring backend unavailable: {type(exc).__name__}"
    except Exception as exc:  # noqa: BLE001 - backends raise their own zoo
        return "", f"keyring lookup failed: {type(exc).__name__}"
    if not secret:
        return "", f"no password stored in keyring service {service!r} for that user"
    return secret, ""


@dataclass(frozen=True)
class Resolution:
    """A resolution attempt: the credentials plus how they were found.

    ``notes`` explains any fall-through (keyring missing, backend locked) so the
    CLI can tell the user *why* it used the env value. Notes never contain a
    credential — they are built from field names and exception types only.
    """

    credentials: MeroShareCredentials
    notes: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.credentials.complete


def resolve_credentials(
    settings: Settings | None = None,
    *,
    dp_id: str | None = None,
    username: str | None = None,
    password: str | None = None,
    keyring_getter=None,
) -> Resolution:
    """Resolve credentials: explicit argument → OS keyring → settings/env.

    ``keyring_getter`` is the seam tests use: a callable
    ``(service, username) -> (password, reason)`` replacing
    :func:`_password_from_keyring`. Nothing here logs, and the returned notes
    are field names and exception types only.
    """
    settings = settings or get_settings()
    notes: list[str] = []

    resolved_dp = (dp_id if dp_id is not None else settings.meroshare_dp_id) or ""
    resolved_user = (username if username is not None else settings.meroshare_username) or ""

    if password is not None and password != "":
        return Resolution(
            MeroShareCredentials(resolved_dp, resolved_user, password, source="argument"),
            notes,
        )

    if settings.meroshare_use_keyring:
        getter = keyring_getter or _password_from_keyring
        secret, reason = getter(settings.meroshare_keyring_service, resolved_user.strip())
        if secret:
            return Resolution(
                MeroShareCredentials(resolved_dp, resolved_user, secret, source="keyring"),
                notes,
            )
        notes.append(reason or "keyring returned no password")

    return Resolution(
        MeroShareCredentials(
            resolved_dp, resolved_user, settings.meroshare_password, source="settings"
        ),
        notes,
    )
