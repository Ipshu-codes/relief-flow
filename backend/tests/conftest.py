import pytest


@pytest.fixture(autouse=True)
def isolate_model_in_unit_tests(monkeypatch):
    import ollama

    async def offline(*args, **kwargs):
        raise ConnectionError('Local inference disabled in automated tests; use the AI evaluation runner')

    monkeypatch.setattr(ollama.AsyncClient, 'generate', offline)
