import { describe, expect, it } from "vitest";
import { getTitleUrl } from "../src/utils/titleRoute";

describe("getTitleUrl", () => {
  it("builds canonical movie and TV routes", () => {
    expect(getTitleUrl({ media_type: "movie", serial_number: "000001" })).toBe(
      "/movie/000001/",
    );
    expect(getTitleUrl({ media_type: "tv", serial_number: "000025" })).toBe(
      "/tv/000025/",
    );
  });

  it("rejects unsupported media types and non-serial values", () => {
    expect(() =>
      getTitleUrl({ media_type: "anime", serial_number: "000001" }),
    ).toThrow("Unsupported media type");
    expect(() =>
      getTitleUrl({
        media_type: "movie",
        serial_number: "title_01a1fa12-6bdf-7c88-859d-1d770d239359",
      }),
    ).toThrow("Invalid title serial number");
    expect(() =>
      getTitleUrl({ media_type: "tv", serial_number: "25" }),
    ).toThrow("Invalid title serial number");
  });
});
