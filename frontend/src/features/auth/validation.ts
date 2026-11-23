export interface AuthFieldErrors {
  username?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
}

const USERNAME_PATTERN = /^[A-Za-z0-9_.-]{3,64}$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateLogin(username: string, password: string): AuthFieldErrors {
  const errors: AuthFieldErrors = {};
  if (!username.trim()) {
    errors.username = "Enter your username.";
  }
  if (!password) {
    errors.password = "Enter your password.";
  }
  return errors;
}

export function validateRegistration(input: {
  username: string;
  email: string;
  password: string;
  confirmPassword: string;
}): AuthFieldErrors {
  const errors: AuthFieldErrors = {};
  if (!USERNAME_PATTERN.test(input.username)) {
    errors.username =
      "Use 3 to 64 characters: letters, numbers, dots, underscores, or hyphens.";
  }
  if (input.email.trim() && !EMAIL_PATTERN.test(input.email.trim())) {
    errors.email = "Enter a valid email address.";
  }
  if (input.password.length < 12) {
    errors.password = "Use at least 12 characters.";
  }
  if (input.confirmPassword !== input.password) {
    errors.confirmPassword = "Passwords do not match.";
  }
  return errors;
}

export function hasErrors(errors: AuthFieldErrors): boolean {
  return Object.values(errors).some(Boolean);
}
