"""Authentication helpers for extracting operator information."""
import base64
import json
import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)


@dataclass
class OperatorContext:
    operator_id: str
    operator_name: str
    token: str
    authorization: str


def _parse_jwt_payload(token: str) -> dict:
    """Parse JWT payload without verifying signature (token treated as trusted)."""
    header_b64, payload_b64, _ = token.split(".")
    padded_payload = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload_json = base64.urlsafe_b64decode(padded_payload.encode("utf-8"))
    return json.loads(payload_json.decode("utf-8"))


def get_operator_context(authorization: Optional[str] = Header(None)) -> OperatorContext:
    """Extract operator context (id & name) from Authorization header."""
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header missing")

    normalized_header = authorization.strip()
    token = (
        normalized_header.split(" ", 1)[1].strip()
        if normalized_header.lower().startswith("bearer ")
        else normalized_header
    )

    try:
        payload = _parse_jwt_payload(token)
        operator_id = payload.get("sub")
        if not operator_id:
            raise ValueError("sub claim missing")
        operator_name = payload.get("operator_name") or payload.get("name") or payload.get("username") or operator_id
        return OperatorContext(
            operator_id=operator_id,
            operator_name=str(operator_name),
            token=token,
            authorization=normalized_header,
        )
    except Exception as exc:
        logger.error("Failed to parse operator from token: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def get_operator_id(authorization: Optional[str] = Header(None)) -> str:
    """Compatibility helper returning only operator id."""
    return get_operator_context(authorization).operator_id
