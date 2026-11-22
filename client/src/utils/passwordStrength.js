export function isStrongOnboardingPassword(password) {
  if (typeof password !== 'string') return false;
  const bytes = new TextEncoder().encode(password).length;
  return bytes >= 12 && bytes <= 72
    && /[a-z]/.test(password)
    && /[A-Z]/.test(password)
    && /\d/.test(password)
    && Array.from(password).some((character) => !/[\p{L}\p{N}]/u.test(character));
}

export const ONBOARDING_PASSWORD_REQUIREMENTS =
  'Use 12–72 UTF-8 bytes with uppercase and lowercase letters, a number, and a symbol.';
