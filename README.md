# Satooshi Pro

A two-button, USB-connected **Raspberry Pi Zero W / WH** signing prototype.
This is experimental software, **not an audited commercial hardware wallet**.
Use test coins. A Linux Pi with a microSD card does not provide a secure element,
tamper resistance, verified boot, or protection against a compromised OS.

## What is implemented

The main Satooshi web app now includes a Hardware workspace. Its default Preview
is a home-use presentation with example balances and simulated multi-coin flows.
Those flows never sign or broadcast transactions. A connected device can display
a clearly labeled preview message and require a physical dismissal; that is not
a financial signature. Real ETH mode remains a separate explicit choice and
supports only the actual firmware capabilities below. Browser-held keys and
funds are never migrated to the hardware account.

### Two-button navigation

Firmware 0.2 shows a left triangle at the lower left and a right triangle at
the lower right. Tap to navigate; hold right for about one second and release
to select or approve. Hold left to cancel (or lock from Home).
Pressing both physical buttons together does nothing. The joystick is unused.

- Original Zero W/WH **ARMv6, 32-bit Raspberry Pi OS**, not Zero 2 W-only code.
- Provisional Adafruit **128×64 OLED Bonnet, product 3531**, SSD1306 I2C at `0x3c`.
- **A = BCM GPIO 5, B = BCM GPIO 6**; joystick is unused.
- USB serial device product descriptor **Satooshi Pro**. Some OS port pickers
  may still show a generic serial-device name.
- A fresh, cryptographically random **24-word BIP39 seed generated on the device
  at setup**, never generated in CI or included in an image.
- Device-only word backup check and optional **4–12 digit PIN**.
- AES-GCM encrypted local storage; five charged failed/interrupted PIN attempts
  logically delete the stored wallet. Warning and attempt count on the device.
- Same identity after restarting or reconnecting from another browser.
- Physical address confirmation and locally decoded/signed **native ETH**
  EIP-1559 payments on **Ethereum and Sepolia only**, account 0.
- A separate, keyless browser companion with a Sepolia-first send flow.
- Regression tests, local terminal simulator, manual image build with checksums.

**Not implemented:** Bitcoin/Solana/TRON or other hardware signing, ERC-20
contracts, swaps, typed messages, on-device recovery import, multiple accounts,
firmware updates, secure-element storage, integration into the existing web
wallet's Send/Swap signer, audited production security, or physical boot validation.
The browser wallet's existing assets are not migrated and its keys are not used.

No seed or PIN export exists. The computer receives only public information and
signatures after physical confirmation. Computer-supplied messages are labeled
informational and cannot authorize a payment.

## Build an image in GitHub

The browser companion filters the port chooser to development USB ID
`1d6b:0104`. Built-in ttyS ports and other hardware wallets are intentionally
not listed. These shared development IDs do **not** authenticate a device.
Open **Connection help** on the setup page for Linux permissions and
host-versus-VM USB troubleshooting.

Updated images place a non-secret `satooshi-usb-status.txt` on the SD card's
boot partition. It records startup stage, result, controller binding and serial
node presence, never seed/PIN/address data. `serial_ready` means the Pi prepared
its USB interface, **not** that a computer enumerated it. Inspect this file
with the Pi powered off if USB detection fails. Do not reflash a funded device
without its paper backup.

1. Open **Actions → Build Pi Zero W image → Run workflow → main → Run workflow**.
2. Wait for a green run. Open the run and download its **Artifacts** archive.
3. Extract the archive. It contains:
   - `satooshi-pro-zero-w.img.xz`
   - `SHA256SUMS`
   - `build-manifest.json`
4. Verify the checksum (`sha256sum -c SHA256SUMS` on Linux) and flash the
   `.img.xz` using Raspberry Pi Imager's **Use custom** option.
5. Use an **8 GB or larger microSD card**. Flashing erases that card. Do not
   apply Imager username, SSH, Wi-Fi or other OS customizations.
6. With power disconnected, fit the correct bonnet; insert the card.
7. Connect a **data-capable USB cable** to the Zero W's **USB port, NOT PWR IN**.
   First boot may take a few minutes. The screen should show Satooshi Pro.

The builder verifies a pinned official Raspberry Pi OS Lite image checksum,
customizes it on a privileged Ubuntu runner, installs ARM packages, runs an
ARM/QEMU derivation smoke test and packages a compressed image. Package security
updates are installed at build time, so builds are not bit-for-bit reproducible.
Artifacts expire after 14 days; run the build again if needed. No image is a
success until the workflow is green, and a green image still needs physical testing.

The USB IDs in this prototype are Linux Foundation **development/example IDs**,
not an allocation for shipping a commercial USB product.

## Open the companion

The `web/` directory is a standalone static website: no build step or API keys.
Serve locally with:

```sh
python3 -m http.server 8080 --directory web
```

Open **http://localhost:8080** directly in desktop Chrome or Edge.
For remote hosting use HTTPS. An embedded preview may block the serial chooser;
open its direct URL in a separate tab. Mobile and other browsers are not
supported for USB setup in this version. GitHub Pages is not automatically enabled.

On the Satooshi workspace the same companion is available at `/start`. The
device's `satooshi.io/start` text is the intended product address, **not a claim
that this repository controls or has published that domain**.

1. Click **Connect device**, then choose the USB serial port.
2. Start setup and confirm creation using both device buttons.
3. Write all words on paper, privately; B moves forward, A moves back.
4. At word 24, press both to begin the backup check.
5. Select the correct words with A/B and confirm each with both.
6. Choose a PIN or explicitly accept no PIN. To enter a PIN, A/B select digits,
   both selects a digit; choose **Done** after 4–12 digits. Repeat it.
7. Verify the address on the device. Confirm it before using the browser address.

**Never use a seed from a test fixture, screenshot or public example.**
No-PIN mode stores its encryption key on the same microSD: it is not protection
against theft or file access. PIN encryption also does not prevent an offline
attacker from copying the card and brute-forcing a short PIN.

## Make a test transaction

Default to **Sepolia test ETH**. Verify the receiving chain and fund the
device-derived address with faucet coins. Enter a recipient and amount,
prepare the transaction, and inspect every page on the device:

1. Amount and actual chain.
2. The **entire destination address**, never just a shortened prefix.
3. Maximum network fee.
4. Maximum total debit and nonce.
5. Hold the right button for about one second and release to sign.
   Hold left to cancel. Tap left/right to move through pages.
   Firmware 0.1 uses both buttons to confirm; 0.2 uses only left/right.

The device signs the exact reviewed payload, not arbitrary computer text.
The browser then asks separately before broadcasting **once**. If broadcasting
times out, the outcome is unknown: check the explorer using the transaction
hash. **Do not send a replacement just because the browser timed out.**

Public RPC endpoints are used by the standalone companion for fees, balances,
broadcast and receipts; providers can see the queried addresses. Neither the
device nor GitHub receives your web wallet's Alchemy/ChangeNOW/dRPC keys.

## Development / simulator

On a development computer with Python 3.11+:

```sh
python3 -m pip install -r requirements.txt pyserial
PYTHONPATH=device python3 -m unittest discover -s tests -v
node --test tests/serial.test.mjs
PYTHONPATH=device python3 -m satooshi.simulator
```

Simulator controls: `a`, `b`, `Enter` for both, `q` to exit. Its terminal shows
the local simulated device screen, including its **test** words; do not record
real recovery words there. A printed local PTY supports serial test programs
on Linux/macOS but is not usually selectable through a browser's Web Serial
picker. Use the physical USB device for that final test.

## Safety and recovery limitations

- Keep the paper backup even in a demo. There is **no device recovery-import UI
  yet**; standard external BIP39 tools can recover the fixed documented ETH path.
  Do not put meaningful funds on this prototype.
- Five failed PIN attempts or a two-stage physical reset performs **logical
  deletion only**, not forensic secure erasure of microSD flash.
- Never reflash a funded device without its paper backup. Flashing destroys its
  stored wallet; new setup creates a different identity.
- Dependencies and signing code are unaudited. Python ECDSA is not designed to
  provide commercial hardware-wallet side-channel resistance.
- Wi-Fi/Bluetooth drivers, SSH, automatic user setup, console login and USB
  networking are disabled in the custom image. A modified card/OS can still
  steal keys. The Pi has no secure-boot guarantee in this design.
- The bonnet model must match the profile. Another display/controller requires
  a different hardware adapter; do not assume a similar-looking board works.

See [USB protocol](docs/protocol.md) and [physical test checklist](docs/hardware-test.md).
