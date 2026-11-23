import assert from 'node:assert/strict';
import { test } from 'node:test';
import { isStrongOnboardingPassword } from '../src/utils/passwordStrength.js';

test('onboarding passwords must satisfy every server-side strength rule', () => {
  assert.equal(isStrongOnboardingPassword('ValidOnboarding!9'), true);
  assert.equal(isStrongOnboardingPassword('short!9A'), false);
  assert.equal(isStrongOnboardingPassword('alllowercasepassword!9'), false);
  assert.equal(isStrongOnboardingPassword('NoDigitsOrSymbol'), false);
  assert.equal(isStrongOnboardingPassword(`Ab9!${'x'.repeat(70)}`), false);
});
