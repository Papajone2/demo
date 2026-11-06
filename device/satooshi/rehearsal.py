"""Host-supplied display rehearsals. Never keys, signatures or broadcast bytes."""
import re
from decimal import Decimal


def text(value, name, limit):
    if not isinstance(value, str) or not 1 <= len(value) <= limit:
        raise ValueError(name + " has an invalid length")
    if any(ord(c) < 32 or ord(c) > 126 for c in value) or value != value.strip():
        raise ValueError(name + " must be printable ASCII without outer spaces")
    return value


def quantity(value, name, positive=True):
    text(value, name, 24)
    if not re.fullmatch(r"(0|[1-9][0-9]*)(\.[0-9]+)?", value):
        raise ValueError(name + " must be a decimal number")
    if positive and Decimal(value) <= 0:
        raise ValueError(name + " must be positive")
    return value


def coin(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9]{1,10}", value):
        raise ValueError(name + " must be an uppercase symbol")
    return value


class Rehearsal:
    simulated = True

    def __init__(self, payload):
        fields = {"operation", "amount", "symbol", "address", "fee", "feeSymbol", "network"}
        if not isinstance(payload, dict):
            raise ValueError("Invalid preview")
        operation = payload.get("operation")
        if operation not in ("send", "swap", "receive"):
            raise ValueError("Unsupported preview operation")
        if operation == "swap":
            fields |= {"receiveAmount", "receiveSymbol"}
        if set(payload) != fields:
            raise ValueError("Unexpected preview fields")
        self.data = dict(payload)  # Immutable to subsequent host payload edits.
        self.operation = operation
        quantity(payload["amount"], "Amount")
        quantity(payload["fee"], "Fee", positive=False)
        coin(payload["symbol"], "Symbol")
        coin(payload["feeSymbol"], "Fee symbol")
        text(payload["address"], "Address", 96)
        if not re.fullmatch(r"[A-Za-z0-9:_-]+", payload["address"]):
            raise ValueError("Use a blockchain address, not a message")
        text(payload["network"], "Network", 18)
        if operation == "swap":
            quantity(payload["receiveAmount"], "Receive amount")
            coin(payload["receiveSymbol"], "Receive symbol")
        # Every exact quantity must fit one compact summary line. No truncation.
        for amount, symbol in (("amount", "symbol"), ("fee", "feeSymbol"),
                               *(([("receiveAmount", "receiveSymbol")]) if operation == "swap" else [])):
            if len(payload[amount] + " " + payload[symbol]) > 24:
                raise ValueError("Quantity is too long for the device summary")

    def pages(self):
        d = self.data
        action = {"send": "Send", "swap": "Swap", "receive": "Receive"}[self.operation]
        pages = [
            (action + " amount", [d["amount"] + " " + d["symbol"], d["network"]]),
            ("Check address", [d["address"][i:i + 24] for i in range(0, len(d["address"]), 24)]),
            ("Network fee", [d["fee"] + " " + d["feeSymbol"]]),
        ]
        if self.operation == "swap":
            pages.append(("Estimated receive", [d["receiveAmount"] + " " + d["receiveSymbol"],
                                                "Estimate only"]))
        short = d["address"] if len(d["address"]) <= 24 else d["address"][:10] + "..." + d["address"][-10:]
        summary = [d["amount"] + " " + d["symbol"], short,
                   d["fee"] + " " + d["feeSymbol"] + " fee"]
        if self.operation == "swap":
            summary.append(d["receiveAmount"] + " " + d["receiveSymbol"])
        pages.append(("Confirm " + action.lower(), summary))
        return pages

    def approve(self):
        # Deliberately no signature/hash/address derivation or fake broadcast result.
        return {"simulated": True, "approved": True, "operation": self.operation}
