import asyncio
from pathlib import Path

from agentsociety.cityagent import default
from agentsociety.configs import (
    AgentsConfig,
    Config,
    EnvConfig,
    ExpConfig,
    LLMConfig,
    MapConfig,
)
from agentsociety.configs.agent import AgentConfig
from agentsociety.configs.exp import WorkflowStepConfig, WorkflowType
from agentsociety.environment import EnvironmentConfig
from agentsociety.llm import LLMProviderType
from agentsociety.simulation import AgentSociety
from agentsociety.storage import DatabaseConfig

EXAMPLE_DIR = Path(__file__).resolve().parent
MAP_FILE_PATH = str((EXAMPLE_DIR / "../../agentsociety_data/beijing.pb").resolve())
PROFILE_FILE_PATH = str((EXAMPLE_DIR / "profiles_hurricane.json").resolve())


config = Config(
    llm=[
        LLMConfig(
            provider=LLMProviderType.ZhipuAI,
            base_url=None,
            api_key="4d963afd591d4c93940b08b06d766e91.bWaMIWJnuKhOUo7y",
            model="glm-4-flashx",
            concurrency=20,
            timeout=60,
        )
    ],
    env=EnvConfig(
        db=DatabaseConfig(
            enabled=True,
            db_type="sqlite",
            pg_dsn=None,
        ),
    ),
    map=MapConfig(
        file_path=MAP_FILE_PATH,
    ),
    agents=AgentsConfig(
        citizens=[
            AgentConfig(
                agent_class="citizen",
                number=10,
                memory_from_file=PROFILE_FILE_PATH,
            )
        ],
    ),  # type: ignore
    exp=ExpConfig(
        name="hurricane_impact_local_1day",
        workflow=[
            WorkflowStepConfig(
                type=WorkflowType.ENVIRONMENT_INTERVENE,
                key="weather",
                value="Hurricane Dorian has made landfall in other cities, travel is slightly affected, and winds can be felt.",
            ),
            WorkflowStepConfig(
                type=WorkflowType.RUN,
                days=1,
                ticks_per_step=1800,
            ),
        ],
        environment=EnvironmentConfig(
            start_tick=6 * 60 * 60,
        ),
    ),
)
config = default(config)


async def main():
    agentsociety = AgentSociety.create(config)
    try:
        await agentsociety.init()
        await agentsociety.run()
    finally:
        await agentsociety.close()


if __name__ == "__main__":
    asyncio.run(main())
