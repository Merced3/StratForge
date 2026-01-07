import httpx

from shared_state import print_log


async def refresh_chart(timeframe, chart_type="live", base_url="http://127.0.0.1:8000"):
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=2.0, read=15.0, write=5.0, pool=5.0)
        ) as client:
            await client.post(
                f"{base_url}/refresh-chart",
                json={"timeframe": timeframe, "chart_type": chart_type},
            )
    except httpx.ReadTimeout:
        print_log("    [refresh_chart] timed out (render likely completed anyway)")
    except Exception as e:
        print_log(f"[refresh_chart] failed: {e}")
