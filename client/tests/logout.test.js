import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const authServiceSource = readFileSync(new URL('../src/services/authService.js', import.meta.url), 'utf8');

test('logout clears browser credentials and revokes the captured server session', async () => {
  const values = new Map([
    ['ecopulse_token', 'test-session-token'],
    ['ecopulse_user', '{"role":"driver"}'],
  ]);
  globalThis.localStorage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };

  let request;
  const api = { post: async (...args) => {
    request = args;
    assert.equal(localStorage.getItem('ecopulse_token'), null);
    return { data: { success: true } };
  } };
  const implementation = authServiceSource.match(/export const logoutUser = \(\) => \{([\s\S]*?)\n\};/);
  assert.ok(implementation, 'logoutUser should remain available in the shared auth service');
  const logoutUser = new Function('localStorage', 'api', `return () => {${implementation[1]}\n};`)(localStorage, api);

  assert.equal(await logoutUser(), true);
  assert.equal(localStorage.getItem('ecopulse_user'), null);
  assert.equal(request[0], '/auth/logout');
  assert.equal(request[2].headers.Authorization, 'Bearer test-session-token');
});
