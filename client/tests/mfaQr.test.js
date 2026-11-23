import test from 'node:test';
import assert from 'node:assert/strict';
import { createMfaQrDataUrl } from '../src/utils/mfaQr.js';

test('MFA enrollment QR is encoded locally as a PNG data URL', async () => {
  const image = await createMfaQrDataUrl(
    'otpauth://totp/EcoPulse%20AI:SUP-LOCAL-TEST?secret=TESTSECRET&issuer=EcoPulse%20AI&digits=6&period=30',
  );
  assert.match(image, /^data:image\/png;base64,/);
  assert.equal(image.includes('TESTSECRET'), false);
});
