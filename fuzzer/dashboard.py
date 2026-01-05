from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.console import Console
from rich import box
import time
import queue
from datetime import datetime

class FuzzerDashboard:
    def __init__(self, num_workers, stats_dict, log_queue):
        """
        :param num_workers: 워커 수
        :param stats_dict: 공유 통계 딕셔너리 (Manager().dict())
            - 'execs', 'crashes', 'unique', 'edges', 'start_time'
        :param log_queue: 로그 메시지 큐 (multiprocessing.Queue)
        """
        self.num_workers = num_workers
        self.stats = stats_dict
        self.log_queue = log_queue
        self.console = Console()
        self.logs = []
        self.max_logs = 10
        self.layout = self.make_layout()
        
    def make_layout(self):
        layout = Layout()
        layout.split(
            Layout(name="header", size=3),
            Layout(name="stats", size=10),
            Layout(name="logs")
        )
        return layout

    def generate_header(self):
        elapsed = time.time() - self.stats.get('start_time', time.time())
        hours, rem = divmod(elapsed, 3600)
        minutes, seconds = divmod(rem, 60)
        time_str = "{:0>2}:{:0>2}:{:05.2f}".format(int(hours), int(minutes), seconds)
        
        return Panel(
            f"[bold cyan]🚀 Antigravity Firmware Fuzzer[/bold cyan]  [yellow]Time: {time_str}[/yellow]",
            style="white on blue"
        )

    def generate_stats_table(self):
        table = Table(box=box.SIMPLE_HEAD)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")

        execs = self.stats.get('execs', 0)
        crashes = self.stats.get('crashes', 0)
        unique = self.stats.get('unique', 0)
        edges = self.stats.get('edges', 0)
        
        elapsed = time.time() - self.stats.get('start_time', time.time())
        speed = execs / elapsed if elapsed > 0 else 0
        
        table.add_row("Total Execs", f"{execs:,}", "Cluster Speed", f"{speed:.2f} exec/s")
        table.add_row("Total Crashes", f"{crashes}", "Unique Crashes", f"{unique}")
        table.add_row("Total Edges", f"{edges}", "Workers", f"{self.num_workers}")
        
        return Panel(table, title="[bold]Statistics[/bold]", border_style="green")

    def generate_log_panel(self):
        # 큐에서 로그 가져오기
        while True:
            try:
                msg = self.log_queue.get_nowait()
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.logs.append(f"[{timestamp}] {msg}")
                if len(self.logs) > self.max_logs:
                    self.logs.pop(0)
            except queue.Empty:
                break
        
        log_content = "\n".join(self.logs)
        return Panel(log_content, title="[bold]Recent Logs[/bold]", border_style="yellow")

    def update(self):
        self.layout["header"].update(self.generate_header())
        self.layout["stats"].update(self.generate_stats_table())
        self.layout["logs"].update(self.generate_log_panel())
        return self.layout
