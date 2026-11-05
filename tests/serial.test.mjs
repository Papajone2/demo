import test from 'node:test';
import assert from 'node:assert/strict';
import { SatooshiDevice, parseEther, NETWORKS, USB_FILTER, connectionErrorMessage } from '../web/serial.js';

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

async function withSerialMock(serial, fn) {
  const originals = ['navigator', 'isSecureContext'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]);
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { serial } });
  Object.defineProperty(globalThis, 'isSecureContext', { configurable: true, value: true });
  try { await fn(); }
  finally {
    for (const [key, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  }
}

test('connection chooser filters unrelated UART ports and handshakes with firmware', async () => {
  let receivedFilter, input, closed = false;
  const port = {
    getInfo: () => ({ ...USB_FILTER }),
    open: async options => assert.equal(options.baudRate, 115200),
    close: async () => { closed = true; },
    readable: new ReadableStream({ start(controller) { input = controller; } }),
    writable: new WritableStream({ write(bytes) {
      const request = JSON.parse(new TextDecoder().decode(bytes));
      input.enqueue(new TextEncoder().encode(JSON.stringify({
        v: 1, id: request.id, ok: true,
        result: { name: 'Satooshi Pro', version: '0.1.0', configured: false, locked: true, phase: 'home' },
      }) + '\n'));
    } }),
  };
  await withSerialMock({ requestPort: async options => { receivedFilter = options; return port; } }, async () => {
    const client = new SatooshiDevice();
    try {
      const state = await client.connect();
      assert.deepEqual(receivedFilter, { filters: [{ usbVendorId: 0x1d6b, usbProductId: 0x0104 }] });
      assert.equal(state.name, 'Satooshi Pro');
    } finally { await client.disconnect(); }
    assert.equal(closed, true);
    assert.equal(client.pending.size, 0);
  });
});

test('unexpected USB identity is rejected before opening any port', async () => {
  let opened = false;
  await withSerialMock({ requestPort: async () => ({
    getInfo: () => ({ usbVendorId: 1234, usbProductId: 5678 }),
    open: async () => { opened = true; },
  }) }, async () => {
    await assert.rejects(new SatooshiDevice().connect(), /not the USB identity/);
    assert.equal(opened, false);
  });
});

test('empty or cancelled chooser gives connection help instead of silently failing', async () => {
  await withSerialMock({ requestPort: async () => { throw new DOMException('No port selected', 'NotFoundError'); } }, async () => {
    const client = new SatooshiDevice();
    await assert.rejects(client.connect(), /Connection help/);
    assert.equal(client.port, null);
  });
});

test('permission and browser policy errors explain the appropriate recovery', () => {
  assert.match(connectionErrorMessage({ name: 'SecurityError' }), /separate desktop/);
  assert.match(connectionErrorMessage({ name: 'NetworkError' }), /Linux serial-port permissions/);
  assert.equal(connectionErrorMessage(new Error('Unexpected firmware')), 'Unexpected firmware');
});
