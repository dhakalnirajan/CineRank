import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { tokenStore } from "../src/api/token";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  tokenStore.clear();
});
