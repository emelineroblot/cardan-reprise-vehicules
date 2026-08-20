"""Entrypoint ASGI Vercel — plan.md § 3.2 / § 3.8.

Le runtime Python de Vercel sert directement une application ASGI. Aucune migration n'est
jouée ici (§ 3.8-3) : `alembic upgrade head` est une commande manuelle/CI, jamais exécutée au
démarrage d'une fonction serverless.
"""

from app.main import app

__all__ = ["app"]
