"""
Deploy webhook - allows GitHub Actions to trigger deployments via HTTPS.

Uses a shared secret (DEPLOY_WEBHOOK_SECRET) for authentication instead of SSH.
The webhook calls the existing /usr/local/bin/vejapro-update script.
"""

import asyncio
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException

from app.core.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)

DEPLOY_SCRIPT = "/usr/local/bin/vejapro-update"


@router.post("/deploy/webhook")
async def deploy_webhook(
    x_deploy_token: str = Header(None, alias="X-Deploy-Token"),
):
    """Trigger deployment via the existing deploy script.

    Requires X-Deploy-Token header matching DEPLOY_WEBHOOK_SECRET.
    The script needs root (sudoers NOPASSWD rule required).
    """
    settings = get_settings()

    if not settings.deploy_webhook_secret:
        raise HTTPException(404, "Nerastas")

    if not x_deploy_token or not hmac.compare_digest(x_deploy_token, settings.deploy_webhook_secret):
        logger.warning("Deploy webhook: invalid or missing token")
        raise HTTPException(404, "Nerastas")

    logger.info("Deploy webhook triggered")

    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo",
            DEPLOY_SCRIPT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
        output = stdout.decode("utf-8", errors="replace").strip()
        exit_code = proc.returncode

        if exit_code == 0:
            logger.info("Deploy webhook: success (exit %d)", exit_code)
            if settings.expose_error_details:
                return {"status": "success", "exit_code": 0, "output": output}
            return {"status": "success", "exit_code": 0}

        logger.error("Deploy webhook: script failed (exit %d)", exit_code)
        if settings.expose_error_details:
            return {"status": "error", "exit_code": exit_code, "output": output}
        return {"status": "error", "exit_code": exit_code}

    except TimeoutError:
        logger.error("Deploy webhook: script timed out after 180s")
        raise HTTPException(504, "Deploy script timed out") from None
    except FileNotFoundError:
        logger.error("Deploy webhook: script not found at %s", DEPLOY_SCRIPT)
        raise HTTPException(500, "Deploy script not found") from None
    except Exception:
        logger.exception("Deploy webhook: unexpected error")
        raise HTTPException(500, "Deploy failed") from None
