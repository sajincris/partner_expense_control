"""CSV / Excel exports. Amounts are written as numbers (not text) in Excel."""
import csv
import io
from decimal import Decimal

from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from app.core.errors import ValidationFailedError

MONEY_FORMAT = "#,##0.00;[Red]-#,##0.00"


def _cell(value):
    if isinstance(value, Decimal):
        return float(value)  # Excel cells are IEEE doubles; source of truth stays DECIMAL in the DB
    if hasattr(value, "value"):
        return value.value
    return value


def export_rows(rows: list[dict], *, filename: str, fmt: str, title: str = "Report") -> StreamingResponse:
    if fmt not in ("csv", "xlsx"):
        raise ValidationFailedError("format must be csv or xlsx")
    headers = list(rows[0].keys()) if rows else ["no_data"]
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: ("" if v is None else (v.value if hasattr(v, "value") else v)) for k, v in r.items()})
        data = buf.getvalue().encode("utf-8-sig")
        media = "text/csv"
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = title[:31]
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F3A5F")
        for r in rows:
            ws.append([_cell(r.get(h)) for h in headers])
        for idx, h in enumerate(headers, start=1):
            col = get_column_letter(idx)
            ws.column_dimensions[col].width = max(12, min(40, len(h) + 4))
            if rows and isinstance(rows[0].get(h), Decimal) and not h.endswith("pct"):
                for cell in ws[col][1:]:
                    cell.number_format = MONEY_FORMAT
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        out = io.BytesIO()
        wb.save(out)
        data = out.getvalue()
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return StreamingResponse(
        io.BytesIO(data), media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}.{fmt}"'},
    )
