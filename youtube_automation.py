from rich.console import Console
from rich.prompt import Prompt, IntPrompt
from rich.panel import Panel
from rich.table import Table

console = Console()

console.print(Panel.fit("🚀 User Information", style="bold blue"))

name = Prompt.ask("Name")
age = IntPrompt.ask("Age")
language = Prompt.ask(
    "Favorite language",
    choices=["Python", "Rust", "Go"],
    default="Python"
)

table = Table(title="Summary")
table.add_column("Field", style="cyan")
table.add_column("Value", style="green")

table.add_row("Name", name)
table.add_row("Age", str(age))
table.add_row("Language", language)

console.print(table)
