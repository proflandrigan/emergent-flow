"""
emergentflow.data.http.live
~~~~~~~~~~~~~~~~~~~~~~~~~~~

``UrllibHttpClient`` — the effectful ``HttpClient`` that makes the real network
call using the standard library ``urllib.request``. This is the ONLY place in the
HTTP seam that opens a socket. It is never imported by ``compile_to_code`` /
``execute`` (ADR 0002 purity). It resolves credentials from ``os.environ`` by
**name** at call time, so nothing secret is ever in the IR or in an
``HttpRequest.content_hash()``.

This module is the ``GatewayClient`` / ``AdapterWarehouseClient`` analog for
HTTP: it lives at the effectful edge, quarantining I/O so the SDK core stays
pure.
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.parse
import urllib.request

from emergentflow.data.http.protocol import HttpRequest, HttpResponse

# urllib.request.urlopen also handles ``file://`` and ``ftp://``, so an
# unvalidated URL from a graph param would be a local file-read primitive.
# The scheme allow-list closes that.
ALLOWED_URL_SCHEMES: frozenset[str] = frozenset({"http", "https"})


class MissingAuthEnvError(RuntimeError):
    """Raised when the configured auth env-var name is unset in the environment.

    The message names the *env var*, never a value -- there is none to leak here.
    """


class UnsupportedUrlSchemeError(ValueError):
    """Raised when a request URL's scheme is not in ``ALLOWED_URL_SCHEMES``.

    The message names the offending scheme and the allowed set.
    """


class UrllibHttpClient:
    """The effectful ``HttpClient`` backed by ``urllib.request``.

    Structurally satisfies ``emergentflow.data.http.protocol.HttpClient``.
    Constructs a live connection on every ``fetch()`` call. Callers outside
    tests and the equivalence harness import this module explicitly; the
    SDK's normal import path never touches it (ADR 0002).

    Parameters
    ----------
    auth_env:
        The **name** of the environment variable holding the credential
        (e.g. ``"MY_API_TOKEN"``). ``None`` means the client sends no auth
        header.
    auth_header:
        The header name to inject (default ``"Authorization"``).
    auth_scheme:
        The scheme prefix (default ``"Bearer"``). An empty string means send
        the raw value with no prefix (e.g. for an ``X-API-Key`` header).
    default_timeout_s:
        Used when ``HttpRequest.timeout_s`` is ``None``.
    """

    def __init__(
        self,
        *,
        auth_env: str | None = None,
        auth_header: str = "Authorization",
        auth_scheme: str = "Bearer",
        default_timeout_s: float = 30.0,
    ) -> None:
        self.auth_env = auth_env
        self.auth_header = auth_header
        self.auth_scheme = auth_scheme
        self.default_timeout_s = default_timeout_s

    def _resolve_auth_header(self) -> tuple[str, str] | None:
        """Resolve and return the auth header pair, or ``None`` if no auth is
        configured.

        Returns ``None`` when ``self.auth_env is None``. Otherwise reads
        ``os.environ.get(self.auth_env)``; if unset or empty, raises
        ``MissingAuthEnvError`` naming ``self.auth_env``.
        """
        if self.auth_env is None:
            return None
        value = os.environ.get(self.auth_env)
        if not value:
            raise MissingAuthEnvError(f"Auth env var {self.auth_env!r} is unset or empty.")
        header_value = value if not self.auth_scheme else f"{self.auth_scheme} {value}"
        return (self.auth_header, header_value)

    def fetch(self, request: HttpRequest) -> HttpResponse:
        """Perform one HTTP request and return an inspectable ``HttpResponse``.

        Catches ``urllib.error.HTTPError`` and converts it to a **returned**
        ``HttpResponse`` — a non-2xx status is data the caller interprets,
        exactly as with ``ReplayHttpClient``. Does not raise on error statuses.
        """
        # 1. Build the final URL with params
        url = request.url
        if request.params:
            query = urllib.parse.urlencode(list(request.params))
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{query}"

        # 2. Validate scheme on the final URL, before opening anything
        scheme = urllib.parse.urlsplit(url).scheme.lower()
        if scheme not in ALLOWED_URL_SCHEMES:
            raise UnsupportedUrlSchemeError(
                f"URL scheme {scheme!r} is not allowed; "
                f"allowed schemes: {sorted(ALLOWED_URL_SCHEMES)}"
            )

        # 3. Assemble headers
        headers = dict(request.headers)
        auth = self._resolve_auth_header()
        if auth:
            headers[auth[0]] = auth[1]

        # 4. Encode body
        data = request.body.encode("utf-8") if request.body is not None else None

        # 5. Build the request
        req = urllib.request.Request(url, data=data, headers=headers, method=request.method)

        # 6. Time the call
        t0 = time.perf_counter()
        timeout = request.timeout_s if request.timeout_s is not None else self.default_timeout_s

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                body = resp.read().decode(
                    resp.headers.get_content_charset() or "utf-8",
                    errors="replace",
                )
                response_headers: tuple[tuple[str, str], ...] = tuple(resp.headers.items())
                return HttpResponse(
                    status=resp.status,
                    body=body,
                    headers=response_headers,
                    url=resp.geturl(),
                    elapsed_ms=elapsed_ms,
                )
        except urllib.error.HTTPError as err:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            try:
                error_body = err.read().decode(
                    err.headers.get_content_charset() or "utf-8",
                    errors="replace",
                )
            except Exception:
                error_body = ""
            error_headers: tuple[tuple[str, str], ...] = tuple(err.headers.items())
            return HttpResponse(
                status=err.code,
                body=error_body,
                headers=error_headers,
                url=err.geturl() or url,
                elapsed_ms=elapsed_ms,
            )


__all__ = [
    "ALLOWED_URL_SCHEMES",
    "MissingAuthEnvError",
    "UnsupportedUrlSchemeError",
    "UrllibHttpClient",
]
