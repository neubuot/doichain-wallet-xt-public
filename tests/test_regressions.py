# Regressionstests für die im Security-Review behobenen Fehler.
# Alle Tests laufen offline (kein Netzwerk, keine Wallet-Datei nötig).
#
# Ausführen:  python3 -m unittest tests.test_regressions -v

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.wallet.crypto_utils import (
    address_to_script_pubkey,
    base58check_encode,
    pubkey_to_address,
    validate_address,
)
from src.wallet.seed_manager import SeedManager
from src.wallet.tron_crypto import trx_to_sun, usdt_to_raw
from src.wallet.transaction import TxOutput, _estimate_tx_size

# Bekannte BIP-39-Test-Mnemonic (Trezor-Testvektoren)
TEST_MNEMONIC = (
    "abandon abandon abandon abandon abandon abandon abandon abandon "
    "abandon abandon abandon about"
)


class TestAmountConversion(unittest.TestCase):
    """Befund: int(x * 1e6) schnitt Beträge ab (0.29 USDT -> 289999 raw)."""

    def test_usdt_rounding(self):
        self.assertEqual(usdt_to_raw(0.29), 290000)
        self.assertEqual(usdt_to_raw(19.99), 19990000)

    def test_trx_rounding(self):
        self.assertEqual(trx_to_sun(19.99), 19990000)
        self.assertEqual(trx_to_sun(0.000001), 1)

    def test_exact_values(self):
        self.assertEqual(trx_to_sun(1), 1_000_000)
        self.assertEqual(usdt_to_raw(100), 100_000_000)


class TestAddressValidation(unittest.TestCase):
    """Befund: Adressen fremder Chains (Bitcoin) wurden als Sendeziel akzeptiert."""

    def test_rejects_bitcoin_p2pkh(self):
        self.assertFalse(validate_address("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"))

    def test_rejects_bitcoin_bech32(self):
        self.assertFalse(
            validate_address("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4")
        )

    def test_accepts_doichain_p2pkh(self):
        sm = SeedManager().from_mnemonic(TEST_MNEMONIC)
        addr = sm.get_receive_address(0)
        self.assertTrue(addr.startswith("N"))
        self.assertTrue(validate_address(addr))
        self.assertTrue(validate_address(addr, expected_version=0x34))

    def test_rejects_garbage(self):
        self.assertFalse(validate_address(""))
        self.assertFalse(validate_address("nicht-eine-adresse"))

    def test_script_pubkey_rejects_unknown_version(self):
        # Bitcoin-P2PKH (Version 0x00) darf kein Script mehr ergeben
        btc = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
        with self.assertRaises(ValueError):
            address_to_script_pubkey(btc)

    def test_script_pubkey_accepts_doichain(self):
        addr = base58check_encode(0x34, b"\x01" * 20)
        script = address_to_script_pubkey(addr)
        # OP_DUP OP_HASH160 <20B> OP_EQUALVERIFY OP_CHECKSIG
        self.assertEqual(script[:3], bytes([0x76, 0xA9, 0x14]))
        self.assertEqual(script[-2:], bytes([0x88, 0xAC]))


class TestSeedManager(unittest.TestCase):
    """Befunde: fragiles Pfad-Parsing, fehlende BIP-32-Randfallprüfung."""

    def setUp(self):
        self.sm = SeedManager().from_mnemonic(TEST_MNEMONIC)

    def test_derivation_is_deterministic(self):
        a = self.sm.get_keypair(0)
        b = self.sm.get_keypair(0)
        self.assertEqual(a, b)

    def test_different_indices_different_keys(self):
        self.assertNotEqual(self.sm.get_keypair(0), self.sm.get_keypair(1))

    def test_passphrase_changes_addresses(self):
        # Befund: Passphrase wurde beim Laden verworfen – Ableitung MUSS abweichen
        other = SeedManager().from_mnemonic(TEST_MNEMONIC, passphrase="x")
        self.assertNotEqual(
            self.sm.get_receive_address(0), other.get_receive_address(0)
        )

    def test_invalid_paths_raise(self):
        for bad in ("x/0", "m/abc", "m/-1", "m/2147483648"):
            with self.assertRaises(ValueError, msg=bad):
                self.sm.derive_path(bad)


class TestTransactionSerialization(unittest.TestCase):
    """Befund: Output-Wert wurde signed gepackt, kein Range-Check."""

    def test_negative_value_rejected(self):
        addr = base58check_encode(0x34, b"\x02" * 20)
        out = TxOutput(address=addr, value=-1)
        with self.assertRaises(ValueError):
            out.serialize()

    def test_valid_value_serializes(self):
        addr = base58check_encode(0x34, b"\x02" * 20)
        out = TxOutput(address=addr, value=100_000)
        data = out.serialize()
        self.assertEqual(int.from_bytes(data[:8], "little"), 100_000)

    def test_size_estimate_distinguishes_outputs(self):
        # Befund: Fee-Schätzung nutzte immer 2 Outputs
        self.assertLess(_estimate_tx_size(1, 1), _estimate_tx_size(1, 2))


class TestXTSignature(unittest.TestCase):
    """Befund: Signiert wurde der rohe Query-String, gesendet der URL-enkodierte."""

    def test_build_query_is_urlencoded_and_sorted(self):
        from src.exchange.xt_client import XTClient

        q = XTClient._build_query({"b": "x y", "a": True, "symbol": "doi_usdt"})
        # sortiert, URL-enkodiert, Booleans normalisiert
        self.assertEqual(q, "a=true&b=x+y&symbol=doi_usdt")

    def test_amount_formatting(self):
        from src.exchange.xt_client import _format_amount

        self.assertEqual(_format_amount(0.00001), "0.00001")  # kein "1e-05"
        self.assertEqual(_format_amount(Decimal("0.30")), "0.30")
        self.assertNotIn("e", _format_amount(1e-06))


if __name__ == "__main__":
    unittest.main(verbosity=2)
