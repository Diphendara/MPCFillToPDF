from threading import Event

from src.worker_events import (
    FileEvent,
    ProgressEvent,
    RunFinishedEvent,
    VerificationWarningEvent,
    normalize_event,
)


def test_typed_events_preserve_gui_payload_contract():
    assert normalize_event(ProgressEvent("download", 2, 4, "Mazo")) == (
        "progress",
        "download",
        2,
        4,
        "Mazo",
    )
    assert normalize_event(FileEvent(1, 2, "Mazo")) == ("file", 1, 2, "Mazo")


def test_terminal_and_confirmation_events_preserve_gui_payload_contract(tmp_path):
    confirmation = Event()
    assert normalize_event(VerificationWarningEvent([("id", "Carta")], confirmation)) == (
        "verify_warning",
        [("id", "Carta")],
        confirmation,
    )
    assert normalize_event(RunFinishedEvent([tmp_path / "out.pdf"], None, tmp_path, "1s")) == (
        "done",
        [tmp_path / "out.pdf"],
        None,
        tmp_path,
        "1s",
    )
