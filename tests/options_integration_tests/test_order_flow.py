import asyncio

import pytest

from options.execution_paper import PaperOrderExecutor
from options.mock_provider import SyntheticOptionsProvider, SyntheticQuoteConfig
from options.order_manager import OptionsOrderManager
from options.quote_service import OptionQuoteService
from options.selection import SelectionRequest


@pytest.mark.anyio
async def test_order_flow_with_synthetic_provider():
    config = SyntheticQuoteConfig(
        underlying_price=500.0,
        strikes_each_side=5,
        price_jitter=0.05,
        spread_pct=0.02,
        min_spread=0.01,
        time_value_atm=0.5,
        time_value_decay=0.03,
        min_time_value=0.1,
        seed=42,
    )
    provider = SyntheticOptionsProvider(
        symbol="SPY",
        expiration="20260106",
        config=config,
    )
    service = OptionQuoteService(
        provider,
        symbol="SPY",
        expiration="20260106",
        poll_interval=0.01,
    )
    await service.start()
    try:
        for _ in range(100):
            if service.get_snapshot():
                break
            await asyncio.sleep(0.01)
        assert service.get_snapshot()

        executor = PaperOrderExecutor(service.get_quote)
        manager = OptionsOrderManager(service, executor)

        request = SelectionRequest(
            symbol="SPY",
                option_type="call",
                expiration="20260106",
                underlying_price=config.underlying_price,
                max_otm=3.0,
            )
        open_result = await manager.open_position(request, quantity=1)
        status = await manager.get_status(open_result.order_result.order_id)

        assert status.status == "filled"
        assert status.avg_fill_price is not None

        position = manager.get_position(open_result.position_id)
        assert position is not None

        sell_submit = await manager.close_position(open_result.position_id)
        assert sell_submit is not None
        sell_status = await manager.get_status(sell_submit.order_result.order_id)
        assert sell_status.status == "filled"
        assert sell_status.avg_fill_price is not None
    finally:
        await service.stop()
