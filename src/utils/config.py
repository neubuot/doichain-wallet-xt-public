"""
Konfiguration laden und validieren.
"""

import os
import yaml
from pathlib import Path


def load_config(config_path: str = None) -> dict:
    """
    Lädt die Konfiguration aus config.yaml.
    
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
    
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    return config


def validate_xt_config(config: dict) -> bool:
    """Prüft ob XT.com API-Konfiguration vorhanden ist."""
    xt = config.get("xt_com", {})
    if not xt.get("api_key") or xt["api_key"] == "DEIN_XT_API_KEY":
        print("⚠️  XT.com API-Key nicht konfiguriert.")
        return False
    if not xt.get("api_secret") or xt["api_secret"] == "DEIN_XT_API_SECRET":
        print("⚠️  XT.com API-Secret nicht konfiguriert.")
        return False
    return True


def validate_tron_config(config: dict) -> bool:
    """Prüft ob Tron-Konfiguration vorhanden ist."""
    tron = config.get("tron", {})
    if not tron.get("full_node"):
        print("⚠️  Tron Full-Node URL nicht konfiguriert.")
        return False
    if not tron.get("usdt_contract"):
        print("⚠️  USDT Contract-Adresse nicht konfiguriert.")
        return False
    return True
