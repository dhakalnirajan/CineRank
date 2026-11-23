import { describe, expect, it } from "vitest";
import {
  hasErrors,
  validateLogin,
  validateRegistration,
} from "../src/features/auth/validation";

describe("authentication validation", () => {
  it("requires credentials for sign in", () => {
    const errors = validateLogin("", "");
    expect(errors.username).toBeDefined();
    expect(errors.password).toBeDefined();
    expect(hasErrors(errors)).toBe(true);
  });

  it("matches backend registration constraints", () => {
    const errors = validateRegistration({
      username: "ab",
      email: "not-an-email",
      password: "short",
      confirmPassword: "different",
    });

    expect(errors.username).toContain("3 to 64");
    expect(errors.email).toBeDefined();
    expect(errors.password).toContain("12");
    expect(errors.confirmPassword).toBeDefined();
  });

  it("accepts a valid registration payload", () => {
    const errors = validateRegistration({
      username: "ada.lovelace",
      email: "",
      password: "longpassword123",
      confirmPassword: "longpassword123",
    });

    expect(hasErrors(errors)).toBe(false);
  });
});
