"""CLI tool for Korean translation middleware."""

import asyncio
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.theme import Theme

from ko_translate import (
    TranslationConfig,
    create_engine,
    get_logger,
    contains_korean,
)

custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
})

console = Console(theme=custom_theme)
app = typer.Typer(help="Korean Translation Middleware CLI")


@app.command()
def translate(
    text: str = typer.Argument(..., help="Text to translate"),
    direction: str = typer.Option(
        "auto",
        "--direction",
        "-d",
        help="Translation direction: auto, ko-en, en-ko",
    ),
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config file",
    ),
    stream: bool = typer.Option(False, "--stream", "-s", help="Enable streaming output"),
) -> None:
    if config_path:
        config = TranslationConfig.from_file(config_path)
    else:
        config = TranslationConfig.load_default()

    engine, logger = create_engine(config)

    async def do_translate():
        if direction == "auto":
            if contains_korean(text):
                direction = "ko-en"
            else:
                direction = "en-ko"

        console.print(f"[info]Direction: {direction}[/info]")

        if direction == "ko-en":
            result = await engine.ko_to_en(text)
        else:
            result = await engine.en_to_ko(text)

        if stream:
            console.print(result)
        else:
            console.print(Panel(
                result,
                title="Translation Result",
                border_style="green",
            ))

    asyncio.run(do_translate())


@app.command()
def proxy(
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config file",
    ),
    host: str = typer.Option("127.0.0.1", "--host", help="Proxy host"),
    port: int = typer.Option(8080, "--port", "-p", help="Proxy port"),
) -> None:
    from ko_translate.server import run_server
    from ko_translate import TranslationEngine

    if config_path:
        config = TranslationConfig.from_file(config_path)
    else:
        config = TranslationConfig.load_default()

    config.proxy_host = host
    config.proxy_port = port

    engine, logger = create_engine(config)

    console.print(f"[info]Starting proxy server on {host}:{port}[/info]")
    run_server(config, engine)


@app.command()
def detect(
    text: str = typer.Argument(..., help="Text to analyze"),
) -> None:
    from ko_translate import detect_korean_ratio

    ratio = detect_korean_ratio(text)
    has_korean = contains_korean(text)

    console.print(f"[info]Korean ratio: {ratio:.2%}[/info]")
    console.print(f"[info]Contains Korean: {has_korean}[/info]")


@app.command()
def config_show(
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config file",
    ),
) -> None:
    if config_path:
        config = TranslationConfig.from_file(config_path)
    else:
        config = TranslationConfig.load_default()

    config_dict = config.to_dict()

    for key, value in config_dict.items():
        console.print(f"[info]{key}[/info]: {value}")


def main():
    app()


if __name__ == "__main__":
    main()