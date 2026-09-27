import asyncio

from app.core.analysis_gate import AnalysisGate


def test_admits_up_to_the_limit_at_once():
    async def scenario():
        gate = AnalysisGate(limit=1)
        assert await gate.acquire(timeout=0.01)
        assert gate.in_flight == 1
        assert not await gate.acquire(timeout=0.01)  # a second one must wait, and times out
        gate.release()
        assert await gate.acquire(timeout=0.01)

    asyncio.run(scenario())


def test_a_waiter_is_admitted_as_soon_as_a_slot_frees():
    async def scenario():
        gate = AnalysisGate(limit=1)
        await gate.acquire(timeout=0.01)
        waiter = asyncio.create_task(gate.acquire(timeout=1.0))
        await asyncio.sleep(0.05)
        assert gate.waiting == 1
        gate.release()
        assert await waiter
        assert gate.waiting == 0

    asyncio.run(scenario())


def test_refuses_immediately_when_the_wait_queue_is_full():
    async def scenario():
        gate = AnalysisGate(limit=1, max_waiting=1)
        await gate.acquire(timeout=0.01)
        first_waiter = asyncio.create_task(gate.acquire(timeout=1.0))
        await asyncio.sleep(0.01)

        loop = asyncio.get_running_loop()
        started = loop.time()
        assert not await gate.acquire(timeout=1.0)
        assert loop.time() - started < 0.1  # refused without waiting out the timeout

        gate.release()
        assert await first_waiter

    asyncio.run(scenario())
