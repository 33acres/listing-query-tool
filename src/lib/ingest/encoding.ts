import Encoding from "encoding-japanese";

export interface DecodedBuffer {
  text: string;
  encoding: string;
}

export function decodeCsvBuffer(buffer: ArrayBuffer): DecodedBuffer {
  const bytes = new Uint8Array(buffer);
  const detected = Encoding.detect(bytes) || "UTF8";
  const normalized = detected.toUpperCase().replace(/[_-]/g, "");

  if (normalized === "UTF8" || normalized === "ASCII") {
    const offset =
      bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf ? 3 : 0;
    return {
      text: new TextDecoder("utf-8", { fatal: false }).decode(bytes.slice(offset)),
      encoding: offset === 3 ? "UTF-8 BOM" : "UTF-8",
    };
  }

  if (normalized === "UTF16" || normalized === "UNICODE") {
    return {
      text: new TextDecoder("utf-16le", { fatal: false }).decode(bytes),
      encoding: "UTF-16LE",
    };
  }

  return {
    text: Encoding.convert(bytes, {
      to: "UNICODE",
      from: detected,
      type: "string",
    }),
    encoding: detected === "SJIS" ? "Shift_JIS" : detected,
  };
}
