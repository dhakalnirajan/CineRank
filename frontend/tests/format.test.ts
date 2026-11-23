import { describe, expect, it } from "vitest";
import { displayTitle } from "../src/utils/displayTitle";
import {
  formatRuntime,
  isRenderableImageUrl,
  parseGenres,
  parsePeople,
  recommendationReason,
} from "../src/utils/format";

describe("catalogue metadata parsing", () => {
  it("splits delimited genres and removes duplicates", () => {
    expect(parseGenres("Drama|Mystery|drama")).toEqual(["Drama", "Mystery"]);
    expect(parseGenres("")).toEqual([]);
    expect(parseGenres(null)).toEqual([]);
  });

  it("normalizes trailing library articles for display", () => {
    expect(displayTitle({ title: "Matrix, The (1999)" })).toBe("The Matrix");
    expect(displayTitle({ title: "'burbs, The (1989)" })).toBe("The 'burbs");
    expect(displayTitle({ title: "10,000 BC (2008)" })).toBe("10,000 BC");
    expect(
      displayTitle({ title: "Matrix, The (1999)", display_title: "The Matrix (1999)" }),
    ).toBe("The Matrix");
  });

  it("parses director and cast JSON defensively", () => {
    expect(parsePeople('["Ada Lovelace", {"name":"Grace Hopper","character":"Self"}]')).toEqual([
      { name: "Ada Lovelace", role: null },
      { name: "Grace Hopper", role: "Self" },
    ]);
    expect(parsePeople("{not json")).toEqual([]);
    expect(parsePeople('{"name":"Not an array"}')).toEqual([]);
    expect(parsePeople(null)).toEqual([]);
  });

  it("only accepts absolute http image URLs", () => {
    expect(isRenderableImageUrl("https://image.tmdb.org/poster.jpg")).toContain(
      "https://image.tmdb.org/poster.jpg",
    );
    expect(isRenderableImageUrl("/relative.jpg")).toBeNull();
    expect(isRenderableImageUrl("javascript:alert(1)")).toBeNull();
    expect(isRenderableImageUrl(null)).toBeNull();
  });

  it("formats runtime without inventing missing values", () => {
    expect(formatRuntime(95)).toBe("1 hr 35 min");
    expect(formatRuntime(120)).toBe("2 hr");
    expect(formatRuntime(45)).toBe("45 min");
    expect(formatRuntime(null)).toBeNull();
    expect(formatRuntime(0)).toBeNull();
  });

  it("turns reason sources into plain-language copy", () => {
    expect(recommendationReason("rank-fusion; sources=popular+content")).toBe(
      "Picked from popular titles and your taste.",
    );
    expect(recommendationReason("rank-fusion")).toBe("Picked for you.");
    expect(recommendationReason(null)).toBeNull();
  });
});
