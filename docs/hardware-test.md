# Physical acceptance checklist — not completed by CI

Do these tests with a new test-only wallet and Sepolia coins, not real funds.

- [ ] Confirm the bonnet model is Adafruit 3531, 128×64 SSD1306, not SH1106/LCD.
- [ ] Original Zero W/WH boots flashed image on an 8 GB+ card.
- [ ] Screen shows every line clearly; no clipping of full addresses or amounts.
- [ ] A is BCM5, B is BCM6. Joystick does nothing.
- [ ] Chord A+B fires once on release, without accidental single-button actions.
- [ ] USB **data** port enumerates; PWR IN does not.
- [ ] Descriptor says Satooshi Pro; Windows/macOS/Linux port picker differences recorded.
- [ ] No SSH, networking gadget or login shell is exposed to the computer.
- [ ] Fresh image has no generated seed or wallet.
- [ ] Creation requires physical confirmation; 24 words form a valid BIP39 phrase.
- [ ] Word check must be completed before vault creation.
- [ ] Four-digit and twelve-digit PINs can be chosen and re-entered.
- [ ] Mismatching PIN confirmation returns to choosing a new PIN.
- [ ] Optional no-PIN choice requires explicit warning confirmation.
- [ ] Reboot and a different browser preserve the same confirmed public address.
- [ ] PIN never appears in browser or USB traffic.
- [ ] Recovery words never appear in browser, USB traffic, logs or image files.
- [ ] Wrong PIN warning decrements; reconnect and power-cycle do not reset attempts.
- [ ] Fifth failed PIN deletes the wallet and returns to first-time setup.
- [ ] Two physical confirmations are required for deliberate reset.
- [ ] Reset/cancel/disconnect during setup never saves or enables an unfinished seed.
- [ ] Address and all amount/fee digits are visible on the device.
- [ ] In-flight transaction cannot be changed from the host.
- [ ] Native Sepolia transfer signature recovers to the device-derived address.
- [ ] Every review page is required; final both-button confirmation is required.
- [ ] Reject BTC, Solana, TRON, token data, arbitrary hashes and unknown chain IDs.
- [ ] Browser does not broadcast before separate explicit confirmation.
- [ ] Broadcast failure is treated as unknown until explorer/receipt verification.
- [ ] Receipt status zero is shown as failed, not completed.
- [ ] Computer messages are clearly informational and never result in signatures.
- [ ] USB disconnect locks within 45 seconds; no physical action for five minutes locks.

Record OS, firmware source commit, image checksum and results when testing.
Do not store seed words, PINs or private keys in an issue or test report.
