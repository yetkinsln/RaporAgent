import type { FieldValue } from "./types";

export function displayValue(value: FieldValue): string {
  if (value === null) return "Kaynakta bulunamadı";
  return Array.isArray(value) ? value.join("\n") : value;
}

export function maskTckn(value: FieldValue, fieldPath: string): string {
  const displayed = displayValue(value);
  if (fieldPath !== "patient.tckn" || value === null) return displayed;
  return displayed.length < 4 ? "••••" : `${"•".repeat(displayed.length - 4)}${displayed.slice(-4)}`;
}

export function inputToFieldValue(raw: string, arrayValue: boolean): FieldValue {
  if (!raw.trim()) return null;
  return arrayValue ? raw.split("\n").map((entry) => entry.trim()).filter(Boolean) : raw.trim();
}
