"""Smart table extraction → CSV / SQL with provenance."""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from makepdf.web.auth import require_api_key
from makepdf.web.ai_helpers import call_openrouter, parse_ai_json


router = APIRouter(prefix="/api/smart-table", tags=["smart-table"])


class ExtractReq(BaseModel):
    page_text: str
    expected_columns: Optional[List[str]] = None


@router.post("/extract")
async def extract(req: ExtractReq, api_key: Optional[str] = Depends(require_api_key)):
    if not req.page_text:
        raise HTTPException(400, "page_text required")
    system = (
        "Extract tabular data from the supplied page text. Return JSON: "
        "{\"columns\":[string],\"rows\":[[any]],\"schema_inferred\":[{\"name\":string,\"type\":\"string|int|float|date\"}],"
        "\"provenance\":[{\"col\":string,\"row\":int,\"text_span\":string}]}."
    )
    user = f"Expected columns (optional): {req.expected_columns or []}\n\nText:\n{req.page_text[:7000]}"
    raw = call_openrouter(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=1500,
        temperature=0.0,
    )
    return parse_ai_json(raw) or {"raw": raw}


@router.post("/to-csv")
async def to_csv(payload: Dict[str, Any], api_key: Optional[str] = Depends(require_api_key)):
    cols = payload.get("columns") or []
    rows = payload.get("rows") or []
    buf = io.StringIO()
    w = csv.writer(buf)
    if cols:
        w.writerow(cols)
    for r in rows:
        w.writerow(r)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=table.csv"},
    )


@router.post("/to-sql")
async def to_sql(payload: Dict[str, Any], api_key: Optional[str] = Depends(require_api_key)):
    """Return a CREATE TABLE + INSERT statements for a table."""
    table_name = payload.get("table", "extracted_table")
    cols = payload.get("columns") or []
    rows = payload.get("rows") or []
    schema = payload.get("schema_inferred") or []
    col_defs = []
    type_map = {"int": "INTEGER", "float": "REAL", "date": "DATE", "string": "TEXT"}
    for c in cols:
        col_type = next((s["type"] for s in schema if s.get("name") == c), "string")
        col_defs.append(f'"{c}" {type_map.get(col_type, "TEXT")}')
    create = f'CREATE TABLE "{table_name}" ({", ".join(col_defs) or "col1 TEXT"});'
    inserts = []
    for r in rows:
        vals = ", ".join("NULL" if v is None else f"'{str(v).replace(chr(39), chr(39)+chr(39))}'" for v in r)
        inserts.append(f'INSERT INTO "{table_name}" VALUES ({vals});')
    return {"create": create, "inserts": inserts, "row_count": len(rows)}
