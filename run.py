import typer
from rich.console import Console
from extractor import process_book_pdf
from generator import assemble_paper

app = typer.Typer(help="Automated JEE Advanced Physics Question Engine")
console = Console()

@app.command()
def ingest(
    pdf_path: str = typer.Option(..., "--pdf", "-p", help="Path to book PDF file"),
    book: str = typer.Option(..., "--book", "-b", help="Book identifier (e.g. Irodov, HCV)"),
    start: int = typer.Option(1, "--start", "-s", help="Start page number"),
    end: int = typer.Option(5, "--end", "-e", help="End page number")
):
    """Extract, parse, and store questions from a physics PDF into the central database."""
    console.print(f"[bold cyan]Starting ingestion for {book}...[/bold cyan]")
    process_book_pdf(pdf_path, book, start, end)

@app.command()
def generate(
    topic: str = typer.Option(..., "--topic", "-t", help="Physics topic (e.g., Mechanics, Optics, Electrodynamics)"),
    single: int = typer.Option(4, "--single", help="Count of Single Choice questions"),
    multi: int = typer.Option(6, "--multi", help="Count of Multi Choice questions"),
    numeric: int = typer.Option(6, "--numeric", help="Count of Numerical questions")
):
    """Synthesize a complete JEE Advanced pattern test paper."""
    console.print(f"[bold green]Generating JEE Advanced paper for: {topic}...[/bold green]")
    assemble_paper([topic], num_single=single, num_multi=multi, num_numeric=numeric)

if __name__ == "__main__":
    app()