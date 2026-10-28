from parcelpilot.main import app


def test_app_boots() -> None:
    assert app.title == "ParcelPilot"
    assert app.version == "0.1.0"
