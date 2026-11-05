/** Table export helpers. Exports always contain every filtered row, not just the
 *  rows currently rendered by the virtualiser. */

export type CellValue = string | number | boolean | Date | null | undefined;

export interface ExportColumn {
  header: string;
  type?: "string" | "number" | "date" | "boolean";
}

function csvCell(value: CellValue): string {
  if (value === null || value === undefined) return "";
  const text = value instanceof Date ? value.toISOString().slice(0, 10) : String(value);
  return /[",\r\n]/.test(text) || /^\s|\s$/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** RFC 4180 CSV with CRLF line endings. */
export function toCsv(columns: ExportColumn[], rows: CellValue[][]): string {
  const lines = [columns.map((c) => csvCell(c.header)).join(",")];
  for (const row of rows) lines.push(row.map(csvCell).join(","));
  return lines.join("\r\n") + "\r\n";
}

/** CSV as a Blob with a UTF-8 BOM so Excel opens ₹, µ and Ω correctly. */
export function csvBlob(columns: ExportColumn[], rows: CellValue[][]): Blob {
  return new Blob(["﻿", toCsv(columns, rows)], { type: "text/csv;charset=utf-8" });
}

export async function xlsxBlob(columns: ExportColumn[], rows: CellValue[][], sheet = "Export"): Promise<Blob> {
  const { default: writeXlsxFile } = await import("write-excel-file/universal");
  const header = columns.map((c) => ({ value: c.header, fontWeight: "bold" as const }));
  const body = rows.map((row) =>
    row.map((value, i) => {
      if (value === null || value === undefined || value === "") return null;
      const type = columns[i]?.type;
      if (type === "number" && typeof value === "number") return { type: Number, value };
      if (type === "date" && value instanceof Date) return { type: Date, value, format: "dd mmm yyyy" };
      if (typeof value === "boolean") return { type: Boolean, value };
      return { type: String, value: value instanceof Date ? value.toISOString().slice(0, 10) : String(value) };
    }),
  );
  return writeXlsxFile([header, ...body], { sheet, stickyRowsCount: 1 }).toBlob();
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
