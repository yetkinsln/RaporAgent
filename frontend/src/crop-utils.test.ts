import { describe, expect, it } from "vitest";

import { MINIMUM_CROP_PIXELS, normaliseCrop } from "./crop-utils";

describe("kırpma seçimi", () => {
  it("ters yönde sürüklenen seçimi sayfa koordinatlarına göre normalleştirir", () => {
    expect(normaliseCrop(
      { left: 0.9, top: 0.8, right: 0.1, bottom: 0.2 },
      1_000,
      900,
    )).toEqual({ left: 0.1, top: 0.2, right: 0.9, bottom: 0.8 });
  });

  it("sunucuda hata vermeden önce çok küçük seçimleri uygula düğmesinden engeller", () => {
    const tooNarrow = (MINIMUM_CROP_PIXELS - 1) / 1_000;
    expect(normaliseCrop({ left: 0.1, top: 0.1, right: 0.1 + tooNarrow, bottom: 0.9 }, 1_000, 900)).toBeNull();
  });
});
