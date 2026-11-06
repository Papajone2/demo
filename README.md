# Satooshi Pro

A two-button, USB-connected **Raspberry Pi Zero W / WH** signing prototype.
This is experimental software, **not an audited commercial hardware wallet**.
Use test coins. A Linux Pi with a microSD card does not provide a secure element,
tamper resistance, verified boot, or protection against a compromised OS.

## What is implemented

The main web app's `/dashboard` uses the **Pi-generated recovery phrase** for
addresses and real browser-side signing. Opening the wallet and each payment
require physical approval before seed entropy is released over USB. Only public
account metadata is deliberately persisted in the browser. Signing material is
kept in a separate temporary runtime session and cleared after success/failure.
JavaScript erasure is best effort: a compromised computer can copy the seed,
so device-only spending is not a security guarantee. This is not offline
hardware signing. Web setup and Terms require acknowledgment. The device shows
ordinary Open/Review/Confirm prompts, not false offline-signature claims.
Root browser-wallet routes, vault, addresses and funds remain separate and
unchanged. No migration is automatic. Transfer coverage is the existing browser
transaction engine's actual support, not every priced asset.

`approve_browser_transfer` requires an unlocked, configured device and local
review of amount, full address, fee and final summary. It returns an approval,
not a signature or a fabricated transaction hash. The browser signs after this
approval. The older `preview_review` remains simulation-only; genuine native
ETH signing remains a separate firmware capability.

### Two-button navigation

The earliest splash is only the supplied wordmark. A ready fresh device shows
the setup address; after connecting it remembers to use a logo-only home.
Pairing is automatic after the browser USB chooser, not a firmware-attestation
claim. Ordinary choices have labeled left/right buttons and confirm on a click.
Recovery-word navigation uses corner arrows. Word checks, restoration words and
PIN digits use a two-second right hold followed by release. The progress bar
stays full while held and its text inverts against the fill.

The PIN is optional and can contain 1–12 digits; short PINs are substantially
weaker. Move across 0–9, Done and Delete with taps, and hold right to select.
Device restore accepts 24 valid BIP39 words entered on the device, never via USB.
Browser-backed payment review uses clicks through amount/address/fee/summary;
the final click approves it for the browser to sign.

Legacy native ETH signing and simulated previews still use a final three-second hold.
Releasing early resets the bar; pressing left cancels the hold. Hold left to
cancel the action (or lock from Home).
Pressing both physical buttons together does nothing. The joystick is unused.

### Review the new interface before flashing

In the main website open `/device-studio`. Rehearse send, swap and receive
screens with no device, or connect firmware 0.3 and send the same structured
preview to the Pi. Custom notes use `show_message` and are always headed
**From computer**; they cannot authorize a payment. These actions are isolated
from real wallet balances and broadcasting. The image artifact includes
`oled-preview.png`, rendered by the same Python renderer as the actual screen.

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

PIN export does not exist. `open_wallet` releases seed entropy only after local
click approval; `approve_and_release` requires all payment review pages and the
final local confirmation. Both require a configured, unlocked device. Generic
messages cannot authorize a payment or release a seed. Never log USB result
payloads or use funded recovery phrases in screenshots or automated tests.

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
   - `oled-preview.png` (actual firmware layouts with public sample data)
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

On the Satooshi workspace the guided main-wallet setup is available at `/start`.
It checks compatibility and requests physical pairing, not authenticity attestation. The
device's `satooshi.io/start` text is the intended product address, **not a claim
that this repository controls or has published that domain**.

1. Click **Connect device**, then choose the USB serial port.
2. Pair by holding right on the device, then start setup and confirm creation.
3. Write all words on paper, privately; right moves forward, left moves back.
4. At word 24, hold right and release to begin the backup check.
5. Select the correct words with left/right; hold right and release to select.
6. Choose a PIN or explicitly accept no PIN. To enter a PIN, A/B select digits,
   hold right and release selects a digit; choose **Done** after 4–12 digits. Repeat it.
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
5. Review the final summary, then hold right for three seconds to sign.
   Releasing early resets the progress bar. Hold left to cancel.

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

## Image identity and startup

Use **Build Pi Zero W image**, not **Device tests**: their run numbers are separate.
New image artifacts are named `satooshi-firmware-0.3.0-image-N`. Each compressed
image filename includes its firmware version, build number and source commit.
Extract the ZIP into a fresh folder. Run `unxz --keep --verbose` followed by that
exact `.img.xz` filename, then flash its matching `.img`. Do not reuse an older
`satooshi-pro-zero-w.img` left in Downloads. Etcher must validate the flash.
Flashing erases the device wallet; keep the recovery backup or use a spare card.

The FAT boot partition contains `satooshi-build.json`, readable on your computer.
Its commit should match the downloaded artifact's `build-manifest.json`.
The website also shows the version and source commit reported over USB.
These are diagnostics, not cryptographic firmware attestation.

An early, keyless OLED service shows only the supplied Satooshi wordmark
before loading the wallet's cryptography. The setup address appears when ready. USB gadget setup
also starts during early system initialization, independently of the splash.
Unused network waits and offline maintenance timers are disabled. Target-Python
bytecode is precompiled. Secure randomness, vault protections, filesystem checks
and physical transaction confirmation remain enabled. Boot times have not been
measured on physical hardware; the logo does not mean the signing service is ready.
