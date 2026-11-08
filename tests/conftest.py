import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
ASSETS = os.path.join(ROOT, "test_assets")


@pytest.fixture(scope="session", autouse=True)
def assets():
    if not os.path.isfile(os.path.join(ASSETS, "robot_jerarquia.fbx")):
        from tests.make_assets import main
        main(ASSETS)
    return ASSETS


def asset(name: str) -> str:
    return os.path.join(ASSETS, name)
