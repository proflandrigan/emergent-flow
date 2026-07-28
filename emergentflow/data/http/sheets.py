"""
emergentflow.data.http.sheets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``ef.data.load_google_sheet`` — load a Google Sheets tab into a DataFrame
through the injected ``HttpClient`` seam (Epic 16 Story 3).

Pure aside from the single delegated effect ``client.fetch(request)``. No
``os.environ``, no socket, no ``urllib`` import — the effect lives entirely
inside the injected client.

Chosen over the Sheets REST API deliberately: Google's CSV-export endpoint
returns plain CSV over a plain HTTP GET, so it rides the existing ``HttpClient``
seam with no Google SDK dependency and no OAuth flow. A private sheet is reached
with whatever credential the injected client is configured to send.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pandas as pd

from emergentflow.api import public_op
from emergentflow.data.contract import validate_schema
from emergentflow.data.errors import DataLoadError
from emergentflow.data.http.fetch import MissingHttpClientError
from emergentflow.data.http.protocol import HttpRequest

if TYPE_CHECKING:
    from emergentflow.data.http.protocol import HttpClient

#: URL template for Google Sheets' CSV export endpoint. Chosen over the Sheets REST
#: API deliberately: it is a plain GET returning CSV, so it rides the existing
#: HttpClient seam with no Google SDK dependency and no OAuth flow. A private sheet
#: is reached with whatever credential the injected client is configured to send.
SHEETS_CSV_URL = "https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:csv"

__all__ = [
    "SHEETS_CSV_URL",
    "load_google_sheet",
]


@public_op(name="ef.data.load_google_sheet")
def load_google_sheet(
    *,
    spreadsheet_id: str,
    client: HttpClient | None,
    sheet: str | None = None,
    header_row: int = 0,
    connection: str | None = None,
    timeout_s: float | None = None,
    expect_columns: list[str] | None = None,
    expect_dtypes: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Load a Google Sheets tab into a pandas DataFrame via the HTTP client seam.

    Uses Google's CSV-export endpoint (``/gviz/tq?tqx=out:csv``) — a plain HTTP
    GET returning CSV, so no Google SDK or OAuth is needed.  The injected
    *client* (an ``HttpClient``) supplies any credential for a private sheet.

    Parameters
    ----------
    spreadsheet_id:
        The id from the sheet's URL (e.g. ``"1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"``).
    client:
        The injected ``HttpClient``.  Pass ``None`` only to detect the missing-client
        case (raises ``MissingHttpClientError``).
    sheet:
        The tab/sheet name within the spreadsheet.  Omit (``None``) for the first/
        default tab.
    header_row:
        Zero-based row index to use as the column header (passed through to
        ``pd.read_csv``).  Default ``0``.
    connection:
        A connection-profile **name** (never a credential).  Resolved to live
        credentials by the ``HttpClient`` at ``fetch()`` time.
    timeout_s:
        Optional timeout in seconds for the HTTP request.
    expect_columns:
        Optional list of column names that must be present after loading. Checked
        once against the final frame via ``emergentflow.data.contract.validate_schema``.
    expect_dtypes:
        Optional map of column name to expected pandas dtype string, checked the
        same way.

    Returns
    -------
    pd.DataFrame
        The sheet data as a tidy DataFrame.

    Raises
    ------
    MissingHttpClientError
        If *client* is ``None``.
    ValueError
        If *spreadsheet_id* is empty.
    DataLoadError
        If the HTTP response is non-2xx, or the response body cannot be parsed as
        CSV with the given *header_row*.
    SchemaContractError
        If *expect_columns* or *expect_dtypes* is set and the loaded frame does
        not satisfy it.
    """
    if client is None:
        raise MissingHttpClientError(
            "ef.data.load_google_sheet requires an injected HttpClient; pass it via "
            "execute(graph, clients=Clients(http=...)) or the compiled module's "
            "main(clients=...)."
        )

    if not spreadsheet_id:
        raise ValueError(f"spreadsheet_id must be a non-empty string, got {spreadsheet_id!r}")

    url = SHEETS_CSV_URL.format(spreadsheet_id=spreadsheet_id)

    # Build params as a tuple so content_hash() is deterministic.
    # Put sheet in params (not the URL) so the fixture key is stable.
    params: tuple[tuple[str, str], ...] = ()
    if sheet is not None:
        params = (("sheet", sheet),)

    request = HttpRequest(
        url=url,
        method="GET",
        headers=(),
        params=params,
        body=None,
        connection=connection,
        timeout_s=timeout_s,
    )

    response = client.fetch(request)

    if not response.ok:
        body_preview = response.body[:500]
        if len(response.body) > 500:
            body_preview += "..."
        raise DataLoadError(
            f"HTTP {response.status} from spreadsheet {spreadsheet_id!r}: {body_preview}"
        )

    try:
        frame = pd.read_csv(io.StringIO(response.body), header=header_row)
    except (pd.errors.ParserError, ValueError) as exc:
        raise DataLoadError(
            f"Failed to parse CSV response from spreadsheet {spreadsheet_id!r}: {exc}"
        ) from exc

    return validate_schema(frame, expect_columns=expect_columns, expect_dtypes=expect_dtypes)
