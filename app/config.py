"""Configuration, lue une seule fois au démarrage depuis .env."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parent.parent
load_dotenv(RACINE / ".env")

DOSSIER_RESSOURCES = RACINE / "ressources"


@dataclass(frozen=True)
class Config:
    ifs_base_url: str = os.getenv("IFS_BASE_URL", "").rstrip("/")
    ifs_realm: str = os.getenv("IFS_REALM", "")
    ifs_client_id: str = os.getenv("IFS_CLIENT_ID", "")
    # repr=False : un secret n'a rien à faire dans une trace de pile.
    ifs_client_secret: str = field(default=os.getenv("IFS_CLIENT_SECRET", ""), repr=False)
    ifs_oidc_redirect_uri: str = os.getenv("IFS_OIDC_REDIRECT_URI", "")
    ifs_oidc_scope: str = os.getenv("IFS_OIDC_SCOPE", "openid")
    secret_session: str = field(
        default=os.getenv("SESSION_SECRET", "") or secrets.token_urlsafe(32), repr=False
    )
    langue: str = os.getenv("EDITIQUE_LANGUE", "fr")
    # Le serveur Armony auquel relayer ce que l'application ne produit pas encore (la valeur d'origine du
    # paramètre IFS ARMONY_SERVER, ex. https://armony-qua.ga.fr/AxData_Rec sur CFG).
    armony_relais: str = os.getenv("ARMONY_RELAIS", "").rstrip("/")

    @property
    def instance_ifs(self) -> str:
        """Quelle instance IFS, **lue dans l'URL** : gafr-tst -> TST, gafr -> PROD.

        Dérivée plutôt que déclarée : une étiquette saisie à côté de l'URL finit
        par la contredire, et c'est l'URL qui décide d'où viennent les données.
        """
        hote = (urlparse(self.ifs_base_url).hostname or "").split(".")[0]
        if not hote:
            return ""
        return hote.split("-", 1)[1].upper() if "-" in hote else "PROD"

    @property
    def issuer(self) -> str:
        if not (self.ifs_base_url and self.ifs_realm):
            return ""
        return f"{self.ifs_base_url}/auth/realms/{self.ifs_realm}"

    @property
    def url_projection(self) -> str:
        return f"{self.ifs_base_url}/main/ifsapplications/projection/v1"

    def pourquoi_sso_incomplet(self) -> str | None:
        """None si le login IFS peut partir, sinon ce qui manque, nommé.

        Keycloak répond « invalid redirect_uri » ou « client not found » sans dire
        quelle variable est vide : autant refuser avant de rediriger.
        """
        manquants = [
            nom
            for nom, valeur in (
                ("IFS_BASE_URL", self.ifs_base_url),
                ("IFS_REALM", self.ifs_realm),
                ("IFS_CLIENT_ID", self.ifs_client_id),
                ("IFS_CLIENT_SECRET", self.ifs_client_secret),
                ("IFS_OIDC_REDIRECT_URI", self.ifs_oidc_redirect_uri),
            )
            if not valeur
        ]
        return f"Il manque dans .env : {', '.join(manquants)}." if manquants else None


config = Config()
