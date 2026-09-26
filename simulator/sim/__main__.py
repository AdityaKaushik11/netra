"""Runs every simulated external system in one container:
ONVIF device (:8081), vendor NVR API (:8090), AI analytics engine and edge heartbeat agent."""

import asyncio
import logging
import os

import uvicorn

from sim import analytics, dashcam, onvif_mock, vendor_api


async def serve(app, port: int) -> None:
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    await uvicorn.Server(config).serve()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    tasks = [serve(onvif_mock.app, 8081), serve(vendor_api.app, 8090)]
    if os.getenv("SIM_ANALYTICS_ENABLED", "true") == "true":
        tasks.append(analytics.run_background_traffic())
    if os.getenv("SIM_EDGE_AGENT_ENABLED", "true") == "true":
        tasks.append(analytics.run_edge_heartbeats())
    if os.getenv("SIM_DASHCAM_ENABLED", "true") == "true":
        tasks.append(dashcam.run_dashcam())
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
