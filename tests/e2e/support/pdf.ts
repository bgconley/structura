import {writeFile} from "node:fs/promises";

export async function writeSimplePdf(filePath: string, lines: string[]): Promise<void> {
  const textStream = [
    "BT",
    "/F1 14 Tf",
    "18 TL",
    "72 720 Td",
    ...lines.flatMap((line, index) => [
      index === 0 ? "" : "T*",
      `(${escapePdfText(line)}) Tj`,
    ]).filter(Boolean),
    "ET",
  ].join("\n");

  const objects = [
    "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
    "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
    [
      "3 0 obj",
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]",
      "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
      "endobj",
      "",
    ].join("\n"),
    "4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    [
      "5 0 obj",
      `<< /Length ${Buffer.byteLength(textStream, "ascii")} >>`,
      "stream",
      textStream,
      "endstream",
      "endobj",
      "",
    ].join("\n"),
  ];

  let body = "%PDF-1.4\n";
  const offsets = objects.map((pdfObject) => {
    const offset = Buffer.byteLength(body, "ascii");
    body += pdfObject;
    return offset;
  });
  const xrefOffset = Buffer.byteLength(body, "ascii");
  body += `xref\n0 ${objects.length + 1}\n`;
  body += "0000000000 65535 f \n";
  body += offsets.map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("");
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\n`;
  body += `startxref\n${xrefOffset}\n%%EOF\n`;

  await writeFile(filePath, body, "ascii");
}

function escapePdfText(value: string): string {
  return value.replaceAll("\\", "\\\\").replaceAll("(", "\\(").replaceAll(")", "\\)");
}
