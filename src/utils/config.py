"""
Konfiguration laden und validieren.
"""

import logging
import os
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


def load_config(config_path: str = None) -> dict:
    """
    Lädt die Konfiguration aus config.yaml.

    Umgebungsvariablen haben Vorrang vor den Werten in der Datei:
        XT_API_KEY        → xt_com.api_key
        XT_API_SECRET     → xt_com.api_secret
        TRONGRID_API_KEY  → tron.api_key

    Args:
        config_path: Pfad zur Konfigurationsdatei.
                     Standard: config/config.yaml im Projektroot.

    Returns:
        dict mit Konfigurationswerten
    """
    if config_path is None:
        # Projektroot ermitteln (2 Ebenen über src/utils/)
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "config" / "config.yaml"

    config_path = Path(config_path)

    if not config_path.exists():
        example_path = config_path.parent / "config.example.yaml"
        raise FileNotFoundError(
            f"Konfigurationsdatei nicht gefunden: {config_path}\n"
            f"Bitte kopiere {example_path} → {config_path} und fülle deine Werte ein."
        )

    _warn_if_world_readable(config_path)

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Leere Datei → safe_load() liefert None statt dict
    config = config or {}

    return _apply_env_overrides(config)


def _warn_if_world_readable(config_path: Path):
    """
    Warnt (POSIX), wenn die Konfigurationsdatei für Gruppe oder andere
    Benutzer lesbar ist – sie enthält API-Secrets im Klartext.
    """
    if os.name != "posix":
        return
    try:
        mode = config_path.stat().st_mode
    except OSError:
        return
    if mode & 0o077:
        logger.warning(
            f"⚠️  Die Konfigurationsdatei {config_path} ist für Gruppe/andere Benutzer "
            f"lesbar, enthält aber API-Secrets im Klartext! "
            f"Empfehlung: chmod 600 {config_path}"
        )


def _apply_env_overrides(config: dict) -> dict:
    """
    Überschreibt Secrets aus der YAML-Datei mit Umgebungsvariablen,
    sofern diese gesetzt sind (Env-Variablen haben Vorrang).
    """
    overrides = [
        ("XT_API_KEY", "xt_com", "api_key"),
        ("XT_API_SECRET", "xt_com", "api_secret"),
        ("TRONGRID_API_KEY", "tron", "api_key"),
    ]
    for env_var, section, key in overrides:
        value = os.environ.get(env_var)
        if value:
            section_cfg = config.get(section)
            if not isinstance(section_cfg, dict):
                section_cfg = {}
                config[section] = section_cfg
            section_cfg[key] = value
    return config


def validate_xt_config(config: dict) -> bool:
    """Prüft ob XT.com API-Konfiguration vorhanden ist."""
    xt = config.get("xt_com") or {}
    if not xt.get("api_key") or xt["api_key"] == "DEIN_XT_API_KEY":
        print("⚠️  XT.com API-Key nicht konfiguriert.")
        return False
    if not xt.get("api_secret") or xt["api_secret"] == "DEIN_XT_API_SECRET":
        print("⚠️  XT.com API-Secret nicht konfiguriert.")
        return False
    return True


def validate_tron_config(config: dict) -> bool:
    """
    Prüft ob die Tron-Konfiguration vorhanden ist.

    Geprüft wird nur, was tatsächlich verwendet wird: der TronGrid
    API-Key (tron.api_key). Node-URL und USDT-Contract sind fest im
    TronClient hinterlegt und werden nicht aus der Config gelesen.
    """
    tron = config.get("tron") or {}
    if not tron.get("api_key"):
        print("⚠️  TronGrid API-Key nicht konfiguriert (tron.api_key) – "
              "niedrigere Rate-Limits möglich.")
        return False
    return True
