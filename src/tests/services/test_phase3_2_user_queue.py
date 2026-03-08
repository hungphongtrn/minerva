"""Tests for OSS user queue with idempotency support."""

import asyncio
import pytest

from src.services.oss_user_queue import (
    OssUserQueue,
    IdempotencyStatus,
    get_oss_user_queue,
    reset_oss_user_queue,
)


class TestOssUserQueue:
    """Test suite for OssUserQueue."""

    @pytest.fixture(autouse=True)
    def reset_queue(self):
        """Reset the global queue before each test."""
        reset_oss_user_queue()
        yield
        reset_oss_user_queue()

    @pytest.fixture
    def queue(self):
        """Create a fresh queue instance."""
        return OssUserQueue()

    async def test_serial_execution_per_user(self, queue):
        """Test that requests for the same user execute serially."""
        execution_order = []

        async def operation(user):
            await asyncio.sleep(0.01)  # Small delay
            execution_order.append(user)
            return f"result-{user}"

        # Start two operations for same user concurrently
        task1 = asyncio.create_task(queue.execute("user-1", None, operation, "op1"))
        task2 = asyncio.create_task(queue.execute("user-1", None, operation, "op2"))

        results = await asyncio.gather(task1, task2)

        # Both should succeed
        assert all(r.success for r in results)
        # Execution should be serial (one after another)
        assert len(execution_order) == 2

    async def test_concurrent_execution_different_users(self, queue):
        """Test that requests for different users execute concurrently."""
        start_times = {}

        async def operation(user):
            start_times[user] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.05)
            return f"result-{user}"

        # Start operations for different users concurrently
        task1 = asyncio.create_task(queue.execute("user-1", None, operation, "user-1"))
        task2 = asyncio.create_task(queue.execute("user-2", None, operation, "user-2"))

        await asyncio.gather(task1, task2)

        # Both should start around the same time (concurrent)
        time_diff = abs(start_times["user-1"] - start_times["user-2"])
        assert time_diff < 0.03  # Should start within 30ms

    async def test_idempotency_returns_cached_result(self, queue):
        """Test that duplicate idempotency keys return cached results."""
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            return f"result-{call_count}"

        # First execution
        result1 = await queue.execute("user-1", "key-1", operation)
        assert result1.success
        assert result1.result == "result-1"
        assert not result1.was_cached

        # Duplicate execution - should return cached
        result2 = await queue.execute("user-1", "key-1", operation)
        assert result2.success
        assert result2.result == "result-1"
        assert result2.was_cached

        # Operation should only be called once
        assert call_count == 1

    async def test_idempotency_different_keys_execute(self, queue):
        """Test that different idempotency keys result in separate executions."""
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            return f"result-{call_count}"

        # Different keys for same user
        result1 = await queue.execute("user-1", "key-1", operation)
        result2 = await queue.execute("user-1", "key-2", operation)

        assert result1.success
        assert result2.success
        # Both should execute
        assert call_count == 2

    async def test_idempotency_same_key_different_users(self, queue):
        """Test that same idempotency key for different users is separate."""
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            return f"result-{call_count}"

        # Same key, different users
        result1 = await queue.execute("user-1", "key-1", operation)
        result2 = await queue.execute("user-2", "key-1", operation)

        assert result1.success
        assert result2.success
        # Both should execute (different users)
        assert call_count == 2

    async def test_in_progress_wait_and_return(self, queue):
        """Test that concurrent requests with same key wait and return same result."""
        call_count = 0

        async def slow_operation():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)
            return f"result-{call_count}"

        # Start two operations with same key concurrently
        task1 = asyncio.create_task(queue.execute("user-1", "key-1", slow_operation))
        task2 = asyncio.create_task(queue.execute("user-1", "key-1", slow_operation))

        results = await asyncio.gather(task1, task2)

        # Both should succeed with same result
        assert all(r.success for r in results)
        assert results[0].result == results[1].result == "result-1"
        # Operation should only be called once
        assert call_count == 1

    async def test_failed_operation_cached(self, queue):
        """Test that failed operations are also cached."""
        call_count = 0

        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Operation failed")

        # First execution - should fail
        result1 = await queue.execute("user-1", "key-1", failing_operation)
        assert not result1.success
        assert "Operation failed" in result1.error
        assert not result1.was_cached

        # Duplicate execution - should return cached failure
        result2 = await queue.execute("user-1", "key-1", failing_operation)
        assert not result2.success
        assert "Operation failed" in result2.error
        assert result2.was_cached

        # Operation should only be called once
        assert call_count == 1

    async def test_cache_ttl_expires(self, queue):
        """Test that cache entries expire after TTL."""
        queue = OssUserQueue(ttl_seconds=0.1)  # Short TTL

        async def operation():
            return "result"

        # First execution
        await queue.execute("user-1", "key-1", operation)

        # Wait for TTL to expire
        await asyncio.sleep(0.15)

        # Cleanup should remove expired entry
        queue._cleanup_expired("user-1")

        # Entry should be gone
        assert ("user-1", "key-1") not in queue._idempotency_cache

    async def test_max_entries_limit(self, queue):
        """Test that max entries per user is enforced."""
        queue = OssUserQueue(max_entries_per_user=3)

        async def operation():
            return "result"

        # Add 3 entries
        for i in range(3):
            await queue.execute("user-1", f"key-{i}", operation)

        # All should exist
        assert len(queue._entries_per_user["user-1"]) == 3

        # Add 4th entry - should trigger cleanup
        await queue.execute("user-1", "key-3", operation)

        # Should still be at max
        assert len(queue._entries_per_user["user-1"]) == 3

    async def test_no_idempotency_key_executes_each_time(self, queue):
        """Test that operations without idempotency key execute each time."""
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            return f"result-{call_count}"

        # Execute multiple times without idempotency key
        result1 = await queue.execute("user-1", None, operation)
        result2 = await queue.execute("user-1", None, operation)
        result3 = await queue.execute("user-1", None, operation)

        assert all(r.success for r in [result1, result2, result3])
        # Should execute 3 times
        assert call_count == 3

    async def test_cache_stats(self, queue):
        """Test cache statistics."""

        async def operation():
            return "result"

        # Add entries in different states
        await queue.execute("user-1", "key-1", operation)

        stats = queue.get_cache_stats("user-1")
        assert stats["total"] == 1
        assert stats["completed"] == 1

    async def test_clear_cache(self, queue):
        """Test clearing cache."""

        async def operation():
            return "result"

        await queue.execute("user-1", "key-1", operation)
        await queue.execute("user-2", "key-1", operation)

        # Clear specific user
        queue.clear_cache("user-1")
        assert ("user-1", "key-1") not in queue._idempotency_cache
        assert ("user-2", "key-1") in queue._idempotency_cache

        # Clear all
        queue.clear_cache()
        assert len(queue._idempotency_cache) == 0


class TestOssUserQueueSingleton:
    """Test the singleton instance."""

    @pytest.fixture(autouse=True)
    def reset_queue(self):
        """Reset the global queue before each test."""
        reset_oss_user_queue()
        yield
        reset_oss_user_queue()

    def test_singleton_returns_same_instance(self):
        """Test that get_oss_user_queue returns the same instance."""
        queue1 = get_oss_user_queue()
        queue2 = get_oss_user_queue()
        assert queue1 is queue2

    def test_reset_creates_new_instance(self):
        """Test that reset creates a new instance."""
        queue1 = get_oss_user_queue()
        reset_oss_user_queue()
        queue2 = get_oss_user_queue()
        assert queue1 is not queue2
