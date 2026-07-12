import json
import errno
import subprocess
from pathlib import Path

import pytest

from alpha_workbench.code_agent import (
    CodexExecProvider,
    CodexExecutionError,
    CodexExecutionTimeoutError,
    CodexNotAvailableError,
    CodexOutputError,
)


class FakeRunner:
    def __init__(
        self,
        *,
        exec_returncode=0,
        output=None,
        timeout=False,
        timeout_after_files=False,
        generated_files=("manifest.json", "factor.py", "test_factor.py"),
    ):
        self.commands = []
        self.exec_returncode = exec_returncode
        self.output = output
        self.timeout = timeout
        self.timeout_after_files = timeout_after_files
        self.generated_files = generated_files

    def __call__(self, command, **kwargs):
        self.commands.append((command, kwargs))
        assert kwargs["shell"] is False

        if command[1:] == ["--version"]:
            return subprocess.CompletedProcess(command, 0, stdout="codex-cli 1.2.3\n", stderr="")

        if self.timeout and not self.timeout_after_files:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        if self.output is not None:
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(self.output, encoding="utf-8")

        job_dir = Path(command[command.index("-C") + 1])
        for name in self.generated_files:
            (job_dir / name).write_text(name, encoding="utf-8")

        if self.timeout:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        return subprocess.CompletedProcess(
            command,
            self.exec_returncode,
            stdout="",
            stderr="generation failed" if self.exec_returncode else "",
        )


def make_provider(runner, **kwargs):
    return CodexExecProvider(
        command_runner=runner,
        executable_finder=lambda name: f"/tools/{name}",
        **kwargs,
    )


def test_detects_codex_executable_and_version():
    runner = FakeRunner()

    provider = make_provider(runner)

    assert provider.executable == "/tools/codex"
    assert provider.version == "1.2.3"
    assert runner.commands[0][0] == ["/tools/codex", "--version"]


def test_shell_wrapper_without_shebang_uses_explicit_bash_launcher():
    class WrapperRunner(FakeRunner):
        def __call__(self, command, **kwargs):
            if command[0] == "/tools/codex":
                self.commands.append((command, kwargs))
                raise OSError(errno.ENOEXEC, "Exec format error")
            assert command[0].endswith("bash")
            return super().__call__(command[1:], **kwargs)

    runner = WrapperRunner()
    provider = make_provider(runner)

    assert provider.version == "1.2.3"
    assert runner.commands[0][0] == ["/tools/codex", "--version"]


def test_missing_codex_executable_is_reported():
    with pytest.raises(CodexNotAvailableError, match="not found"):
        CodexExecProvider(
            command_runner=FakeRunner(),
            executable_finder=lambda _name: None,
        )


def test_generate_builds_isolated_list_command_and_returns_result(tmp_path):
    runner = FakeRunner(output=json.dumps({"summary": "Implemented factor", "risks": ["PIT"]}))
    provider = make_provider(runner)

    result = provider.generate({"factor_id": "earnings_surprise"}, tmp_path)

    command, kwargs = runner.commands[1]
    assert isinstance(command, list)
    assert command[:2] == ["/tools/codex", "exec"]
    assert command[command.index("--sandbox") + 1] == "workspace-write"
    for flag in (
        "--ephemeral",
        "--skip-git-repo-check",
        "--ignore-user-config",
        "--ignore-rules",
        "--output-schema",
        "--output-last-message",
        "-C",
    ):
        assert flag in command
    assert kwargs["shell"] is False

    job_dir = Path(command[command.index("-C") + 1])
    assert job_dir.parent == tmp_path.resolve()
    assert result.job_dir == job_dir
    assert result.provider == "codex_exec"
    assert result.version == "1.2.3"
    assert result.files == ["manifest.json", "factor.py", "test_factor.py"]
    assert result.summary == "Implemented factor"
    assert result.risks == ["PIT"]
    assert result.is_mock is False

    prompt = command[-1]
    assert "exactly these three files" in prompt
    assert "manifest.json, factor.py, test_factor.py" in prompt
    assert "Do not access the network" in prompt
    assert "uqer" in prompt
    assert "credentials" in prompt
    assert "FactorContext" in prompt
    assert "factor_name (string)" in prompt
    assert "lookback_days (non-negative integer)" in prompt
    assert "field(name), trading_dates, and symbols" in prompt
    assert "event_field" not in prompt
    assert "event_window_return" not in prompt
    assert "point_in_time_fill" not in prompt


def test_repair_reuses_existing_job_and_includes_validation_error(tmp_path):
    runner = FakeRunner(output=json.dumps({"summary": "Repaired factor", "risks": []}))
    provider = make_provider(runner)
    generated = provider.generate("build a factor", tmp_path)
    job_dir = generated.job_dir

    result = provider.repair(
        {"factor_id": "earnings_surprise"},
        job_dir,
        "factor_name field required",
    )

    command = runner.commands[2][0]
    assert Path(command[command.index("-C") + 1]) == job_dir.resolve()
    assert "This is a repair turn" in command[-1]
    assert "factor_name field required" in command[-1]
    assert result.job_dir == job_dir.resolve()


def test_repair_rejects_unowned_directory(tmp_path):
    provider = make_provider(FakeRunner())
    unowned = tmp_path / "unowned"
    unowned.mkdir()

    with pytest.raises(CodexOutputError, match="not created by this provider"):
        provider.repair("build a factor", unowned, "validation failed")


def test_repair_does_not_accept_stale_last_message(tmp_path):
    runner = FakeRunner(output=json.dumps({"summary": "Initial factor", "risks": []}))
    provider = make_provider(runner)
    generated = provider.generate("build a factor", tmp_path)
    runner.output = None

    result = provider.repair("build a factor", generated.job_dir, "validation failed")

    assert result.job_dir == generated.job_dir
    assert "did not return a valid final JSON" in result.summary


def test_cleanup_removes_only_owned_job_directory(tmp_path):
    runner = FakeRunner(output=json.dumps({"summary": "Implemented factor", "risks": []}))
    provider = make_provider(runner)
    generated = provider.generate("build a factor", tmp_path)

    provider.cleanup(generated.job_dir)

    assert not generated.job_dir.exists()
    with pytest.raises(CodexOutputError, match="not created by this provider"):
        provider.cleanup(generated.job_dir)


def test_isolated_command_mounts_ephemeral_auth_and_process_namespace(tmp_path):
    provider = make_provider(FakeRunner())
    provider._isolate_generation = True
    provider._generation_mount = None
    job_dir = tmp_path / "job"
    auth_root = tmp_path / "auth"
    job_dir.mkdir()
    auth_root.mkdir()

    command = provider._isolated_command(["/usr/bin/codex", "exec"], job_dir, auth_root)

    assert "--share-net" in command
    assert "--proc" in command
    assert str(auth_root) in command
    assert "/mnt/auth-home" in command


def test_generate_reports_timeout_without_calling_real_codex(tmp_path):
    provider = make_provider(FakeRunner(timeout=True), timeout_seconds=0.5)

    with pytest.raises(CodexExecutionTimeoutError, match="timed out"):
        provider.generate("build a factor", tmp_path)
    assert not list(tmp_path.glob("codex-job-*"))


def test_generate_salvages_required_files_after_timeout(tmp_path):
    provider = make_provider(
        FakeRunner(timeout=True, timeout_after_files=True),
        timeout_seconds=0.5,
    )

    result = provider.generate("build a factor", tmp_path)

    assert result.files == ["manifest.json", "factor.py", "test_factor.py"]
    assert "did not return a final JSON" in result.summary
    assert result.job_dir.exists()


def test_generate_reports_nonzero_exit(tmp_path):
    provider = make_provider(FakeRunner(exec_returncode=2))

    with pytest.raises(CodexExecutionError, match="status 2"):
        provider.generate("build a factor", tmp_path)
    assert not list(tmp_path.glob("codex-job-*"))


def test_generate_rejects_missing_required_files(tmp_path):
    runner = FakeRunner(
        output=json.dumps({"summary": "Implemented factor", "risks": []}),
        generated_files=("manifest.json", "factor.py"),
    )
    provider = make_provider(runner)

    with pytest.raises(CodexOutputError, match="test_factor.py"):
        provider.generate("build a factor", tmp_path)


@pytest.mark.parametrize(
    "output",
    [
        "not-json",
        json.dumps({"summary": "missing risks"}),
        json.dumps({"summary": "", "risks": []}),
        json.dumps({"summary": "ok", "risks": [], "unexpected": True}),
    ],
)
def test_generate_rejects_invalid_output_json(tmp_path, output):
    provider = make_provider(FakeRunner(output=output))

    with pytest.raises(CodexOutputError, match="invalid final JSON"):
        provider.generate("build a factor", tmp_path)
