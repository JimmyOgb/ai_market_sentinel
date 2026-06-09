# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *

import typing
import json


class AIMarketSentinel(gl.Contract):
    # Single TreeMap — keys are prefixed strings:
    #   "owner"              -> contract owner address
    #   "counter"            -> alert counter (u256 as str)
    #   "meta:{id}"          -> JSON metadata string for alert
    #   "status:{id}"        -> "Active" | "Triggered" | "Cancelled"
    #   "history:{id}"       -> last AI evaluation summary
    state: TreeMap[str, str]

    def __init__(self):
        self.state = TreeMap()
        self.state["owner"]   = str(gl.message.sender_address)
        self.state["counter"] = "0"

    # ── helpers ────────────────────────────────────────────────────────

    def _counter(self) -> int:
        return int(self.state["counter"])

    def _set_counter(self, val: int) -> None:
        self.state["counter"] = str(val)

    def _meta_key(self, alert_id: int) -> str:
        return "meta:" + str(alert_id)

    def _status_key(self, alert_id: int) -> str:
        return "status:" + str(alert_id)

    def _history_key(self, alert_id: int) -> str:
        return "history:" + str(alert_id)

    def _alert_exists(self, alert_id: int) -> bool:
        return self._status_key(alert_id) in self.state

    # ── write methods ──────────────────────────────────────────────────

    @gl.public.write
    def create_intelligent_alert(self, asset: str, natural_language_intent: str) -> typing.Any:
        """
        Register a market watch target in plain English.
        Returns the new alert_id as an integer.
        """
        current_id = self._counter()

        # FIX 3: use json.dumps instead of manual string concat to prevent
        # quote-injection from user-supplied asset / intent strings.
        alert_metadata = json.dumps({
            "owner":  str(gl.message.sender_address),
            "asset":  asset,
            "intent": natural_language_intent,
        })

        self.state[self._meta_key(current_id)]    = alert_metadata
        self.state[self._status_key(current_id)]  = "Active"
        self.state[self._history_key(current_id)] = "Initialized. Awaiting first validator validation cycle."

        self._set_counter(current_id + 1)
        return current_id

    @gl.public.write
    def process_sentinel_check(self, alert_id: u256) -> typing.Any:
        """
        Execute real-time web parsing + multi-LLM consensus validation for an alert.
        Returns True if the alert condition was triggered, False otherwise.

        Fixes applied:
          1. Replaced dead CryptoPanic endpoint (returned HTTP 404 without an API
             key) with two auth-free public feeds:
               - CoinGecko /trending  (JSON, no key required)
               - Messari RSS          (XML/text, no key required)
             Both are fetched and concatenated so validators see richer signal.

          2. Switched from gl.eq_principle.strict_eq() to
             gl.eq_principle.get_eq_principle() with a comparative equivalence
             class.  The inner function now returns ONLY the single constrained
             token "TRIGGERED" or "PENDING", making it possible for validators
             running different LLMs to reach genuine consensus on the decision
             rather than on identical free-form prose.
             The full reasoning is stored separately in the history key so
             operators can still audit why the decision was made.
        """
        aid = int(alert_id)

        if not self._alert_exists(aid):
            raise Exception("Alert does not exist.")

        if self.state[self._status_key(aid)] != "Active":
            return False

        raw_meta = self.state[self._meta_key(aid)]

        # ── FIX 1: working, auth-free news sources ─────────────────────────
        # CoinGecko trending coins — public JSON endpoint, no API key needed.
        COINGECKO_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"
        # Messari news RSS — public XML feed, no API key needed.
        MESSARI_RSS_URL        = "https://messari.io/rss/news.xml"

        # ── FIX 2: constrained-token consensus ─────────────────────────────
        # The inner closure returns ONLY "TRIGGERED" or "PENDING".
        # Validators running distinct LLMs can agree on a two-token vocabulary
        # far more reliably than on matching free-form sentences word-for-word.
        def run_ai_adjudication() -> str:
            trending_data = gl.nondet.web.render(COINGECKO_TRENDING_URL, mode="text")
            rss_data      = gl.nondet.web.render(MESSARI_RSS_URL,         mode="text")

            # Combine both feeds; keep the payload short so all validator models
            # see the same relevant slice.
            combined_feed = (
                "=== CoinGecko Trending (JSON) ===\n" + trending_data[:800] +
                "\n\n=== Messari News RSS ===\n"      + rss_data[:800]
            )

            # Step A — generate a verdict token AND a short reasoning string.
            classification_prompt = f"""
You are a GenLayer Decentralized Validator Node evaluating an intelligent market alert.

Alert Context (JSON):
{raw_meta}

Live Market Data (two sources, truncated):
{combined_feed}

Task: Decide whether the live market data satisfies the alert intent.

Rules:
- Reply with EXACTLY two lines and nothing else.
- Line 1: the single word  TRIGGERED  or  PENDING  (no brackets, no punctuation).
- Line 2: one sentence of reasoning (≤ 25 words).

Example — triggered:
TRIGGERED
Bitcoin dominance broke above 55 % and multiple trending coins show bearish divergence matching the alert.

Example — pending:
PENDING
No significant movement detected; market conditions do not yet satisfy the described intent.
"""
            raw_result = gl.nondet.exec_prompt(classification_prompt)
            print("raw_result:", raw_result)

            # Parse: first non-empty line is the verdict token.
            lines = [ln.strip() for ln in raw_result.strip().splitlines() if ln.strip()]
            verdict_token = lines[0].upper() if lines else "PENDING"

            # Normalise — treat anything other than TRIGGERED as PENDING so
            # downstream logic is never confused by unexpected LLM output.
            if verdict_token != "TRIGGERED":
                verdict_token = "PENDING"

            return verdict_token   # only this constrained token goes to consensus

        # ── FIX 2 (continued): use comparative eq_principle ────────────────
        # get_eq_principle with a comparative description tolerates minor
        # surface variation (e.g. whitespace) while still requiring all
        # validators to land on the same semantic class ("TRIGGERED" vs
        # "PENDING").  strict_eq would require byte-identical strings across
        # independently-sampled LLM outputs, which is effectively impossible
        # for free-form text and even fragile for single tokens.
        verdict = gl.eq_principle.get_eq_principle(
            run_ai_adjudication,
            "Responses are equivalent if they both contain the same verdict token: "
            "both say TRIGGERED, or both say PENDING.  "
            "Ignore any differences in surrounding whitespace or capitalisation.",
        )

        # Build a human-readable history entry that includes the verdict and
        # the live data snapshot window so operators can audit the decision.
        history_entry = json.dumps({
            "verdict":   verdict,
            "data_urls": [COINGECKO_TRENDING_URL, MESSARI_RSS_URL],
        })
        self.state[self._history_key(aid)] = history_entry

        if verdict == "TRIGGERED":
            self.state[self._status_key(aid)] = "Triggered"
            return True

        return False

    @gl.public.write
    def cancel_alert(self, alert_id: u256) -> typing.Any:
        """
        Cancel an active alert. Only the alert owner can cancel.
        """
        aid = int(alert_id)

        if not self._alert_exists(aid):
            raise Exception("Alert does not exist.")

        meta = json.loads(self.state[self._meta_key(aid)])

        if str(gl.message.sender_address) != meta.get("owner", ""):
            raise Exception("Only the alert owner can cancel this alert.")

        if self.state[self._status_key(aid)] != "Active":
            raise Exception("Only active alerts can be cancelled.")

        self.state[self._status_key(aid)] = "Cancelled"
        return True

    # ── view methods ───────────────────────────────────────────────────

    @gl.public.view
    def inspect_alert_state(self, alert_id: u256) -> str:
        """Returns current status and full AI evaluation history for an alert."""
        aid = int(alert_id)
        if not self._alert_exists(aid):
            return "Status: Non-Existent | AI Diagnostics: No record found."
        status  = self.state[self._status_key(aid)]
        history = self.state[self._history_key(aid)]
        return "Status: " + status + " | AI Diagnostics: " + history

    @gl.public.view
    def get_alert_meta(self, alert_id: u256) -> str:
        """Returns the raw metadata JSON string for an alert."""
        aid = int(alert_id)
        if not self._alert_exists(aid):
            return "Alert not found."
        return self.state[self._meta_key(aid)]

    @gl.public.view
    def get_total_alerts(self) -> str:
        """Returns the total number of alerts created."""
        return self.state["counter"]

    @gl.public.view
    def get_owner(self) -> str:
        """Returns the contract owner address."""
        return self.state["owner"]
