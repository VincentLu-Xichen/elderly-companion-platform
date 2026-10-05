#!/usr/bin/env python3
"""Tkinter control panel for ESDS Raspberry Pi services."""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

SERVICES = {
    "agent": "elderly-agent.service",
    "gateway": "esds-voice.service",
    "audio": "esds-pi-audio.service",
}
ENV_PATH = Path.home() / ".config" / "elderly-agent" / "env"
VOICE_ENV_PATH = Path.home() / ".config" / "esds-voice" / "env"


class ControlPanel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ESDS Control Panel")
        self.root.geometry("820x650")
        self.root.minsize(720, 560)
        self.busy = False
        self.refresh_job = None
        self.status_vars = {key: tk.StringVar(value="Checking") for key in SERVICES}
        self.enabled_vars = {key: tk.StringVar(value="Checking") for key in SERVICES}
        self.health_var = tk.StringVar(value="Checking")
        self.bridge_var = tk.StringVar(value="Checking")
        self.mode_var = tk.StringVar(value="Checking")
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Sans", 18, "bold"))
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="ESDS Control Panel", style="Title.TLabel").pack(anchor="w")

        services = ttk.LabelFrame(outer, text="Services", padding=10)
        services.pack(fill="x")
        service_labels = (("agent", "Agent service"), ("gateway", "Voice gateway"), ("audio", "Raspberry Pi audio"))
        for row, (key, label) in enumerate(service_labels):
            ttk.Label(services, text=label, width=20).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Label(services, textvariable=self.status_vars[key], width=14).grid(row=row, column=1, sticky="w")
            ttk.Button(services, text="Start", command=lambda k=key: self.run_service(k, "start")).grid(row=row, column=2, padx=3)
            ttk.Button(services, text="Stop", command=lambda k=key: self.run_service(k, "stop")).grid(row=row, column=3, padx=3)
            ttk.Button(services, text="Restart", command=lambda k=key: self.run_service(k, "restart")).grid(row=row, column=4, padx=3)
            ttk.Label(services, text="Boot:").grid(row=row, column=5, sticky="e", padx=(18, 4))
            ttk.Label(services, textvariable=self.enabled_vars[key]).grid(row=row, column=6, sticky="w")

        actions = ttk.LabelFrame(outer, text="Quick actions", padding=10)
        actions.pack(fill="x", pady=12)
        ttk.Button(actions, text="Start all services", command=self.start_all).grid(row=0, column=0, padx=3, pady=3)
        ttk.Button(actions, text="Stop all services", command=self.stop_all).grid(row=0, column=1, padx=3, pady=3)
        ttk.Button(actions, text="Stop Daily Chat", command=self.stop_daily_chat).grid(row=0, column=2, padx=3, pady=3)
        ttk.Button(actions, text="Refresh status", command=self.refresh_now).grid(row=0, column=3, padx=3, pady=3)
        ttk.Button(actions, text="Daily Chat mode", command=lambda: self.set_mode("agent_bridge")).grid(row=1, column=0, padx=3, pady=3)
        ttk.Button(actions, text="CBT mode", command=lambda: self.set_mode("cbt_agent_bridge")).grid(row=1, column=1, padx=3, pady=3)
        ttk.Label(actions, text="Current mode:").grid(row=1, column=2, sticky="e", padx=(18, 3))
        ttk.Label(actions, textvariable=self.mode_var).grid(row=1, column=3, sticky="w")

        settings = ttk.LabelFrame(outer, text="Configuration", padding=10)
        settings.pack(fill="x")
        self.agent_boot_var = tk.BooleanVar(value=False)
        self._toggle(settings, "Agent at boot", self.agent_boot_var, lambda value: self.set_single_boot("agent", value), 0)
        self.daily_boot_var = tk.BooleanVar(value=False)
        self._toggle(settings, "Daily Chat at boot", self.daily_boot_var, self.set_daily_boot, 1)
        self.bridge_setting_var = tk.BooleanVar(value=False)
        self._toggle(settings, "Voice Bridge Enable", self.bridge_setting_var, self.set_bridge, 2)

        logs = ttk.LabelFrame(outer, text="Recent logs", padding=8)
        logs.pack(fill="both", expand=True)
        self.log_text = tk.Text(logs, height=12, wrap="none", state="disabled", font=("Monospace", 9))
        scrollbar = ttk.Scrollbar(logs, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    @staticmethod
    def _toggle(parent, label: str, variable: tk.BooleanVar, command, column: int) -> None:
        tk.Checkbutton(
            parent,
            text=label,
            variable=variable,
            command=lambda: command(variable.get()),
        ).grid(row=0, column=column, sticky="w", padx=8)

    def command(self, args: list[str]) -> tuple[int, str]:
        completed = subprocess.run(args, check=False, capture_output=True, text=True, timeout=20, env=os.environ.copy())
        return completed.returncode, (completed.stdout + completed.stderr).strip()

    def service_state(self, service: str, action: str) -> str:
        code, output = self.command(["systemctl", "--user", action, service])
        if action == "is-active":
            return "Running" if code == 0 and output == "active" else "Stopped"
        return "Enabled" if code == 0 and output == "enabled" else "Disabled"

    def refresh(self) -> None:
        def work() -> None:
            states = {key: self.service_state(service, "is-active") for key, service in SERVICES.items()}
            enabled = {key: self.service_state(service, "is-enabled") for key, service in SERVICES.items()}
            health = self.http_health()
            bridge = self.read_bridge()
            mode = self.read_mode()
            logs = self.read_logs()
            self.root.after(0, lambda: self.apply_status(states, enabled, health, bridge, mode, logs))

        threading.Thread(target=work, daemon=True).start()
        if self.refresh_job is None:
            self.refresh_job = self.root.after(5000, self.scheduled_refresh)

    def scheduled_refresh(self) -> None:
        self.refresh_job = None
        self.refresh()

    def apply_status(self, states, enabled, health: str, bridge: str, mode: str, logs: str) -> None:
        for key in SERVICES:
            self.status_vars[key].set(states[key])
            self.enabled_vars[key].set(enabled[key])
        self.agent_boot_var.set(enabled["agent"] == "Enabled")
        self.daily_boot_var.set(
            enabled["gateway"] == "Enabled" and enabled["audio"] == "Enabled"
        )
        self.health_var.set(health)
        self.bridge_var.set(bridge)
        self.mode_var.set(mode)
        self.bridge_setting_var.set(bridge == "Enabled")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", logs)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def http_health(self) -> str:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=2) as response:
                return "Healthy" if response.status == 200 else f"HTTP {response.status}"
        except (urllib.error.URLError, TimeoutError):
            return "Unavailable"

    def read_bridge(self) -> str:
        try:
            values = {}
            for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    values[key] = value.strip()
            return "Enabled" if values.get("VOICE_BRIDGE_ENABLED", "").lower() == "true" else "Disabled"
        except OSError:
            return "Config missing"

    def read_mode(self) -> str:
        try:
            values = {}
            for line in VOICE_ENV_PATH.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    values[key] = value.strip()
            provider = values.get("ESDS_CHAT_PROVIDER", "")
            if provider == "agent_bridge":
                return "Daily Chat"
            if provider == "cbt_agent_bridge":
                return f"CBT ({values.get('ESDS_CBT_LESSON_ID', 'lesson-1')})"
            return provider or "Unknown"
        except OSError:
            return "Config missing"

    def read_logs(self) -> str:
        chunks = []
        for label, service in SERVICES.items():
            _, output = self.command([
                "journalctl", "--user", "-u", service, "-n", "12",
                "--no-pager", "-o", "cat",
            ])
            if not output or "No journal files were found" in output:
                _, output = self.command(["systemctl", "--user", "status", service, "-l", "--no-pager"])
            output = self.clean_log_output(output)
            chunks.append(f"[{label}]\n{output or 'No status available'}")
        return "\n\n".join(chunks)

    @staticmethod
    def clean_log_output(output: str) -> str:
        prefix = re.compile(
            r"^[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\S+\s+.*?\[\d+\]:\s?"
        )
        return "\n".join(prefix.sub("", line) for line in output.splitlines())

    def run_async(self, title: str, operation) -> None:
        if self.busy:
            return
        self.busy = True

        def work() -> None:
            try:
                code, output = operation()
                self.root.after(0, lambda: self.finish_operation(title, code, output))
            except Exception as exc:
                self.root.after(0, lambda: self.finish_operation(title, 1, str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def finish_operation(self, title: str, code: int, output: str) -> None:
        self.busy = False
        if code != 0:
            messagebox.showerror(title, output or "Operation failed")
        self.refresh_now()

    def refresh_now(self) -> None:
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
            self.refresh_job = None
        self.root.after(50, self.refresh)

    def run_service(self, key: str, action: str) -> None:
        self.run_async(action, lambda: self.command(["systemctl", "--user", action, SERVICES[key]]))

    def wait_active(self, service: str, timeout: float = 10) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            code, output = self.command(["systemctl", "--user", "is-active", service])
            if code == 0 and output == "active":
                return True
            time.sleep(0.5)
        return False

    def start_all(self) -> None:
        def operation():
            for key in ("agent", "gateway", "audio"):
                code, output = self.command(["systemctl", "--user", "restart", SERVICES[key]])
                if code:
                    return code, output
                if not self.wait_active(SERVICES[key]):
                    return 1, f"{SERVICES[key]} did not become active"
            return 0, ""

        self.run_async("Start all services", operation)

    def stop_daily_chat(self) -> None:
        def operation():
            for key in ("audio", "gateway"):
                code, output = self.command(["systemctl", "--user", "stop", SERVICES[key]])
                if code:
                    return code, output
            return 0, ""

        self.run_async("Stop Daily Chat", operation)

    def set_mode(self, provider: str) -> None:
        lesson_id = "lesson-1"

        def operation():
            try:
                lines = VOICE_ENV_PATH.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                return 1, str(exc)
            updated = []
            found_provider = False
            found_lesson = False
            for line in lines:
                if line.startswith("ESDS_CHAT_PROVIDER="):
                    updated.append(f"ESDS_CHAT_PROVIDER={provider}")
                    found_provider = True
                elif line.startswith("ESDS_CBT_LESSON_ID="):
                    updated.append(f"ESDS_CBT_LESSON_ID={lesson_id}")
                    found_lesson = True
                else:
                    updated.append(line)
            if not found_provider:
                updated.append(f"ESDS_CHAT_PROVIDER={provider}")
            if not found_lesson:
                updated.append(f"ESDS_CBT_LESSON_ID={lesson_id}")
            temporary = VOICE_ENV_PATH.with_suffix(".tmp")
            temporary.write_text("\n".join(updated) + "\n", encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(VOICE_ENV_PATH)
            for key in ("agent", "gateway", "audio"):
                code, output = self.command(["systemctl", "--user", "restart", SERVICES[key]])
                if code:
                    return code, output
                if not self.wait_active(SERVICES[key]):
                    return 1, f"{SERVICES[key]} did not become active"
            return 0, ""

        self.run_async("Switch voice mode", operation)

    def stop_all(self) -> None:
        if not messagebox.askyesno("Confirm", "Stop Agent, voice gateway, and audio client?"):
            return

        def operation():
            for key in ("audio", "gateway", "agent"):
                code, output = self.command(["systemctl", "--user", "stop", SERVICES[key]])
                if code:
                    return code, output
            return 0, ""

        self.run_async("Stop all services", operation)

    def set_single_boot(self, key: str, enabled: bool) -> None:
        action = "enable" if enabled else "disable"
        self.run_async("Agent at boot", lambda: self.command(["systemctl", "--user", action, SERVICES[key]]))

    def set_daily_boot(self, enabled: bool) -> None:
        def operation():
            action = "enable" if enabled else "disable"
            for key in ("gateway", "audio"):
                code, output = self.command(["systemctl", "--user", action, SERVICES[key]])
                if code:
                    return code, output
            return 0, ""

        self.run_async("Daily Chat at boot", operation)

    def set_bridge(self, enabled: bool) -> None:
        if enabled and not messagebox.askyesno("Confirm voice bridge", "Confirm that the participant accepted the current data notice?"):
            self.bridge_setting_var.set(False)
            return

        def operation():
            try:
                lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                return 1, str(exc)
            replacement = f"VOICE_BRIDGE_ENABLED={'true' if enabled else 'false'}"
            updated = [replacement if line.startswith("VOICE_BRIDGE_ENABLED=") else line for line in lines]
            if not any(line.startswith("VOICE_BRIDGE_ENABLED=") for line in lines):
                updated.append(replacement)
            temporary = ENV_PATH.with_suffix(".tmp")
            temporary.write_text("\n".join(updated) + "\n", encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(ENV_PATH)
            for key in ("agent", "gateway", "audio"):
                code, output = self.command(["systemctl", "--user", "restart", SERVICES[key]])
                if code:
                    return code, output
                if not self.wait_active(SERVICES[key]):
                    return 1, f"{SERVICES[key]} did not become active"
            return 0, ""

        self.run_async("Voice bridge", operation)


def main() -> None:
    root = tk.Tk()
    ControlPanel(root)
    root.mainloop()


if __name__ == "__main__":
    main()
