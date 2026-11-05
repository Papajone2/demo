import { SatooshiDevice, NETWORKS, prepareTransfer, broadcastTransfer, transactionReceipt } from './serial.js';

const $ = id => document.getElementById(id);
const device = new SatooshiDevice();
const S = { state: null, address: null, busy: null, prepared: null, signed: null, sent: null, connecting: false, watch: 0 };

const ACTION_COPY = {
  setup: 'Creating your wallet. Write the 24 words on paper from the device screen, then pass the backup check.',
  unlock: 'Hold right to confirm on current firmware (both buttons on older firmware), then enter your PIN there if set.',
  get_address: 'Compare the full address on the device screen, then hold right to confirm (both buttons on older firmware).',
  review_transfer: 'Read every page on the device. Confirm only if network, address, amount and fee match.',
  reset: 'The device asks you twice. Reject with A if you are unsure.',
  show_message: 'A labeled computer message is on the device screen. Dismiss it there.',
};
const LABEL = { setup: 'Setting up', unlock: 'Unlocking', get_address: 'Verifying address', review_transfer: 'Reviewing transfer', reset: 'Resetting', show_message: 'Showing message' };

function formatEth(wei) {
  const w = BigInt(wei), whole = w / 10n ** 18n;
  const frac = (w % 10n ** 18n).toString().padStart(18, '0').replace(/0+$/, '');
  return whole + (frac ? '.' + frac : '');
}
const PHASE = { home: 'Home', setup_confirm: 'Confirm new wallet', backup: 'Writing down recovery words', quiz: 'Backup check', pin_choice: 'Choosing PIN option', no_pin_confirm: 'Confirm no PIN', pin: 'PIN entry', unlock_confirm: 'Confirm unlock', address: 'Address on screen', review: 'Reviewing transfer', reset: 'Reset confirmation', message: 'Computer message' };
const IDLE = ['home', 'idle', 'ready', 'locked'];
const deviceBusy = st => !!st && !!st.phase && !IDLE.includes(st.phase);
const humanize = s => String(s || '').replace(/[_-]+/g, ' ').replace(/^./, c => c.toUpperCase());
const chainId = () => document.querySelector('input[name=net]:checked').value;
function showErr(el, msg) { el.textContent = msg || ''; el.hidden = !msg; }

function clearSession() {
  S.address = null; S.prepared = null; S.signed = null;
}
function invalidate() {
  S.prepared = null; S.signed = null;
  render();
}

function render() {
  const st = S.state, connected = !!st, busy = !!S.busy || deviceBusy(S.state);
  const supported = SatooshiDevice.supported();
  $('unsupported').hidden = supported;

  const pill = $('connPill');
  if (S.connecting) { pill.dataset.tone = 'busy'; pill.textContent = 'Connecting'; }
  else if (!connected) { pill.dataset.tone = pill.dataset.tone === 'bad' ? 'bad' : 'idle'; pill.textContent = pill.dataset.tone === 'bad' ? 'Disconnected' : 'Not connected'; }
  else if (busy) { pill.dataset.tone = 'busy'; pill.textContent = 'Waiting for you'; }
  else { pill.dataset.tone = 'ok'; pill.textContent = st.locked ? 'Connected, locked' : 'Connected'; }

  const pi = document.querySelector('.pi');
  pi.dataset.s = busy ? 'busy' : connected ? 'on' : 'off';
  $('screenLabel').textContent = busy ? 'look here' : connected ? (st.configured ? (st.locked ? 'locked' : 'ready') : 'new') : 'offline';

  $('facts').hidden = !connected;
  if (connected) {
    $('fVersion').textContent = st.version;
    $('fConfigured').textContent = st.configured ? 'Created' : 'Not set up';
    $('fLocked').textContent = st.configured ? (st.locked ? 'Locked' : 'Unlocked') : '—';
    $('fAttempts').textContent = st.configured ? (st.attemptsRemaining ?? 5) + ' of 5' + (st.pinEnabled ? '' : ' (no PIN)') : '5 of 5';
  }

  const phaseBusy = busy;
  $('progress').hidden = !phaseBusy;
  if (phaseBusy) {
    const ph = st && !IDLE.includes(st.phase) ? (PHASE[st.phase] || humanize(st.phase)) : '';
    $('phaseText').textContent = S.busy ? LABEL[S.busy] + (ph ? ' · ' + ph : '') : (ph || 'Working');
    const steps = Number(st?.steps) || 0, step = Number(st?.step) || 0;
    const shown = steps ? Math.min(step + 1, steps) : 0;
    $('stepText').textContent = steps ? (st.phase === 'backup' ? `Word ${shown} of ${steps}` : `Page ${shown} of ${steps}`) : '';
    $('barFill').style.transform = `scaleX(${steps ? shown / steps : 0.08})`;
    $('actionHint').textContent = ACTION_COPY[S.busy] || 'The device is in the middle of a flow. Finish it there, or send a cancellation request.';
  }
  const devErr = connected && st.error ? humanize(st.error) : '';
  if (devErr) showErr($('devError'), devErr);

  $('connectBtn').hidden = connected;
  $('connectBtn').disabled = !supported || S.connecting;
  $('connectBtn').textContent = S.connecting ? 'Choose your device…' : (pill.dataset.tone === 'bad' ? 'Reconnect device' : 'Connect device');
  $('setupBtn').hidden = !(connected && !st.configured && st.phase === 'home');
  $('unlockBtn').hidden = !(connected && st.configured && st.locked);
  $('addressBtn').hidden = !(connected && st.configured && !st.locked);
  $('addressBtn').textContent = S.address ? 'Show address on device again' : 'Show and verify address';
  $('pingBtn').hidden = !connected;
  $('lockBtn').hidden = !(connected && st.configured && !st.locked);
  $('disconnectBtn').hidden = !connected;
  for (const id of ['setupBtn', 'unlockBtn', 'addressBtn', 'pingBtn', 'lockBtn', 'resetBtn']) $(id).disabled = busy || !connected;
  $('resetBtn').disabled = busy || !connected || !st.configured;

  const unlocked = connected && st.configured && !st.locked;
  $('cancelBtn').disabled = !connected;
  const canSend = unlocked && !!S.address;
  $('verifiedBox').hidden = !canSend;
  $('verifiedAddr').textContent = S.address || '';
  $('addrPill').dataset.tone = canSend ? 'ok' : 'idle';
  $('addrPill').textContent = canSend ? 'Address verified' : 'Address not verified';
  $('sendLocked').hidden = canSend;
  const done = { connect: connected, setup: connected && st.configured && !st.locked, address: canSend, send: !!S.signed || !!S.sent };
  document.querySelectorAll('#journey li').forEach(li => li.classList.toggle('done', !!done[li.dataset.k]));

  $('sendForm').hidden = !canSend || !!S.signed;
  const lockFields = busy || S.preparing;
  $('netSet').disabled = lockFields;
  $('toInput').disabled = lockFields; $('amountInput').disabled = lockFields;
  $('reviewBtn').disabled = lockFields;
  $('reviewBtn').textContent = S.preparing ? 'Checking network and fees…' : S.busy === 'review_transfer' ? 'Approve on device…' : 'Review and sign on device';
  $('realWarn').hidden = chainId() !== '1';

  const sg = S.signed;
  $('signedBox').hidden = !sg;
  if (sg) {
    $('sNet').textContent = NETWORKS[sg.chainId].name;
    $('sTo').textContent = sg.to;
    $('sAmount').textContent = formatEth(sg.value) + ' ETH';
    $('sFee').textContent = 'up to ' + formatEth(BigInt(sg.maxFeePerGas) * BigInt(sg.gasLimit)) + ' ETH';
    $('broadcastBtn').disabled = sg.attempted || S.broadcasting || !connected;
    $('broadcastBtn').textContent = S.broadcasting ? 'Sending…' : 'Broadcast once';
    $('discardBtn').disabled = S.broadcasting;
  }

  const sent = S.sent;
  $('sentBox').hidden = !sent;
  if (sent) {
    $('sentBox').dataset.tone = sent.tone;
    $('sentLabel').textContent = sent.label;
    $('sentText').textContent = sent.text;
    $('sentHash').textContent = sent.hash;
    $('explorerLink').href = NETWORKS[sent.chainId].explorer + sent.hash;
    $('receiptBtn').disabled = !!S.watch;
    $('receiptBtn').textContent = S.watch ? 'Watching…' : 'Watch receipt';
  }
}

async function run(method, params, onDone) {
  showErr($('devError'), '');
  S.busy = method; render();
  try {
    const result = await device.action(method, params);
    await onDone?.(result);
  } catch (e) {
    showErr(method === 'review_transfer' ? $('sendError') : $('devError'), e.message);
  } finally {
    S.busy = null; render();
  }
}

device.addEventListener('state', e => {
  const prev = S.state, st = e.detail;
  if (!st.configured || st.locked || (prev && prev.configured && !st.configured)) clearSession();
  else if (st.phase === 'reset') { S.prepared = null; S.signed = null; }
  S.state = st; render();
});
device.addEventListener('result', () => render());
device.addEventListener('error', e => showErr($('devError'), String(e.detail)));
device.addEventListener('disconnected', e => {
  S.state = null; S.busy = null; S.preparing = false; clearSession();
  $('connPill').dataset.tone = 'bad';
  if (!/by you/.test(e.detail)) showErr($('devError'), String(e.detail) + ' Reconnect to continue.');
  render();
});

$('connectBtn').addEventListener('click', () => {
  const pending = device.connect(); // must run synchronously within the click gesture
  S.connecting = true; clearSession(); showErr($('devError'), ''); render();
  pending.then(st => { S.state = st; $('connPill').dataset.tone = 'ok'; })
    .catch(e => showErr($('devError'), e.message))
    .finally(() => { S.connecting = false; render(); });
});
$('setupBtn').addEventListener('click', () => run('setup'));
$('unlockBtn').addEventListener('click', () => run('unlock'));
$('addressBtn').addEventListener('click', () => {
  clearSession(); render();
  run('get_address', {}, r => {
    if (!r || !/^0x[0-9a-fA-F]{40}$/.test(r.address)) throw new Error('Device returned no valid address.');
    S.address = r.address;
  });
});
$('pingBtn').addEventListener('click', () => run('show_message', { text: 'Hello from the Satooshi Pro start page.' }));
$('cancelBtn').addEventListener('click', () => {
  const b = $('cancelBtn'); b.disabled = true; b.textContent = 'Cancellation requested…';
  device.request('cancel').catch(e => showErr($('devError'), e.message))
    .finally(() => { b.textContent = 'Send cancellation request'; render(); });
});
$('lockBtn').addEventListener('click', () => {
  clearSession(); render();
  device.request('lock').catch(e => showErr($('devError'), e.message)).finally(render);
});
$('disconnectBtn').addEventListener('click', () => device.disconnect('Disconnected by you.'));
$('resetBtn').addEventListener('click', () => {
  if (!confirm('Reset this Satooshi Pro?\n\nThe wallet key will be deleted from the device. Funds can only be recovered with your written 24 words.\n\nThe device will ask you to confirm twice more.')) return;
  clearSession(); S.sent = null;
  run('reset');
});

document.querySelectorAll('input[name=net]').forEach(r => r.addEventListener('change', invalidate));
$('toInput').addEventListener('input', invalidate);
$('amountInput').addEventListener('input', invalidate);

$('sendForm').addEventListener('submit', async ev => {
  ev.preventDefault();
  if (S.busy || S.preparing || !S.address) return;
  showErr($('sendError'), '');
  const from = S.address, chain = chainId();
  const to = $('toInput').value.trim(), amount = $('amountInput').value.trim();
  S.preparing = true; S.prepared = null; S.signed = null; render();
  let payload;
  try {
    payload = await prepareTransfer({ chainId: chain, from, to, amount });
  } catch (e) {
    showErr($('sendError'), e.message);
    return;
  } finally { S.preparing = false; render(); }
  if (S.address !== from) return;
  S.prepared = payload;
  await run('review_transfer', payload, r => {
    if (S.prepared !== payload || S.address !== from) throw new Error('Transfer details changed. Review again.');
    if (String(r.chainId) !== payload.chainId || r.address?.toLowerCase() !== from.toLowerCase()) throw new Error('Device signed for an unexpected account or network. Not shown.');
    S.signed = { ...payload, rawTransaction: r.rawTransaction, transactionHash: r.transactionHash, attempted: false };
  });
});

$('discardBtn').addEventListener('click', () => { S.signed = null; S.prepared = null; render(); });

$('broadcastBtn').addEventListener('click', async () => {
  const sg = S.signed;
  if (!sg || sg.attempted) return;
  sg.attempted = true; S.broadcasting = true; render();
  const base = { chainId: sg.chainId, hash: sg.transactionHash };
  try {
    await broadcastTransfer(sg);
    S.sent = { ...base, tone: 'ok', label: 'Submitted to network', text: `${formatEth(sg.value)} ETH to ${sg.to}. Waiting to be included in a block.` };
  } catch (e) {
    S.sent = { ...base, tone: 'warn', label: 'Outcome unknown',
      text: 'Provider said: ' + e.message + ' The transfer may still have reached the network. Check the explorer or watch the receipt before doing anything else. This signature will not be resent.' };
  } finally {
    S.broadcasting = false; S.signed = null; S.prepared = null;
    $('amountInput').value = '';
    render();
  }
});

$('receiptBtn').addEventListener('click', () => {
  const sent = S.sent; if (!sent || S.watch) return;
  const out = $('receiptText'); out.hidden = false; out.dataset.s = ''; out.textContent = 'Checking…';
  let tries = 0;
  const tick = async () => {
    if (S.sent !== sent) { S.watch = 0; return; }
    tries++;
    try {
      const r = await transactionReceipt(sent.chainId, sent.hash);
      if (r && r.status === '0x1') { out.dataset.s = 'ok'; out.textContent = 'Confirmed: success in block ' + BigInt(r.blockNumber); S.watch = 0; render(); return; }
      if (r && r.status === '0x0') { out.dataset.s = 'fail'; out.textContent = 'Included but failed (status 0x0). Funds spent on fee only.'; S.watch = 0; render(); return; }
      out.textContent = 'Not in a block yet (check ' + tries + ' of 40).';
    } catch (e) { out.textContent = 'Could not read receipt: ' + e.message; }
    if (tries >= 40) { out.textContent += ' Stopped watching; use the explorer.'; S.watch = 0; render(); return; }
    S.watch = setTimeout(tick, 8000);
  };
  S.watch = -1; render(); tick();
});

render();
