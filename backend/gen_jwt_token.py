from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, Tuple

import jwt
from fastapi_users.authentication import JWTStrategy
from fastapi_users.jwt import decode_jwt

JWT_SECRET_KEY="e139dea2c086ce9fedbc7b0e67dab95353d667ff1a8167d90c6d6a4a8b12b101"
JWT_ALGORITHM = "HS256"


# Align with project auth configuration
def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=JWT_SECRET_KEY,
        lifetime_seconds=60 * 60,
        algorithm=JWT_ALGORITHM
    )


def _parse_extra_kv(pairs: list[str] | None) -> Dict[str, Any]:
    if not pairs:
        return {}
    result: Dict[str, Any] = {}
    for item in pairs:
        if "=" not in item:
            raise ValueError(f"Invalid --extra format: '{item}'. Use key=value")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"Invalid --extra key in '{item}'")
        # Try to coerce JSON for convenience (e.g., true, 123, {"a":1})
        try:
            coerced = json.loads(value)
        except Exception:
            coerced = value
        result[key] = coerced
    return result


def _build_claims(
    *,
    sub: str,
    audience: Any,
    expires_minutes: int,
    extras: Dict[str, Any],
) -> Dict[str, Any]:
    now = int(time.time())
    exp = now + int(expires_minutes) * 60
    claims: Dict[str, Any] = {"sub": sub, "aud": audience, "iat": now, "exp": exp}
    # Merge extras (user supplied claims override defaults except reserved ones)
    for k, v in extras.items():
        if k in {"sub", "aud", "iat", "exp"}:
            continue
        claims[k] = v
    return claims


def _sign_token(claims: Dict[str, Any], *, algorithm: str) -> str:
    # For HS* algorithms, the secret is symmetric
    secret = JWT_SECRET_KEY
    token = jwt.encode(claims, secret, algorithm=algorithm)
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def _verify_with_strategy(token: str) -> Tuple[Dict[str, Any], str, str]:
    strategy = get_jwt_strategy()
    # fastapi_users expects audience check and algorithms list
    payload = decode_jwt(
        token,
        strategy.decode_key,  # type: ignore[attr-defined]
        strategy.token_audience,  # type: ignore[attr-defined]
        algorithms=[strategy.algorithm],  # type: ignore[attr-defined]
    )
    return payload, strategy.token_audience, strategy.algorithm  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a JWT compatible with project auth settings",
    )
    parser.add_argument("--user-id", "--sub", dest="sub", required=True, help="subject/user id")
    parser.add_argument(
        "--expires-minutes",
        type=int,
        default=3600,
        help="token lifetime in minutes (default: settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)",
    )
    parser.add_argument(
        "--aud",
        dest="aud",
        default=None,
        help="override audience (default: strategy.token_audience)",
    )
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        metavar="key=value",
        help="additional claims (repeatable)",
    )
    parser.add_argument(
        "--format",
        choices=["token", "json"],
        default="token",
        help="output format (token only or JSON with preview)",
    )

    args = parser.parse_args(argv)

    strategy = get_jwt_strategy()
    # Determine audience: use CLI override (supports comma-separated) or strategy default
    if args.aud:
        if "," in args.aud:
            audience: Any = [s.strip() for s in args.aud.split(",") if s.strip()]
        else:
            audience = args.aud.strip()
    else:
        audience = strategy.token_audience  # type: ignore[attr-defined]
    algorithm = strategy.algorithm  # type: ignore[attr-defined]

    extras = _parse_extra_kv(args.extra)
    claims = _build_claims(
        sub=str(args.sub),
        audience=audience,
        expires_minutes=int(args.expires_minutes),
        extras=extras,
    )

    token = _sign_token(claims, algorithm=str(algorithm))

    # Verify using the same strategy decode routine to ensure compatibility
    try:
        verified_payload, verified_aud, verified_alg = _verify_with_strategy(token)
    except Exception as e:
        print(f"[error] token verification failed: {e}", file=sys.stderr)
        return 1

    if args.format == "token":
        print(token)
    else:
        out = {
            "token": token,
            "algorithm": verified_alg,
            "audience": verified_aud,
            "claims": verified_payload,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


