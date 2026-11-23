import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ScrollRow } from "../src/components/media/ScrollRow";

function renderRow(onNearEnd: () => void) {
  const { container } = render(
    <ScrollRow title="For you" onNearEnd={onNearEnd}>
      <div>Card</div>
    </ScrollRow>,
  );
  const scroller = container.querySelector<HTMLElement>(".overflow-x-auto");
  if (!scroller) {
    throw new Error("Rail scroller was not rendered");
  }
  return scroller;
}

function setGeometry(scroller: HTMLElement, scrollWidth: number, scrollLeft: number) {
  Object.defineProperty(scroller, "scrollWidth", { configurable: true, value: scrollWidth });
  Object.defineProperty(scroller, "clientWidth", { configurable: true, value: 1000 });
  Object.defineProperty(scroller, "scrollLeft", {
    configurable: true,
    value: scrollLeft,
    writable: true,
  });
}

describe("rail prefetch", () => {
  it("requests more while one viewport still remains", async () => {
    const onNearEnd = vi.fn();
    const scroller = renderRow(onNearEnd);
    setGeometry(scroller, 2400, 500);

    fireEvent.scroll(scroller);

    await waitFor(() => expect(onNearEnd).toHaveBeenCalledTimes(1));
  });

  it("stays quiet while the reader is far from the end", async () => {
    const onNearEnd = vi.fn();
    const scroller = renderRow(onNearEnd);
    setGeometry(scroller, 4000, 0);

    fireEvent.scroll(scroller);
    await new Promise((resolve) => setTimeout(resolve, 30));

    expect(onNearEnd).not.toHaveBeenCalled();
  });
});
