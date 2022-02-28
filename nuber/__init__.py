from .reader import Reader
import click
import signal

__version__ = '0.1.0'

@click.command()
@click.argument("book", type=click.Path(exists=True))
def main(book):
    reader = Reader(click.format_filename(book))

    def signal_handler(*_):
        reader.action_quit(None)

    signal.signal(signal.SIGHUP, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    reader.loop() # type: ignore
