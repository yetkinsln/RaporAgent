import type { CropSelection } from "./types";

// Sunucu 20 pikselden küçük kırpmayı kabul etmez. Yuvarlama farklarının
// kullanıcıya hata olarak dönmemesi için arayüz biraz daha büyük bir eşik kullanır.
export const MINIMUM_CROP_PIXELS = 24;

type CropPoint = { x: number; y: number };

export function cropPointFromSvg(svg: SVGSVGElement, clientX: number, clientY: number): CropPoint {
  const viewBox = svg.viewBox.baseVal;
  const matrix = svg.getScreenCTM();

  if (matrix && viewBox.width > 0 && viewBox.height > 0) {
    const point = new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
    return {
      x: clamp(point.x / viewBox.width),
      y: clamp(point.y / viewBox.height),
    };
  }

  // Eski/eksik SVG API'leri için güvenli geri dönüş. Bu yol normal tarayıcılarda
  // kullanılmaz, ancak seçim yine sayfanın görünür alanında kalır.
  const bounds = svg.getBoundingClientRect();
  return {
    x: bounds.width > 0 ? clamp((clientX - bounds.left) / bounds.width) : 0,
    y: bounds.height > 0 ? clamp((clientY - bounds.top) / bounds.height) : 0,
  };
}

export function normaliseCrop(
  crop: CropSelection,
  width: number | null | undefined,
  height: number | null | undefined,
): CropSelection | null {
  if (!width || !height) return null;

  const left = Math.min(crop.left, crop.right);
  const right = Math.max(crop.left, crop.right);
  const top = Math.min(crop.top, crop.bottom);
  const bottom = Math.max(crop.top, crop.bottom);

  return (right - left) * width >= MINIMUM_CROP_PIXELS && (bottom - top) * height >= MINIMUM_CROP_PIXELS
    ? { left, top, right, bottom }
    : null;
}

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value));
}
