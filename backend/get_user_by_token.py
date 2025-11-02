async def get_user_by_token(
    token: str, caching_client: CachingClient, session: AsyncSession
) -> User | None:

    try:
        jwt_strategy = get_jwt_strategy()

        # Only decode JWT to get user_id, do not query database
        try:
            data = decode_jwt(
                token,
                jwt_strategy.decode_key,
                jwt_strategy.token_audience,
                algorithms=[jwt_strategy.algorithm],
            )
            user_id = data.get("sub")
            if user_id is None:
                return None
        except Exception:
            return None

        # Get user information from cache
        cached_user: dict | None = await caching_client.get(
            endpoint="auth", key=f"jwt:{user_id}"
        )
        if cached_user:
            user = User.from_dict(cached_user)
        else:
            # Query user information from database
            stmt = select(User).where(User.id == user_id)
            user = (await session.execute(stmt)).scalar_one_or_none()

            if user:
                await caching_client.set(
                    endpoint="auth",
                    key=f"jwt:{user_id}",
                    value=user.dict(),
                    expiration_time=timedelta(hours=2),
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Could not validate credentials",
                )

        return user

    except Exception as e:
        logger.warning(f"JWT token validation failed: {e}")
        return None
