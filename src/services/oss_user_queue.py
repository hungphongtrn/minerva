"""OSS user queue service for per-user request ordering and idempotency.

Provides:
- Per-user async request serialization (one request per user at a time)
- In-process idempotency keyed by (X-User-ID, X-Idempotency-Key)
- TTL-based cache eviction to prevent unbounded memory growth
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple
from enum import Enum


class IdempotencyStatus(Enum):
    """Status of an idempotent request."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IdempotencyEntry:
    """Entry in the idempotency cache."""

    status: IdempotencyStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    event_waiters: list[asyncio.Event] = field(default_factory=list)


@dataclass
class OssQueueResult:
    """Result of queuing and executing a user request."""

    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    was_cached: bool = False  # True if returned from idempotency cache


class OssUserQueue:
    """Per-user async queue with idempotency support.

    This class manages:
    1. Per-user request serialization - only one request per user executes at a time
    2. In-process idempotency - duplicate requests with same idempotency key
       return cached results instead of re-executing

    The idempotency cache is in-process only (not distributed). For multi-replica
    deployments, requests must be sticky-routed or an external cache is needed.

    Cache limits:
    - TTL: 5 minutes for completed entries
    - Max entries per user: 100
    """

    DEFAULT_TTL_SECONDS = 300  # 5 minutes
    MAX_ENTRIES_PER_USER = 100

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries_per_user: int = MAX_ENTRIES_PER_USER,
    ):
        """Initialize the OSS user queue.

        Args:
            ttl_seconds: TTL for completed idempotency entries
            max_entries_per_user: Maximum idempotency entries per user
        """
        self._ttl_seconds = ttl_seconds
        self._max_entries_per_user = max_entries_per_user

        # Per-user locks for request serialization
        self._user_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

        # Idempotency cache: (user_id, idempotency_key) -> IdempotencyEntry
        self._idempotency_cache: Dict[Tuple[str, str], IdempotencyEntry] = {}

        # Track entry counts per user for cleanup
        self._entries_per_user: Dict[str, list[Tuple[str, float]]] = defaultdict(list)

    def _make_key(self, user_id: str, idempotency_key: str) -> Tuple[str, str]:
        """Create cache key from user_id and idempotency_key."""
        return (user_id, idempotency_key)

    def _cleanup_expired(self, user_id: str) -> None:
        """Remove expired entries for a user."""
        now = time.time()
        expired_keys = [
            key
            for key, entry in self._idempotency_cache.items()
            if key[0] == user_id
            and entry.completed_at
            and (now - entry.completed_at) > self._ttl_seconds
        ]
        for key in expired_keys:
            del self._idempotency_cache[key]
            # Remove from user's entry list
            self._entries_per_user[user_id] = [
                (k, ts) for k, ts in self._entries_per_user[user_id] if k != key[1]
            ]

    def _enforce_max_entries(self, user_id: str) -> None:
        """Enforce max entries limit for a user (remove oldest)."""
        user_entries = self._entries_per_user[user_id]
        if len(user_entries) > self._max_entries_per_user:
            # Sort by timestamp (oldest first) and remove oldest
            user_entries.sort(key=lambda x: x[1])
            to_remove = len(user_entries) - self._max_entries_per_user
            for i in range(to_remove):
                old_key = self._make_key(user_id, user_entries[i][0])
                if old_key in self._idempotency_cache:
                    del self._idempotency_cache[old_key]
            # Update entry list
            self._entries_per_user[user_id] = user_entries[to_remove:]

    async def execute(
        self,
        user_id: str,
        idempotency_key: Optional[str],
        operation: Callable[..., Any],
        *args,
        **kwargs,
    ) -> OssQueueResult:
        """Execute an operation with per-user serialization and idempotency.

        This method:
        1. If idempotency_key provided, checks cache for existing result
        2. If in-progress, waits for completion and returns result
        3. If completed recently, returns cached result
        4. Acquires per-user lock for serialization
        5. Executes operation
        6. Caches result if idempotency_key provided

        Args:
            user_id: External user ID (X-User-ID)
            idempotency_key: Optional idempotency key (X-Idempotency-Key)
            operation: Async callable to execute
            *args, **kwargs: Arguments for operation

        Returns:
            OssQueueResult with success status and result/error
        """
        # If no idempotency key, just serialize and execute
        if not idempotency_key:
            async with self._user_locks[user_id]:
                try:
                    result = await operation(*args, **kwargs)
                    return OssQueueResult(success=True, result=result)
                except Exception as e:
                    return OssQueueResult(success=False, error=str(e))

        cache_key = self._make_key(user_id, idempotency_key)

        # Check idempotency cache
        if cache_key in self._idempotency_cache:
            entry = self._idempotency_cache[cache_key]

            if entry.status == IdempotencyStatus.IN_PROGRESS:
                # Wait for completion
                waiter = asyncio.Event()
                entry.event_waiters.append(waiter)
                await waiter.wait()

                # Re-check entry after waiting
                entry = self._idempotency_cache.get(cache_key)
                if not entry:
                    # Entry was cleaned up during wait
                    pass
                elif entry.status == IdempotencyStatus.COMPLETED:
                    return OssQueueResult(
                        success=True,
                        result=entry.result,
                        was_cached=True,
                    )
                elif entry.status == IdempotencyStatus.FAILED:
                    return OssQueueResult(
                        success=False,
                        error=entry.error,
                        was_cached=True,
                    )

            elif entry.status == IdempotencyStatus.COMPLETED:
                # Return cached result
                return OssQueueResult(
                    success=True,
                    result=entry.result,
                    was_cached=True,
                )

            elif entry.status == IdempotencyStatus.FAILED:
                # Return cached error
                return OssQueueResult(
                    success=False,
                    error=entry.error,
                    was_cached=True,
                )

        # Create cache entry
        entry = IdempotencyEntry(status=IdempotencyStatus.IN_PROGRESS)
        self._idempotency_cache[cache_key] = entry
        self._entries_per_user[user_id].append((idempotency_key, time.time()))

        # Cleanup and enforce limits
        self._cleanup_expired(user_id)
        self._enforce_max_entries(user_id)

        # Execute with per-user lock
        async with self._user_locks[user_id]:
            try:
                result = await operation(*args, **kwargs)

                # Update cache entry as completed
                entry.status = IdempotencyStatus.COMPLETED
                entry.result = result
                entry.completed_at = time.time()

                # Wake up waiters
                for waiter in entry.event_waiters:
                    waiter.set()
                entry.event_waiters.clear()

                return OssQueueResult(success=True, result=result)

            except Exception as e:
                # Update cache entry as failed
                entry.status = IdempotencyStatus.FAILED
                entry.error = str(e)
                entry.completed_at = time.time()

                # Wake up waiters
                for waiter in entry.event_waiters:
                    waiter.set()
                entry.event_waiters.clear()

                return OssQueueResult(success=False, error=str(e))

    def get_cache_stats(self, user_id: str) -> Dict[str, int]:
        """Get cache statistics for a user.

        Args:
            user_id: External user ID

        Returns:
            Dict with total, in_progress, completed, failed counts
        """
        entries = [entry for key, entry in self._idempotency_cache.items() if key[0] == user_id]

        return {
            "total": len(entries),
            "in_progress": sum(1 for e in entries if e.status == IdempotencyStatus.IN_PROGRESS),
            "completed": sum(1 for e in entries if e.status == IdempotencyStatus.COMPLETED),
            "failed": sum(1 for e in entries if e.status == IdempotencyStatus.FAILED),
        }

    def clear_cache(self, user_id: Optional[str] = None) -> None:
        """Clear idempotency cache.

        Args:
            user_id: If provided, only clear entries for this user.
                     If None, clear all entries.
        """
        if user_id:
            keys_to_remove = [key for key in self._idempotency_cache.keys() if key[0] == user_id]
            for key in keys_to_remove:
                del self._idempotency_cache[key]
            self._entries_per_user[user_id] = []
        else:
            self._idempotency_cache.clear()
            self._entries_per_user.clear()


# Module-level singleton instance
_oss_user_queue: Optional[OssUserQueue] = None


def get_oss_user_queue() -> OssUserQueue:
    """Get the global OSS user queue instance.

    Returns:
        OssUserQueue singleton instance
    """
    global _oss_user_queue
    if _oss_user_queue is None:
        _oss_user_queue = OssUserQueue()
    return _oss_user_queue


def reset_oss_user_queue() -> None:
    """Reset the global OSS user queue instance (for testing)."""
    global _oss_user_queue
    _oss_user_queue = None
