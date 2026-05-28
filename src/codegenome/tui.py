"""Textual TUI for CodeGenome."""

import asyncio
import os
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, RichLog
from textual.worker import Worker, get_current_worker

class CodeGenomeTUI(App):
    """A Textual app for managing CodeGenome."""
    
    CSS = """
    Screen {
        layout: vertical;
    }
    
    #workspace-container {
        height: auto;
        padding: 1 2;
        border: solid green;
        margin: 1;
    }
    
    #commands-container {
        height: auto;
        padding: 1 2;
        border: solid blue;
        margin: 1 1 0 1;
        layout: horizontal;
        align: center middle;
    }
    
    Button {
        margin: 0 1;
    }
    
    #log-container {
        height: 1fr;
        padding: 1 2;
        border: solid white;
        margin: 1;
    }
    
    RichLog {
        height: 1fr;
        width: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        """Create child widgets for the app.

        Returns:
            ComposeResult: An iterable of widgets to compose the UI.
        """
        yield Header()
        
        with Container(id="workspace-container"):
            yield Label("Workspace Root:")
            yield Input(value=".", id="workspace-input", placeholder="Enter path to workspace...")
            
        with Horizontal(id="commands-container"):
            yield Button("Analyze", id="btn-analyze", variant="primary")
            yield Button("Export", id="btn-export", variant="primary")
            yield Button("Generate AI Rules", id="btn-rules", variant="primary")
            yield Button("Start MCP", id="btn-mcp", variant="success")
            yield Button("Live Evolve", id="btn-evolve", variant="success")
            yield Button("Stop Active Processes", id="btn-stop", variant="error")
            
        with Container(id="log-container"):
            yield Label("Console Log:")
            yield RichLog(id="console-log", markup=True, highlight=True)
            
        yield Footer()

    def on_mount(self) -> None:
        """Called when app starts. Initializes widgets and state."""
        self.log_widget = self.query_one(RichLog)
        self.workspace_input = self.query_one("#workspace-input", Input)
        self.active_processes = []
        self.log_widget.write("[bold green]CodeGenome TUI Initialized.[/bold green]")
        self.log_widget.write("Enter a workspace path and click a command to begin.")

    def get_workspace_path(self) -> str:
        """Get the current workspace path from input.

        Returns:
            str: The workspace path entered by the user.
        """
        return self.workspace_input.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Event handler called when a button is pressed.

        Args:
            event (Button.Pressed): The button press event.
        """
        button_id = event.button.id
        workspace = self.get_workspace_path()
        
        if button_id == "btn-analyze":
            self.run_command(["codegenome", "analyze", workspace])
        elif button_id == "btn-export":
            self.run_command(["codegenome", "export", "--format", "json", "--path", workspace])
        elif button_id == "btn-rules":
            self.run_command(["codegenome", "rules", "--client", "all", workspace])
        elif button_id == "btn-mcp":
            self.run_command(["codegenome", "mcp-start", "--path", workspace], is_background=True)
        elif button_id == "btn-evolve":
            self.run_command(["codegenome", "evolve", "--live", workspace], is_background=True)
        elif button_id == "btn-stop":
            self.stop_all_processes()

    def run_command(self, cmd: list[str], is_background: bool = False) -> None:
        """Run a CLI command in a worker.

        Args:
            cmd (list[str]): The command list to execute.
            is_background (bool, optional): Whether to run the process in the background. Defaults to False.
        """
        command_str = " ".join(cmd)
        self.log_widget.write(f"\n[bold blue]> Running:[/bold blue] {command_str}")
        self.run_worker(self._execute_process(cmd, is_background), exclusive=False)

    async def _execute_process(self, cmd: list[str], is_background: bool) -> None:
        """Execute subprocess asynchronously.

        Args:
            cmd (list[str]): The command list to execute.
            is_background (bool): Whether the process should run in the background.
        """
        worker = get_current_worker()
        
        try:
            # We use sys.executable to ensure we run in the same python env
            if cmd[0] == "codegenome":
                cmd = [sys.executable, "-m", "codegenome.cli"] + cmd[1:]
                
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            
            if is_background:
                self.active_processes.append(process)
                self.log_widget.write(f"[italic]Started background process (PID: {process.pid})[/italic]")
            
            while True:
                if worker.is_cancelled:
                    process.terminate()
                    break
                    
                line = await process.stdout.readline()
                if not line:
                    break
                    
                text = line.decode().rstrip()
                # Run the log write directly since async workers run in the main asyncio loop
                self.log_widget.write(text)
                
            await process.wait()
            
            if is_background and process in self.active_processes:
                self.active_processes.remove(process)
                
            status_color = "green" if process.returncode == 0 else "red"
            self.log_widget.write(f"[[bold {status_color}]Process exited with code {process.returncode}[/bold {status_color}]]")
            
        except Exception as e:
            self.log_widget.write(f"[bold red]Error:[/bold red] {e}")

    def stop_all_processes(self) -> None:
        """Stop all active background processes."""
        if not self.active_processes:
            self.log_widget.write("[yellow]No active background processes to stop.[/yellow]")
            return
            
        for p in self.active_processes:
            try:
                p.terminate()
                self.log_widget.write(f"[yellow]Terminated process (PID: {p.pid})[/yellow]")
            except Exception as e:
                self.log_widget.write(f"[red]Failed to terminate PID {p.pid}: {e}[/red]")
        self.active_processes.clear()

def main():
    """Entry point for the CodeGenome TUI."""
    app = CodeGenomeTUI()
    app.run()

if __name__ == "__main__":
    main()
