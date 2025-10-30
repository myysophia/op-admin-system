"""Authentication helpers for extracting operator information."""
import logging
from typing import Optional

import base64
import json
import logging
from fastapi import Header, HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


def get_operator_id(authorization: Optional[str] = Header(None)) -> str:
    """Extract operator id from Authorization header."""
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header missing")

    token = authorization.split(" ", 1)[1].strip() if authorization.lower().startswith("bearer ") else authorization.strip()

    try:
        header_b64, payload_b64, _ = token.split(".")
        padded_payload = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(padded_payload.encode("utf-8"))
        payload = json.loads(payload_json.decode("utf-8"))
        operator = payload.get("sub")
        if not operator:
            raise ValueError("sub claim missing")
        return operator
    except Exception as exc:
        logger.error("Failed to parse operator from token: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
