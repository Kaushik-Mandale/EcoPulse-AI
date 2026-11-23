import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildProfileUpdatePayload } from '../src/utils/profilePayload.js';

const formData = { full_name: '  Updated Name  ', ward: '  Ward B  ', phone: '  9876543210  ' };

test('profile payload includes ward only for citizens', () => {
  assert.deepEqual(buildProfileUpdatePayload({ role: 'citizen' }, formData), {
    full_name: 'Updated Name',
    phone: '9876543210',
    ward: 'Ward B',
  });

  for (const role of ['driver', 'admin', 'collector']) {
    assert.deepEqual(buildProfileUpdatePayload({ role }, formData), {
      full_name: 'Updated Name',
      phone: '9876543210',
    });
  }
});
