import { describe, expect, it } from "vitest";

import schema from "../../schemas/case-extraction.schema.json";
import { GROUPS } from "./App";

describe("doğrulama paneli alan kapsamı", () => {
  it("kanonik hasta, üst yazı ve tıbbi alanların tamamını tam bir kez gösterir", () => {
    const visible = GROUPS.flatMap((group) => group.fields.map((field) => `${group.key}.${field}`));
    const canonical = (["patient", "request", "medical"] as const).flatMap((group) =>
      Object.keys(schema.properties[group].properties).map((field) => `${group}.${field}`),
    );

    expect(new Set(visible).size).toBe(visible.length);
    expect([...visible].sort()).toEqual([...canonical].sort());
  });
});
