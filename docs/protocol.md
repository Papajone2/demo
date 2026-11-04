# USB protocol v1

USB CDC ACM, 115200 baud, UTF-8 JSON separated by `\n`, at most 4096 input
bytes per frame. Desktop Chrome/Edge Web Serial requires HTTPS or localhost and
a user-initiated port picker. Open the page directly, not inside Replit's iframe.

Request: `{"v":1,"id":"unique-id","method":"hello","params":{}}`

Reply: `{"v":1,"id":"unique-id","ok":true,"result":{...}}`

Errors have `ok:false,error:"..."`. Use a fresh ID for every request.
The last 8192 request IDs are remembered for duplicate rejection. Every signing
request still needs a fresh physical review, regardless of request-ID age.

| Method | Parameters | Effect |
|---|---|---|
| hello / status | `{}` | Sanitized status and exact capabilities |
| setup | `{}` | Physical create confirmation, 24 words, backup quiz, optional device PIN |
| unlock | `{}` | Physical confirmation, device PIN entry if enabled |
| get_address | `{}` | Show complete account-0 ETH address; release only after device confirmation |
| review_transfer | strict transfer object below | Device decodes, reviews and signs an EIP-1559 native ETH payment |
| show_message | `{"text":"up to 80 printable ASCII characters"}` | Clearly labeled **COMPUTER MESSAGE / INFO ONLY**, never authorizes signing |
| lock / cancel | `{}` | Drop signing work; lock also drops unlocked entropy |
| reset | `{}` | Two separate physical confirmations; logical key deletion |

Interactive commands immediately acknowledge `{"accepted":true}`. Completion is
an event `{"event":"result","data":{"requestId":"original-id","result":{...}}}`.
Cancellation returns `{"cancelled":true}`. Subscribe before sending a command.

State events: `{"event":"state","data":{name,version,configured,locked,phase,
step,steps,attemptsRemaining,pinEnabled,error,capabilities,prototype}}`.
**They do not include device screen text, words, entropy, PINs, private keys,
or signing payloads.** A browser may show progress, but not mirror recovery screens.

Transfer fields (all integer fields are canonical **decimal strings**):

```json
{
  "chainId": "11155111",
  "nonce": "0",
  "to": "0x1111111111111111111111111111111111111111",
  "value": "1000000000000000",
  "gasLimit": "21000",
  "maxPriorityFeePerGas": "1000000000",
  "maxFeePerGas": "3000000000"
}
```

Only chain IDs 1 and 11155111. Fixed BIP44 path `m/44'/60'/0'/0/0`. No data,
access lists, contract calls, tokens, blind hashes, messages or arbitrary paths.
Device checks destination checksum when mixed case, rejects zero address,
checks fee/amount bounds and requires all review pages before signing.
Signing returns `{rawTransaction,transactionHash,address,chainId}`. The browser
must ask separately before broadcasting; device never accesses a network.

No request can export or import a seed, enter a PIN, simulate a button, execute
a shell command, install software, or bypass the physical review. Simulator
keyboard controls are local only, **not** exposed through this USB protocol.

Status polling every 15 seconds maintains liveness. No host traffic for 45
seconds or five minutes without a physical action locks an unlocked device.
Disconnect/reconnect does not create a new wallet. Setup is rejected if one exists.
