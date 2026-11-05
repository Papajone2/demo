/** Satooshi Pro USB client. No secrets, PINs or seed words are requested or stored. */
export const USB_FILTER = Object.freeze({ usbVendorId: 0x1d6b, usbProductId: 0x0104 });

export function connectionErrorMessage(error) {
  if (error.name === 'NotFoundError') return 'No Satooshi Pro selected. If the list is empty, open Connection help below.';
  if (error.name === 'SecurityError') return 'Open this page in a separate desktop Chrome or Edge tab, not an embedded preview. Check the browser’s serial-device permissions.';
  if (error.name === 'NetworkError') return 'Could not open the USB port. Close other apps using the device and check Linux serial-port permissions in Connection help.';
  return error.message || 'USB connection failed. Open Connection help below.';
}

export class SatooshiDevice extends EventTarget {
  constructor() {
    super();
    this.pending = new Map();
    this.jobs = new Map();
    this.port = null;
    this.state = null;
  }
  notify(type, detail) { this.dispatchEvent(new CustomEvent(type, { detail })); }
  static supported() { return Boolean(globalThis.isSecureContext && navigator.serial); }
  async connect() {
    if (!SatooshiDevice.supported()) throw new Error('Open this page directly in desktop Chrome or Edge over HTTPS (or localhost).');
    if (this.port) throw new Error('A device is already connected.');
    try {
      const port = await navigator.serial.requestPort({ filters: [USB_FILTER] });
      const info = port.getInfo();
      if (info.usbVendorId !== USB_FILTER.usbVendorId || info.usbProductId !== USB_FILTER.usbProductId) {
        throw new Error('This is not the USB identity used by Satooshi Pro. Do not select a built-in serial port.');
      }
      await port.open({ baudRate: 115200 });
      this.port = port;
      this.writer = port.writable.getWriter();
      this.reader = port.readable.getReader();
      this.readTask = this.readLoop();
      const state = await this.request('hello');
      if (state.name !== 'Satooshi Pro' || !['0.1.0', '0.2.0'].includes(state.version)) throw new Error('Unexpected device or firmware version.');
      this.state = state;
      this.notify('state', state);
      this.heartbeat = setInterval(() => this.request('status').then(s => {
        this.state = s; this.notify('state', s);
      }).catch(error => this.disconnect(error.message)), 15000);
      return state;
    } catch (error) {
      await this.disconnect();
      throw new Error(connectionErrorMessage(error), { cause: error });
    }
  }
  async request(method, params = {}, id = crypto.randomUUID()) {
    if (!this.writer) throw new Error('Connect your device first.');
    const response = new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('Device did not respond. Check the USB data cable.')); }, 12000);
      this.pending.set(id, { resolve, reject, timer });
    });
    try {
      await this.writer.write(new TextEncoder().encode(JSON.stringify({ v: 1, id, method, params }) + '\n'));
    } catch (error) {
      const p = this.pending.get(id);
      if (p) { clearTimeout(p.timer); this.pending.delete(id); p.reject(error); }
    }
    return response;
  }
  async action(method, params = {}) {
    const id = crypto.randomUUID();
    const result = new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.jobs.delete(id);
        reject(new Error('Device approval timed out. Cancel on the device before retrying.'));
      }, 20 * 60 * 1000);
      this.jobs.set(id, { resolve, reject, timer });
    });
    // Install a handler immediately; an acknowledgement can fail before result is awaited.
    result.catch(() => {});
    try {
      await this.request(method, params, id);
      return await result;
    } catch (error) {
      const job = this.jobs.get(id);
      if (job) { clearTimeout(job.timer); this.jobs.delete(id); job.reject(error); }
      throw error;
    }
  }
  async readLoop() {
    let buffer = '';
    const decoder = new TextDecoder();
    try {
      while (this.reader) {
        const { done, value } = await this.reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        if (buffer.length > 65536) throw new Error('Invalid oversized device response.');
        let newline;
        while ((newline = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, newline); buffer = buffer.slice(newline + 1);
          if (!line.trim()) continue;
          const msg = JSON.parse(line);
          if (msg.event === 'state') {
            this.state = msg.data; this.notify('state', msg.data);
          } else if (msg.event === 'result') {
            const job = this.jobs.get(msg.data.requestId);
            if (job) {
              clearTimeout(job.timer); this.jobs.delete(msg.data.requestId);
              if (msg.data.result.cancelled) job.reject(new Error('Cancelled on device.'));
              else job.resolve(msg.data.result);
            }
            this.notify('result', msg.data);
          } else {
            const pending = this.pending.get(msg.id);
            if (pending) {
              clearTimeout(pending.timer); this.pending.delete(msg.id);
              if (msg.ok) pending.resolve(msg.result);
              else pending.reject(new Error(msg.error || 'Device rejected the request.'));
            }
          }
        }
      }
    } catch (error) {
      this.notify('error', error.message);
    } finally {
      // Schedule outside this read task to avoid awaiting ourselves.
      if (!this.closing) queueMicrotask(() => this.disconnect('USB disconnected.'));
    }
  }
  async disconnect(reason = 'Disconnected') {
    if (this.closing) return;
    this.closing = true;
    clearInterval(this.heartbeat);
    for (const map of [this.pending, this.jobs]) {
      for (const p of map.values()) { clearTimeout(p.timer); p.reject(new Error(reason)); }
      map.clear();
    }
    const reader = this.reader, writer = this.writer, port = this.port;
    this.reader = this.writer = this.port = null;
    if (reader) { try { await reader.cancel(); reader.releaseLock(); } catch {} }
    if (writer) { try { writer.releaseLock(); } catch {} }
    if (port) { try { await port.close(); } catch {} }
    this.state = null;
    this.closing = false;
    this.notify('disconnected', reason);
  }
}

export const NETWORKS = {
  '11155111': { name: 'Sepolia (test ETH)', rpc: 'https://ethereum-sepolia-rpc.publicnode.com', explorer: 'https://sepolia.etherscan.io/tx/' },
  '1': { name: 'Ethereum (real ETH)', rpc: 'https://ethereum-rpc.publicnode.com', explorer: 'https://etherscan.io/tx/' },
};
export function parseEther(value) {
  if (!/^(0|[1-9]\d*)(\.\d{1,18})?$/.test(value)) throw new Error('Enter an ETH amount with at most 18 decimal places.');
  const [whole, fraction = ''] = value.split('.');
  const wei = BigInt(whole) * 10n ** 18n + BigInt(fraction.padEnd(18, '0'));
  if (wei <= 0n || wei >= 2n ** 256n) throw new Error('Enter a positive amount within uint256.');
  return wei;
}
async function rpc(chain, method, params) {
  const network = NETWORKS[String(chain)];
  if (!network) throw new Error('Unsupported network.');
  const response = await fetch(network.rpc, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
    signal: AbortSignal.timeout(20000),
  });
  if (!response.ok) throw new Error('Network provider unavailable (' + response.status + ').');
  const result = await response.json();
  if (result.error) throw new Error(result.error.message || 'RPC request failed.');
  if (result.result === undefined) throw new Error('Provider returned no result.');
  return result.result;
}
export async function prepareTransfer({ chainId, from, to, amount }) {
  if (!/^0x[0-9a-fA-F]{40}$/.test(from) || !/^0x[0-9a-fA-F]{40}$/.test(to)) throw new Error('Enter a valid Ethereum address.');
  const value = parseEther(amount);
  const [actualChain, nonce, code, block, priority, balance] = await Promise.all([
    rpc(chainId, 'eth_chainId', []),
    rpc(chainId, 'eth_getTransactionCount', [from, 'pending']),
    rpc(chainId, 'eth_getCode', [to, 'latest']),
    rpc(chainId, 'eth_getBlockByNumber', ['latest', false]),
    rpc(chainId, 'eth_maxPriorityFeePerGas', []),
    rpc(chainId, 'eth_getBalance', [from, 'pending']),
  ]);
  if (BigInt(actualChain).toString() !== String(chainId)) throw new Error('Provider returned the wrong chain.');
  if (code !== '0x') throw new Error('Contract recipients are not supported by this prototype.');
  if (!block.baseFeePerGas) throw new Error('Provider did not return EIP-1559 fees.');
  const maxPriorityFeePerGas = BigInt(priority);
  const maxFeePerGas = BigInt(block.baseFeePerGas) * 2n + maxPriorityFeePerGas;
  if (BigInt(balance) < value + maxFeePerGas * 21000n) throw new Error('Not enough ETH for this amount and the maximum network fee.');
  return {
    chainId: String(chainId), nonce: BigInt(nonce).toString(), to,
    value: value.toString(), gasLimit: '21000',
    maxPriorityFeePerGas: maxPriorityFeePerGas.toString(), maxFeePerGas: maxFeePerGas.toString(),
  };
}
export async function broadcastTransfer(signed) {
  if (!NETWORKS[String(signed.chainId)] || !/^0x02[0-9a-f]+$/i.test(signed.rawTransaction)) throw new Error('Invalid signed transfer.');
  // One attempt only: timeout is an UNKNOWN outcome, never a reason to resend automatically.
  const hash = await rpc(signed.chainId, 'eth_sendRawTransaction', [signed.rawTransaction]);
  if (hash.toLowerCase() !== signed.transactionHash.toLowerCase()) throw new Error('Provider returned an unexpected transaction hash. Check the explorer; do not resend.');
  return hash;
}
export async function transactionReceipt(chainId, hash) {
  return rpc(chainId, 'eth_getTransactionReceipt', [hash]);
}
