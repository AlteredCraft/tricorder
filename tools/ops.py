# /// script
# requires-python = ">=3.12"
# dependencies = ["textual>=8.2,<9"]
# ///
"""Tricorder bench operations TUI. Run from the repo root: `uv run tools/ops.py`.

Tasks live in tools/ops_tasks.py (host-tested); this file only lays them out,
previews the exact command and streams its output.
"""
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Header, Input, Label, OptionList, RichLog, Select, Static

from tools import ops_tasks as ops


class OpsApp(App):
    TITLE = 'Tricorder ops'
    CSS = """
    #tasks { width: 30; border: round $primary; }
    #detail { padding: 0 1; }
    .row { height: auto; margin: 1 0 0 0; }
    .row Label { width: 16; padding: 1 0; }
    .row Input, .row Select { width: 1fr; }
    #buttons { height: auto; margin: 1 0; }
    #buttons Button { margin-right: 2; }
    #plan { border: round $secondary; padding: 0 1; height: auto; }
    #result { padding: 0 1; height: auto; }
    #log { height: 1fr; min-height: 8; border: round $panel; }
    """
    BINDINGS = [('r', 'run', 'Run'), ('d', 'detect', 'Detect'), ('q', 'quit', 'Quit')]

    def __init__(self, root=ROOT, *, ports=ops.serial_ports, ip_lookup=ops.mac_ipv4,
                 reachable=ops.tcp_reachable, plan=ops.provision_plan):
        super().__init__()
        self.root, self.ports, self.ip_lookup = Path(root), ports, ip_lookup
        self.reachable, self.plan_for = reachable, plan
        self.plan = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield OptionList(*[t.title for t in ops.TASKS], id='tasks')
            with Vertical(id='detail'):
                task = ops.TASKS[0]
                yield Static(f'[b]{task.title}[/b]\n{task.summary}')
                with VerticalScroll():
                    with Horizontal(classes='row'):
                        yield Label('Wi-Fi file')
                        yield Select([], id='env', prompt='Choose a .env.local.* file')
                    with Horizontal(classes='row'):
                        yield Label('Tab5 USB port')
                        yield Input(id='port', placeholder='not detected')
                    with Horizontal(classes='row'):
                        yield Label('Mac LAN IP')
                        yield Input(id='ip', placeholder='not detected')
                    yield Static(id='plan')
                    with Horizontal(id='buttons'):
                        yield Button('Run', id='run', variant='primary')
                        yield Button('Detect again', id='detect')
                    yield Static(id='result')
                yield RichLog(id='log', wrap=True, markup=True)
        yield Footer()

    def on_mount(self):
        self.query_one('#tasks', OptionList).highlighted = 0
        self.action_detect()

    def action_detect(self):
        files = ops.wifi_env_files(self.root)
        options = [(f'{f.path.name} — ' + (f.ssid if f.error is None else f'invalid: {f.error}'), str(f.path))
                   for f in files]
        select = self.query_one('#env', Select)
        select.set_options(options)
        valid = [str(f.path) for f in files if f.error is None]
        if len(valid) == 1:
            select.value = valid[0]
        self.query_one('#port', Input).value = ops.tab5_port(self.ports()) or ''
        self.query_one('#ip', Input).value = self.ip_lookup() or ''
        self.refresh_plan()

    def on_select_changed(self, _):
        self.refresh_plan()

    def on_input_changed(self, _):
        self.refresh_plan()

    def refresh_plan(self):
        env = self.query_one('#env', Select).value
        chosen = next((f for f in ops.wifi_env_files(self.root) if str(f.path) == env), None)
        self.plan = self.plan_for(self.root, env_file=Path(env) if chosen else None,
                                  port=self.query_one('#port', Input).value.strip() or None,
                                  mac_ip=self.query_one('#ip', Input).value.strip() or None)
        if chosen and chosen.error:
            self.plan.errors.insert(0, f'{chosen.path.name} is invalid: {chosen.error}')
            self.plan.argv = []
        text = ('[red]' + '\n'.join(self.plan.errors) + '[/red]' if self.plan.errors else
                f'Tab5 will join [b]{chosen.ssid}[/b] and use {self.plan.endpoint}\n'
                f'[dim]{" ".join(self.plan.argv)}[/dim]\n'
                'The Mac must be on the same network for the reachability check.')
        self.query_one('#plan', Static).update(text)
        self.query_one('#run', Button).disabled = bool(self.plan.errors)

    def on_button_pressed(self, event):
        if event.button.id == 'run':
            self.action_run()
        elif event.button.id == 'detect':
            self.action_detect()

    def action_run(self):
        if self.plan and not self.plan.errors:
            self.provision(self.plan, self.query_one('#ip', Input).value.strip())

    @work(exclusive=True)
    async def provision(self, plan, mac_ip):
        log, result, run = self.query_one('#log', RichLog), self.query_one('#result', Static), self.query_one('#run', Button)
        run.disabled = True
        result.update('Running… the Tab5 may reset; allow about a minute.')
        log.write(f'$ {" ".join(plan.argv)}')
        process = await asyncio.create_subprocess_exec(
            *plan.argv, cwd=self.root, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        lines = []
        async for raw in process.stdout:
            line = raw.decode(errors='replace').rstrip()
            lines.append(line)
            log.write(line)
        code = await process.wait()
        outcome = await asyncio.to_thread(ops.provision_result, lines, mac_ip=mac_ip, reachable=self.reachable)
        if code == 0 and not outcome.problems:
            result.update(f'[green]Done.[/green] Tab5 is at {outcome.tab5_ip}, reachable from this Mac. '
                          f'Evidence: {plan.output.relative_to(self.root)}')
        else:
            problems = outcome.problems or [f'provision_device exited with {code}']
            result.update('[red]' + '\n'.join(problems) + '[/red]')
        run.disabled = False


if __name__ == '__main__':
    OpsApp().run()
