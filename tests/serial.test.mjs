import test from 'node:test';
import assert from 'node:assert/strict';
import { SatooshiDevice, parseEther, NETWORKS } from '../web/serial.js';

test('decimal amounts preserve precision', () => {
  assert.equal(parseEther('1.000000000000000001'), 1000000000000000001n);
  assert.equal(parseEther('0.000000000000000001'), 1n);
});
test('reject ambiguous, negative, zero and excessive precision', () => {
  for (const value of ['0', '-1', '1e9', '01', '1.', 'NaN', '1.0000000000000000001', 'Infinity', ' 1']) {
    assert.throws(() => parseEther(value));
  }
});
test('only explicitly implemented networks are advertised', () => {
  assert.deepEqual(Object.keys(NETWORKS).sort(), ['1', '11155111']);
});
test('disconnected client fails explicitly, never simulates approval', async () => {
  const client = new SatooshiDevice();
  await assert.rejects(client.request('get_address'), /Connect your device/);
  await assert.rejects(client.action('setup'), /Connect your device/);
  assert.equal(client.jobs.size, 0);
});
test('acknowledgement alone is not a physical approval', async () => {
  const client = new SatooshiDevice();
  client.request = async () => ({ accepted: true });
  let completed = false;
  const pending = client.action('get_address').then(() => { completed = true; });
  await new Promise(resolve => setTimeout(resolve, 5));
  assert.equal(completed, false);
  const [id, job] = [...client.jobs.entries()][0];
  clearTimeout(job.timer);
  client.jobs.delete(id);
  job.resolve({ address: 'public-test-fixture' });
  await pending;
  assert.equal(completed, true);
});
