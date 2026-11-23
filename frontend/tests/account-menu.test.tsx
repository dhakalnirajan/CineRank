import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AccountMenu } from "../src/components/navigation/AccountMenu";
import { renderWithProviders } from "./test-utils";

function renderMenu(onSignOut = vi.fn()) {
  return renderWithProviders(
    <AccountMenu
      username="ada lovelace"
      email="ada@example.com"
      onSignOut={onSignOut}
    />,
    { route: "/" },
  );
}

describe("AccountMenu", () => {
  it("keeps the username out of the navbar until the avatar is opened", async () => {
    const user = userEvent.setup();
    renderMenu();

    expect(screen.queryByText("ada lovelace")).not.toBeInTheDocument();

    const trigger = screen.getByRole("button", {
      name: "Account menu for ada lovelace",
    });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("ada lovelace")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Profile" })).toHaveAttribute(
      "href",
      "/profile",
    );
    expect(screen.getByRole("link", { name: "Watchlist" })).toHaveAttribute(
      "href",
      "/watchlist",
    );
    expect(screen.getByRole("link", { name: "Rating history" })).toHaveAttribute(
      "href",
      "/history",
    );
  });

  it("stays closed on hover and stays open after the pointer leaves a click", async () => {
    const user = userEvent.setup();
    renderMenu();

    const trigger = screen.getByRole("button", {
      name: "Account menu for ada lovelace",
    });

    await user.hover(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    await user.unhover(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("ada@example.com")).not.toBeInTheDocument();
  });

  it("closes on Escape and signs out from the menu", async () => {
    const user = userEvent.setup();
    const onSignOut = vi.fn();
    renderMenu(onSignOut);

    const trigger = screen.getByRole("button", {
      name: "Account menu for ada lovelace",
    });

    fireEvent.click(trigger);
    await user.keyboard("{Escape}");
    expect(screen.queryByText("ada@example.com")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();

    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });
});
