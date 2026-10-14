"""Advanced captcha + optional user password (PIN)."""

from __future__ import annotations

import hashlib
import hmac
import random
import secrets
from dataclasses import dataclass

from config import get_settings

# Emoji pools for visual captcha
EMOJI_POOL = ["🚀", "💎", "⭐", "🔥", "🌙", "⚡", "🎯", "🛡️", "💰", "🔑", "🎲", "🧩"]


@dataclass
class CaptchaChallenge:
    question: str
    answer: str
    options: list[str]  # shuffled choices including correct
    kind: str


def make_captcha() -> CaptchaChallenge:
    """Generate one of several hard-ish challenge types."""
    kind = random.choice(["math", "emoji", "sequence", "word"])

    if kind == "math":
        a, b = random.randint(11, 39), random.randint(7, 29)
        op = random.choice(["+", "-", "×"])
        if op == "+":
            ans = a + b
        elif op == "-":
            if b > a:
                a, b = b, a
            ans = a - b
        else:
            a, b = random.randint(3, 12), random.randint(3, 9)
            ans = a * b
        question = f"🔐 <b>Security check</b>\n\nWhat is <b>{a} {op} {b}</b>?"
        correct = str(ans)
        opts = {correct}
        while len(opts) < 4:
            noise = str(ans + random.randint(-12, 12))
            if noise != correct and int(noise) >= 0:
                opts.add(noise)
        options = list(opts)
        random.shuffle(options)
        return CaptchaChallenge(question, correct, options, kind)

    if kind == "emoji":
        target = random.choice(EMOJI_POOL)
        others = [e for e in EMOJI_POOL if e != target]
        options = [target] + random.sample(others, 3)
        random.shuffle(options)
        question = (
            f"🔐 <b>Security check</b>\n\n"
            f"Tap the button that shows: <b>{target}</b>"
        )
        return CaptchaChallenge(question, target, options, kind)

    if kind == "sequence":
        start = random.randint(2, 8)
        step = random.choice([2, 3, 4, 5])
        seq = [start + i * step for i in range(4)]
        ans = start + 4 * step
        question = (
            f"🔐 <b>Security check</b>\n\n"
            f"What comes next?\n<code>{seq[0]}, {seq[1]}, {seq[2]}, {seq[3]}, ?</code>"
        )
        correct = str(ans)
        opts = {correct}
        while len(opts) < 4:
            opts.add(str(ans + random.choice([-step * 2, -step, step, step * 2, 1, -1])))
        options = list(opts)
        random.shuffle(options)
        return CaptchaChallenge(question, correct, options, kind)

    # word: reverse / count letters
    words = ["ROCKET", "WALLET", "CREDIT", "SECURE", "FUND", "LOAN"]
    w = random.choice(words)
    mode = random.choice(["reverse", "length", "first"])
    if mode == "reverse":
        correct = w[::-1]
        question = f"🔐 <b>Security check</b>\n\nReverse this word:\n<code>{w}</code>"
        opts = {correct, w, w.lower(), w[:3] + w[3:][::-1]}
    elif mode == "length":
        correct = str(len(w))
        question = f"🔐 <b>Security check</b>\n\nHow many letters in:\n<code>{w}</code>?"
        opts = {correct}
        while len(opts) < 4:
            opts.add(str(random.randint(3, 9)))
    else:
        correct = w[0]
        question = f"🔐 <b>Security check</b>\n\nFirst letter of:\n<code>{w}</code>?"
        opts = {correct}
        while len(opts) < 4:
            opts.add(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    options = list(opts)[:4]
    random.shuffle(options)
    return CaptchaChallenge(question, correct, options, kind)


def _pepper() -> str:
    s = get_settings()
    return (s.bot_token or "marcenzo")[:24]


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        (salt + _pepper()).encode("utf-8"),
        120_000,
    ).hex()
    return digest, salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    digest, _ = hash_password(password, salt)
    return hmac.compare_digest(digest, stored_hash)
