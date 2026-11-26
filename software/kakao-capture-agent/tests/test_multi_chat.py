import json
import threading
from dataclasses import replace
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.api.incoming_llm import IncomingMessage, parse_incoming
from app.api.operations_client import OperationsResult
from app.api.workflow_llm import check_cancel
from app.automation.monitoring_service import MonitoringService
from app.automation.multi_chat import MultiChatWorkflow
from app.automation.unified_workflow import UnifiedProcessor, UnifiedWorkflow
from app.config import Config, WatchedChat, load, save
from app.models import AgentError, Cancelled, ForegroundLost, Selection, State, Target
from app.storage.chat_paths import chat_queue_key
from tests.test_automation import Capture, Desktop


def targets(count=3):
    return [Target(i, 1, "start", "kakao.exe", "chat", f"Room {i}") for i in range(1, count + 1)]


def test_selected_chats_persist_independent_ids_and_reselection(tmp_path):
    config = Config(target=targets()[0], chat_id="existing-chat")
    config.select_agent_chats(targets())
    assert config.agent_chats[0].chat_id == "existing-chat"
    original = config.agent_chats.copy()
    path = tmp_path / "config.json"
    save(path, config)
    restored = load(path)
    assert restored.agent_chats == original
    snapshots = restored.agent_configs()
    assert len({c.chat_id for c in snapshots}) == 3
    assert [c.target for c in snapshots] == targets()
    snapshots[1].chat_id = "changed"
    assert restored.agent_chats == original
    # Explicitly choosing new handles for the same chats preserves their queues.
    restored.select_agent_chats([replace(t, hwnd=t.hwnd + 100) for t in targets()])
    assert [c.chat_id for c in restored.agent_chats] == [c.chat_id for c in original]
    # A primary chat label edited in Settings also reaches its workflow snapshot.
    restored.chat_id = "new-label"
    assert restored.agent_configs()[0].chat_id == "new-label"


def test_legacy_config_and_selection_limits(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"version": 1, "chat_id": "legacy"}')
    assert load(path).agent_chats == []
    config = Config()
    for selected in ([], targets(4), [targets()[0]] * 2):
        with pytest.raises(ValueError):
            config.select_agent_chats(selected)
        assert not config.agent_chats
    config.select_agent_chats(targets())
    config.agent_chats[1] = WatchedChat(targets()[1], config.chat_id)
    with pytest.raises(ValueError, match="unique"):
        save(path, config)
    config.chat_id = None
    with pytest.raises(ValueError, match="primary conversation"):
        config.validate()


@pytest.fixture
def fleet(config, queue, region, monkeypatch):
    config.select_agent_chats(targets())
    config.auto_reply_cooldown_seconds = 1
    config.operations_url = "https://operations.test"
    config.operations_username = "tester"
    environment = SimpleNamespace(foreground=None, invalid=set())
    captures, sends, operations, comparisons, logs, names = [], [], [], [], [], []
    chat_logs = []
    gates = {}
    now = [0.0]

    class ChatDesktop:
        def __init__(self, config):
            self.config = config
            self.frame = np.full((100, 80, 3), config.target.hwnd * 30, dtype=np.uint8)

        def suggest_chat_region(self):
            if self.config.target.hwnd in environment.invalid:
                raise AgentError("Target closed or resized")
            return Selection(region, 300, 300, 96)

        def activate_target(self, cancel):
            check_cancel(cancel)
            self.suggest_chat_region()
            environment.foreground = self.config.target.hwnd
            self.validate()

        def validate(self):
            self.suggest_chat_region()
            if environment.foreground != self.config.target.hwnd:
                raise ForegroundLost("Other chat has focus")
            return region

    class ChatCapture:
        def __init__(self, desktop):
            self.desktop = desktop

        def grab(self):
            self.desktop.validate()
            captures.append(environment.foreground)
            return self.desktop.frame.copy(), region

    class Sender:
        composer_cleared = True
        input_started = False

        def __init__(self, desktop, cancel):
            self.desktop, self.cancel = desktop, cancel

        def send(self, text, **kwargs):
            check_cancel(self.cancel)
            self.desktop.validate()
            sends.append((environment.foreground, text))
            return "composer cleared"

    class LLM:
        def incoming(self, png, cancel):
            check_cancel(cancel)
            marker = int(cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)[0, 0, 0])
            return IncomingMessage("incoming", f"위치조정/Person{marker}/Road{marker}")

        def classify_latest(self, png, cancel):
            return self.incoming(png, cancel)

        def classify(self, before, after, cancel, **kwargs):
            markers = [
                int(cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)[0, 0, 0])
                for png in (before, after)
            ]
            comparisons.append(markers)
            return self.incoming(after, cancel)

        async def run_operation(self, operation, cancel):
            check_cancel(cancel)
            return await operation()

        async def request(self, messages, **kwargs):
            source = json.loads(messages[-1]["content"])
            if "text" in source:
                return json.dumps({"requests": [source["text"]]})
            _, name, address = source["message"].split("/")
            return json.dumps(
                {
                    "action": "기기위치조정",
                    "action_text": "위치조정",
                    "name": name,
                    "address": address,
                }
            )

    class Operations:
        def __init__(self, chat):
            self.chat = chat

        def run(self, request, cancel):
            gate = gates.get(self.chat)
            if gate:
                gate[0].set()
                while not gate[1].wait(0.01):
                    check_cancel(cancel)
            check_cancel(cancel)
            operations.append((self.chat, request))
            return OperationsResult("completed", f"Response for {request['name']}", True)

    desktop = Desktop(region)
    monkeypatch.setattr(
        "app.automation.unified_workflow.create_unified_operations",
        lambda config: Operations(config.target.hwnd),
    )
    service = MonitoringService(
        desktop,
        Capture(desktop, np.zeros((100, 80, 3), dtype=np.uint8)),
        queue,
        config,
        lambda *a: None,
        lambda _: None,
        logs.append,
        chat_activity=lambda key, message: chat_logs.append((key, message)),
    )

    def create(mode):
        group = MultiChatWorkflow(
            service.auto_catch,
            config.agent_configs(),
            queue,
            service.stop_input,
            lambda _: None,
            lambda message: service.transition(State.INITIALIZING, message),
            lambda _: None,
            logs.append,
            mode,
            desktop_factory=ChatDesktop,
            capture_factory=ChatCapture,
            sender_factory=Sender,
            preview_chat=names.append,
            chat_activity=service.chat_activity,
        )
        for workflow in group.workflows:
            workflow.llm_factory = lambda _: LLM()
            workflow.clock = lambda: now[0]
            if not isinstance(workflow, UnifiedWorkflow):
                workflow.processor_factory = lambda w=workflow: UnifiedProcessor(
                    w.journal, Operations(w.config.target.hwnd)
                )
        return group

    service.create_multi_chat = create
    fleet = SimpleNamespace(
        service=service,
        config=config,
        queue=queue,
        environment=environment,
        gates=gates,
        captures=captures,
        sends=sends,
        operations=operations,
        comparisons=comparisons,
        logs=logs,
        chat_logs=chat_logs,
        now=now,
        names=names,
    )
    yield fleet
    service.command("stop")
    service.dispatch("stop")


def complete_round(fleet):
    admit_screens(fleet)
    for workflow in fleet.service.auto_catch.workflows:
        if workflow.worker:
            workflow.worker.join(2)
            assert not workflow.worker.is_alive()
    fleet.service.poll_auto_catch()


def admit_screens(fleet):
    for workflow in fleet.service.auto_catch.workflows:
        if getattr(workflow, "screening", None) is not None:
            workflow.screening.result(timeout=2)
            workflow.finish_screen()


def test_only_keyword_bubbles_enter_each_windows_persistent_queue(fleet):
    f = fleet
    f.config.select_agent_chats(targets(2))
    create = f.service.create_multi_chat
    commands = ("전원연결/가상인/가상로 1", "가상인/전원연결/가상로 1", "가상인/가상로 1/전원연결")

    def create_group(mode):
        group = create(mode)
        for workflow in group.workflows:
            llm = workflow.llm_factory(None)
            llm.classify_latest = lambda *_: IncomingMessage("incoming", "안녕하세요")
            workflow.llm_factory = lambda _, llm=llm: llm
        return group

    f.service.create_multi_chat = create_group
    f.service.dispatch("auto_catch")
    admit_screens(f)
    first, second = f.service.auto_catch.workflows

    def rows():
        with f.queue.connect() as db:
            return db.execute("SELECT chat_key,incoming FROM image_reply_queue ORDER BY id").fetchall()

    first.llm.classify = lambda *a, **kw: IncomingMessage("incoming", "오늘 회의 시간 알려주세요")
    second.llm.classify = lambda *a, **kw: IncomingMessage("outgoing", commands[0])
    for workflow in (first, second):
        workflow.desktop.frame[:] = 110
        workflow.capture_changes()
    admit_screens(f)
    assert not rows() and not list(first.jobs.images.rglob("*.png"))

    bubbles = ("감사합니다", commands[0], "다음에 봐요", commands[1], commands[2])
    second.llm.classify = lambda *a, **kw: IncomingMessage(
        "incoming", "\n".join(bubbles), bubbles=bubbles, bubble_senders=("A", "B", "C", "D", "E")
    )
    second.desktop.frame[:] = 170
    second.capture_changes()
    admit_screens(f)
    row, = rows()
    result = json.loads(row["incoming"])
    assert row["chat_key"] == second.chat_key
    assert result["bubbles"] == list(commands) and result["bubble_senders"] == ["B", "D", "E"]
    assert len(list(first.jobs.images.rglob("*.png"))) == 1
    for _ in range(5):
        f.now[0] += 2
        f.service.poll_auto_catch()
        complete_round(f)
    assert [(chat, request["message"]) for chat, request in f.operations] == [
        (2, command) for command in commands
    ]
    assert len(rows()) == 3 and first.reply_count == 0 and second.reply_count == 3


def test_slow_keyword_screen_leaves_other_window_free_to_reply(fleet):
    f = fleet
    f.config.select_agent_chats(targets(2))
    f.service.dispatch("auto_catch")
    admit_screens(f)
    f.service.poll_auto_catch()
    complete_round(f)
    first, second = f.service.auto_catch.workflows
    entered, release = threading.Event(), threading.Event()

    def slow_read(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return IncomingMessage("incoming", "감사합니다")

    first.llm.classify = slow_read
    try:
        f.now[0] += 2
        first.desktop.frame[:] = 100
        second.desktop.frame[:] = 170
        f.service.poll_auto_catch()
        assert entered.wait(2)
        if second.screening is not None:
            second.screening.result(timeout=2)
        second.process_queue()
        if second.worker is not None:
            second.worker.join(2)
        f.service.poll_auto_catch()
        assert first.jobs.count(first.chat_key) == 0 and not first.screening.done()
        assert f.sends[-1] == (2, "Response for Person170")
    finally:
        release.set()


def stop(fleet):
    fleet.service.command("stop")
    fleet.service.dispatch(fleet.service.commands.get_nowait())


def test_chat_log_routes_progress_and_activity_by_identity_and_stop_to_all(fleet):
    f = fleet
    f.service.dispatch("auto_catch")
    group = f.service.auto_catch
    keys = [chat_queue_key(w.config) for w in group.workflows]
    assert set(key for key, _ in f.chat_logs) == set(keys)  # Startup progress for every chat.
    f.chat_logs.clear()
    for index, workflow in enumerate(group.workflows):
        workflow.progress(f"capture-{index}")
        workflow.processor.activity(f"processing-{index}")
    assert f.chat_logs == [
        (key, message)
        for index, key in enumerate(keys)
        for message in (f"capture-{index}", f"processing-{index}")
    ]
    assert any("Chat 2: Room 2 — processing-1" in line for line in f.logs)
    f.chat_logs.clear()
    f.service.transition(State.PAUSED, "Chat 2 unavailable; all chats paused")
    assert {key for key, text in f.chat_logs if text.startswith("PAUSED")} == set(keys)
    f.chat_logs.clear()
    stop(f)
    assert {key for key, text in f.chat_logs if text.startswith("STOPPED")} == set(keys)


def test_single_chat_logs_progress_and_processor_activity(fleet):
    f = fleet
    f.config.agent_chats = []
    key = chat_queue_key(f.config)
    f.service.general_auto_catch.progress("Single capture")
    f.service.general_auto_catch.processor_factory().activity("Single API request")
    assert f.chat_logs == [(key, "Single capture"), (key, "Single API request")]
    assert "Single API request" in f.logs


def test_three_chats_keep_pipeline_and_replies_isolated(fleet):
    f = fleet
    f.service.dispatch("auto_catch")
    group = f.service.auto_catch
    assert f.captures == [1, 2, 3]
    assert len({w.chat_key for w in group.workflows}) == 3
    assert all(w.jobs is group.base_workflow.jobs for w in group.workflows)
    f.service.poll_auto_catch()
    complete_round(f)
    assert f.sends == [
        (1, "Response for Person30"),
        (2, "Response for Person60"),
        (3, "Response for Person90"),
    ]
    assert sorted(chat for chat, _ in f.operations) == [1, 2, 3]
    assert group.reply_count == 3
    assert len(set(f.names)) == 3
    # A change in one chat must compare with that chat's last frame only.
    group.workflows[1].desktop.frame[:] = 150
    f.service.poll_auto_catch()
    f.now[0] += 1.5
    f.service.poll_auto_catch()
    complete_round(f)
    assert f.comparisons == [[60, 150]]
    assert f.sends[-1] == (2, "Response for Person150")
    assert len(f.sends) == 4


def test_identical_requests_in_three_groups_have_separate_images_and_replies(fleet):
    f = fleet
    create = f.service.create_multi_chat

    def same_request(mode):
        group = create(mode)
        for workflow in group.workflows:
            workflow.desktop.frame[:] = 30
        return group

    f.service.create_multi_chat = same_request
    f.service.dispatch("auto_catch")
    admit_screens(f)
    group = f.service.auto_catch
    with f.queue.connect() as db:
        rows = db.execute("SELECT * FROM image_reply_queue ORDER BY id").fetchall()
    paths = [group.workflows[0].jobs.paths(row["text"])[1] for row in rows]
    assert len(set(paths)) == 3 and len({p.name for p in paths}) == 1
    assert all(
        path.parent.name.startswith(f"Room {index}--") for index, path in enumerate(paths, 1)
    )
    assert len({row["chat_key"] for row in rows}) == 3
    f.service.poll_auto_catch()
    complete_round(f)
    assert f.sends == [(i, "Response for Person30") for i in (1, 2, 3)]
    stop(f)
    f.service.dispatch("auto_catch")
    f.service.poll_auto_catch()
    complete_round(f)
    assert len(f.sends) == 6 and len(f.operations) == 6


def test_wrong_chat_job_is_rejected_before_analysis_or_sending(fleet):
    f = fleet
    f.service.dispatch("auto_catch")
    admit_screens(f)
    first, second, _ = f.service.auto_catch.workflows
    with f.queue.connect() as db:
        job = dict(
            db.execute(
                "SELECT * FROM image_reply_queue WHERE chat_key=?", (first.chat_key,)
            ).fetchone()
        )
    with pytest.raises(AgentError, match="another chat"):
        second.begin_job(job)
    assert second.worker is None and second.job is None
    assert not f.sends and not f.operations


def test_slow_first_chat_does_not_block_other_chats(fleet):
    f = fleet
    entered, release = threading.Event(), threading.Event()
    f.gates[1] = (entered, release)
    try:
        f.service.dispatch("auto_catch")
        f.service.poll_auto_catch()
        assert entered.wait(2)
        group = f.service.auto_catch
        for workflow in group.workflows[1:]:
            workflow.worker.join(2)
            assert not workflow.worker.is_alive()
        f.service.poll_auto_catch()
        assert f.sends == [(2, "Response for Person60"), (3, "Response for Person90")]
        assert group.workflows[0].worker.is_alive()
        group.workflows[2].desktop.frame[:] = 180
        f.service.poll_auto_catch()
        f.now[0] += 1.5
        f.service.poll_auto_catch()
        assert group.workflows[2].jobs.count(group.workflows[2].chat_key) == 1
        release.set()
        complete_round(f)
        assert (1, "Response for Person30") in f.sends
        assert (3, "Response for Person180") in f.sends
    finally:
        release.set()


def test_two_windows_queue_bursts_and_restart_discards_remaining_work(fleet):
    f = fleet
    f.config.select_agent_chats(targets(2))
    entered, release = threading.Event(), threading.Event()
    f.gates[1] = (entered, release)
    first_power = "가상인 / 경기 광명시 가상로 238 / 전원연결"
    second_move = "위치조정/가상림/가상로 15"
    frames = {
        110: ["[자동 확인]\n" + second_move, first_power, first_power],
        120: [second_move, second_move],
        160: [second_move],
        170: [first_power],
    }

    def classify(before, after, cancel, *, batch):
        assert batch == "bubbles"
        marker = cv2.imdecode(np.frombuffer(after, np.uint8), cv2.IMREAD_COLOR)[0, 0, 0]
        return parse_incoming(json.dumps({
            "kind": "incoming", "sender": "", "is_ai": False,
            "text": [{"text": text} for text in frames[marker]],
        }), batch=True)

    def poll():
        f.now[0] += 2
        f.service.poll_auto_catch()

    try:
        f.service.dispatch("auto_catch")
        first, second = f.service.auto_catch.workflows
        for workflow in (first, second):
            workflow.llm.classify = classify
        poll()
        assert entered.wait(2)
        second.worker.join(2)
        for pair in [(110, 120), (160, 170)]:
            first.desktop.frame[:] = pair[0]
            second.desktop.frame[:] = pair[1]
            poll()
        assert first.jobs.count(first.chat_key) == 3
        for _ in range(6):
            if second.worker:
                second.worker.join(2)
            poll()
        assert [r["message"] for chat, r in f.operations if chat == 2] == [
            "위치조정/Person60/Road60", second_move, second_move, first_power,
        ]
        assert all(chat == 2 for chat, _ in f.sends)
        release.set()
        first.worker.join(2)
        poll()  # Deliver the first chat's startup result.
        poll()  # Claim its first changed capture.
        first.worker.join(2)
        poll()  # First power request sent; its sibling and the later capture are still pending.
        assert first.jobs.count(first.chat_key) == 2
        stop(f)
        f.service.dispatch("auto_catch")
        first, second = f.service.auto_catch.workflows
        first.llm.classify = classify
        for _ in range(8):
            poll()
            complete_round(f)
        assert [r["message"] for chat, r in f.operations if chat == 1] == [
            "위치조정/Person30/Road30", first_power, "위치조정/Person30/Road30",
        ]
        assert [text for chat, text in f.sends if chat == 1] == [
            "Response for Person30", "Response for 가상인", "Response for Person30",
        ]
        assert [text for chat, text in f.sends if chat == 2] == [
            "Response for Person60", "Response for 가상림", "Response for 가상림", "Response for 가상인",
            "Response for Person60",
        ]
        for workflow in (first, second):
            assert workflow.jobs.count(workflow.chat_key) == 0
            assert workflow.jobs.review_count(workflow.chat_key) == 0
    finally:
        release.set()


def test_stop_cancels_every_chat_and_each_explicit_restart_runs_current_snapshot(fleet):
    f = fleet
    f.service.dispatch("auto_catch")
    admit_screens(f)
    keys = [w.chat_key for w in f.service.auto_catch.workflows]
    stop(f)  # Startup jobs were durably captured but not processed.
    assert not f.sends and not f.operations
    f.service.dispatch("auto_catch")
    assert [w.chat_key for w in f.service.auto_catch.workflows] == keys
    f.service.poll_auto_catch()
    complete_round(f)
    assert len(f.sends) == 3
    stop(f)
    f.service.dispatch("auto_catch")
    f.service.poll_auto_catch()
    complete_round(f)
    assert len(f.sends) == 6 and len(f.operations) == 6


def test_stop_during_inference_cancels_all_workers(fleet):
    f = fleet
    for chat in (1, 2, 3):
        f.gates[chat] = (threading.Event(), threading.Event())
    f.service.dispatch("auto_catch")
    f.service.poll_auto_catch()
    group = f.service.auto_catch
    for entered, _ in f.gates.values():
        assert entered.wait(2)
    workers = [w.worker for w in group.workflows]
    stop(f)
    for worker in workers:
        worker.join(2)
        assert not worker.is_alive()
    assert not f.sends and not f.operations and not group.active
    assert all(w.jobs.count(w.chat_key) == 1 for w in group.workflows)


def test_invalid_second_chat_pauses_all_without_misrouting(fleet):
    f = fleet
    f.service.dispatch("auto_catch")
    admit_screens(f)
    f.environment.invalid.add(2)
    with pytest.raises(AgentError, match="Chat 2.*all chats paused") as error:
        f.service.poll_auto_catch()
    f.service.pause(error.value)
    assert f.service.state == State.PAUSED
    assert f.service.stop_input.is_set() and not f.service.auto_focus_recovery
    assert not f.service.auto_catch.active
    assert not f.sends
    assert all(w.jobs.count(w.chat_key) == 1 for w in f.service.auto_catch.workflows)


def test_preflight_failure_does_not_arm_any_chat(fleet):
    f = fleet
    f.environment.invalid.add(3)
    with pytest.raises(AgentError, match="Target closed"):
        f.service.dispatch("auto_catch")
    assert not f.captures and not f.sends and not f.operations
    assert f.service.stop_input.is_set()


def test_stop_between_chats_prevents_next_capture(fleet):
    f = fleet
    f.service.dispatch("auto_catch")
    group = f.service.auto_catch
    first = group.workflows[0]
    capture_changes = first.capture_changes

    def stop_after_capture():
        capture_changes()
        f.service.command("stop")

    first.capture_changes = stop_after_capture
    f.captures.clear()
    with pytest.raises(Cancelled):
        f.service.poll_auto_catch()
    assert f.captures == [1] and not f.sends


def test_review_scopes_follow_selection_and_workflow_switch(fleet):
    f = fleet
    f.service.dispatch("auto_catch")
    group = f.service.auto_catch
    scopes = f.service.review_scopes()
    assert [key for _, key in scopes] == [w.chat_key for w in group.workflows]
    stop(f)
    # Switching back to a single chat keeps the original single-chat implementation.
    f.config.agent_chats = []
    base = f.service.general_auto_catch
    base.arm = lambda: None
    f.service.dispatch("auto_catch")
    assert f.service.auto_catch is base
    assert len(f.service.review_scopes()) == 1


def test_switch_between_continuous_workflows_keeps_chat_keys_separate(fleet):
    from app.automation.device_workflow import DeviceWorkflow
    from app.automation.unified_workflow import UnifiedWorkflow

    f = fleet
    f.service.dispatch("auto_catch")
    unified_keys = [w.chat_key for w in f.service.auto_catch.workflows]
    stop(f)
    f.service.dispatch("device_workflow")
    group = f.service.auto_catch
    assert group.mode == "device_workflow"
    assert all(isinstance(w, DeviceWorkflow) for w in group.workflows)
    assert f.sends == [(i, DeviceWorkflow.greeting) for i in (1, 2, 3)]
    assert not set(unified_keys).intersection(w.chat_key for w in group.workflows)
    stop(f)
    f.service.dispatch("auto_catch")
    assert all(isinstance(w, UnifiedWorkflow) for w in f.service.auto_catch.workflows)
    assert [w.chat_key for w in f.service.auto_catch.workflows] == unified_keys


def test_gui_selects_persists_and_returns_to_single_chat(fleet, tmp_path, monkeypatch, qt_app):
    from PySide6.QtCore import QAbstractNativeEventFilter, Qt

    from app.gui import main_window
    from app.gui.agent_chats_dialog import AgentChatsDialog

    class Hotkey(QAbstractNativeEventFilter):
        registered = True

        def nativeEventFilter(self, *_):
            return False, 0

        def close(self):
            pass

    monkeypatch.setattr(main_window, "EmergencyHotkey", lambda _: Hotkey())
    f = fleet
    f.config.agent_chats = []
    f.service.desktop.foreground_chat_target = lambda: targets()[1]
    f.service.desktop.candidates = targets
    signals = main_window.Signals()
    window = main_window.MainWindow(
        f.config,
        tmp_path / "config.json",
        f.service.desktop,
        f.service,
        SimpleNamespace(is_alive=lambda: False),
        f.queue,
        signals,
    )

    def choose(dialog):
        for index in range(3):
            dialog.windows.item(index).setCheckState(Qt.Checked)
        return main_window.QDialog.Accepted

    monkeypatch.setattr(AgentChatsDialog, "exec", choose)
    try:
        window.select_agent_chats()
        assert len(load(window.config_path).agent_chats) == 3
        assert window.activity_views.count() == 4
        key = chat_queue_key(f.config.agent_configs()[1])
        signals.chat_activity.emit(key, "Live second-chat event")
        qt_app.processEvents()
        assert "Live second-chat event" in window.activity_views.chat_logs[key].toPlainText()
        assert "3. Room 3" in window.target_label.text()
        second_id = f.config.agent_chats[1].chat_id
        f.service.state = State.AUTO_CATCHING
        window.update_status(State.AUTO_CATCHING.value, "Watching 3 chats")
        assert all(not button.isEnabled() for button in window.setup_buttons)
        assert window.stop_button.isEnabled()
        window.select_agent_chats()  # No configuration changes while running.
        assert len(f.config.agent_chats) == 3
        f.service.state = State.STOPPED
        window.update_status(State.STOPPED.value, "")
        def pick_single(dialog):
            dialog.finish_pick()
            assert dialog.selected_targets() == [targets()[1]]
            return main_window.QDialog.Accepted

        monkeypatch.setattr(AgentChatsDialog, "exec", pick_single)
        window.select_window()
        assert f.config.target == targets()[1]
        assert f.config.chat_id == second_id and f.config.agent_chats == []
        assert load(window.config_path).agent_chats == []
        assert window.activity_views.count() == 2
        assert "Live second-chat event" in window.activity_views.chat_logs[key].toPlainText()
    finally:
        window.closing = True
        window.close()
        window.deleteLater()


def test_agent_chats_dialog_limits_selection(qt_app):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QDialogButtonBox

    from app.gui.agent_chats_dialog import AgentChatsDialog

    dialog = AgentChatsDialog(targets(4), [])
    button = dialog.buttons.button(QDialogButtonBox.Ok)
    assert not button.isEnabled()
    for index in range(3):
        dialog.windows.item(index).setCheckState(Qt.Checked)
    assert button.isEnabled() and dialog.selected_targets() == targets()
    dialog.windows.item(3).setCheckState(Qt.Checked)
    assert not button.isEnabled()
    dialog.accept()
    assert dialog.result() != QDialog.Accepted
    dialog.windows.item(3).setCheckState(Qt.Unchecked)
    dialog.accept()
    assert dialog.result() == QDialog.Accepted
    dialog.deleteLater()
