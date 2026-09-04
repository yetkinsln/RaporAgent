import { describe, expect, it } from "vitest";
import { inputToFieldValue, maskTckn } from "./field-utils";

describe("field presentation", () => {
  it("masks TCKN by default", () => {
    expect(maskTckn("10000000146", "patient.tckn")).toBe("•••••••0146");
  });

  it("keeps multi-value corrections as an array", () => {
    expect(inputToFieldValue("Birinci husus\nİkinci husus", true)).toEqual(["Birinci husus", "İkinci husus"]);
  });
});
