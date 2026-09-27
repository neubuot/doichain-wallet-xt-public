# Regressionstests fuer v0.9.9: Discovery-Index-Fehler.
#
# Befund (Fall Michael, 27.09.2026): Versionen 0.9.5 bis 0.9.8 setzten den
# "naechsten freien Index" nach der Discovery auf max_used + 1 + GAP_LIMIT.
# Wechselgeld landete dadurch ab Index 50. Eine spaetere Discovery mit frischem
# State brach nach 50 leeren Adressen ab und sah diese Adressen nie.
# 99.000 DOI waren unsichtbar, obwohl der Seed sie besitzt.
#
# Alle Tests laufen offline (ElectrumX-Attrappe).
# Ausfuehren:  python -m unittest tests.test_v099 -v

import sys
import unittest
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.simplefilter("ignore", DeprecationWarning)

from src.wallet.doi_wallet import DoiWallet
from src.wallet.seed_manager import SeedManager

TEST_MNEMONIC = (
    "abandon abandon abandon abandon abandon abandon abandon abandon "
    "abandon abandon abandon about"
)


class _FakeElectrum:
    """Attrappe: Historie und Saldo je Adresse aus einem Dict."""

    def __init__(self, used: dict):
        # used: {address: satoshi}
        self.used = used
        self.is_connected = True
        self.history_calls = 0
        self.balance_calls = 0

    def get_history(self, addr):
        self.history_calls += 1
        return [{"tx_hash": "ab" * 32, "height": 100}] if addr in self.used else []

    def get_balance(self, addr):
        self.balance_calls += 1
        return {"confirmed": self.used.get(addr, 0), "unconfirmed": 0}

    def get_utxos(self, addr):
        return []


def _addr(change, idx):
    return SeedManager().from_mnemonic(TEST_MNEMONIC).get_keypair(index=idx, change=change)["address"]


def _wallet():
    w = DoiWallet()
    w.restore(TEST_MNEMONIC)
    return w


class TestIndexNotInflated(unittest.TestCase):
    def test_empty_wallet_next_index_is_zero(self):
        w = _wallet()
        w.electrum = _FakeElectrum({})
        w.discover_addresses()
        # vorher: 50 (= 0 benutzte + GAP_LIMIT)
        self.assertEqual(w._receive_index, 0)
        self.assertEqual(w._change_index, 0)

    def test_used_addresses_next_index_is_max_plus_one(self):
        w = _wallet()
        w.electrum = _FakeElectrum({_addr(0, 1): 100_000_000_000, _addr(1, 3): 5})
        w.discover_addresses()
        self.assertEqual(w._receive_index, 2)
        self.assertEqual(w._change_index, 4)

    def test_handed_out_address_not_reissued(self):
        w = _wallet()
        w.electrum = _FakeElectrum({})
        a1 = w.get_new_receive_address()   # Index 5 (initial), floor = 6
        w.discover_addresses()              # leer, target 0, floor gewinnt
        self.assertEqual(w._receive_index, 6)
        self.assertNotEqual(w.get_new_receive_address(), a1)


class TestMichaelScenario(unittest.TestCase):
    """State sagt change_index=50, Wechselgeld liegt auf Change 50..59."""

    def _setup(self):
        used = {_addr(0, 1): 100_000_000_000}           # 1.000 DOI auf Empfang 1
        for i in range(50, 59):
            used[_addr(1, i)] = 0                        # verbrauchte Wechselgeld-Adressen
        used[_addr(1, 59)] = 9_899_999_977_150           # 98.999,9997715 DOI
        w = _wallet()
        w.set_state({"version": 1, "network": "doichain-mainnet",
                     "receive_index": 52, "change_index": 50, "last_discover": None})
        w.electrum = _FakeElectrum(used)
        return w

    def test_old_behaviour_would_miss_change_50(self):
        # Kontrolle: mit Gap 50 und OHNE Mindest-Scan haette man 0..49 gescannt
        # und bei 50 leeren aufgehoert. Mit v0.9.9 (min_scan = 50) wird weitergesucht.
        w = self._setup()
        diag = w.discover_addresses()
        self.assertEqual(diag["change"]["max_used_index"], 59)
        self.assertEqual(w._change_index, 60)
        self.assertEqual(w._receive_index, 2)   # aufgeblaehter 52 zurueckgesetzt

    def test_balance_includes_change_59(self):
        w = self._setup()
        w.discover_addresses()
        bal = w.get_balance(force_refresh=True)
        self.assertAlmostEqual(bal["confirmed_doi"], 1000 + 98999.9997715, places=6)

    def test_state_roundtrip_keeps_fix(self):
        w = self._setup()
        w.discover_addresses()
        state = w.get_state()
        self.assertEqual(state["change_index"], 60)
        self.assertEqual(state["receive_index"], 2)


class TestDeepScanWithoutState(unittest.TestCase):
    def test_receive_52_found_when_state_missing(self):
        # Alte Version hatte Empfangsadresse Index 52 ausgegeben (1 + 1 + 50),
        # State-Datei ging verloren: normale Gap 50 wuerde bei 2..51 abbrechen.
        w = _wallet()
        w.electrum = _FakeElectrum({_addr(0, 1): 1, _addr(0, 52): 7_000_000_000})
        w._deep_scan_pending = True
        diag = w.discover_addresses()
        self.assertEqual(diag["gap_limit"], DoiWallet.DEEP_GAP_LIMIT)
        self.assertEqual(diag["receive"]["max_used_index"], 52)
        self.assertEqual(w._receive_index, 53)
        self.assertFalse(w._deep_scan_pending)
        self.assertAlmostEqual(w.get_balance(force_refresh=True)["confirmed_doi"], 70.00000001)

    def test_watch_filter_limits_refresh_queries(self):
        w = _wallet()
        fe = _FakeElectrum({_addr(0, 1): 1})
        w.electrum = fe
        w._deep_scan_pending = True
        w.discover_addresses()          # scannt 0..121 je Kette
        known = len(w._known_addresses)
        fe.balance_calls = 0
        w.get_balance(force_refresh=True)
        self.assertGreater(known, 200)
        # Saldo-Refresh fragt nur Fenster (max_used + GAP) plus Benutzte ab
        self.assertLessEqual(fe.balance_calls, 2 * (DoiWallet.GAP_LIMIT + 2))
        self.assertIn(_addr(0, 1), w._watch)


if __name__ == "__main__":
    unittest.main()
