import PyInstaller.__main__
from pathlib import Path

HERE = Path(__file__).parent.absolute()
path_to_main = str(HERE / "__main__.py")


def install():
    PyInstaller.__main__.run(
        [
            path_to_main,
            "--noconfirm",
            "--onedir",
            "--nowindowed",
            "--name",
            "arbbot",
            "--add-data",
            f"{HERE}/alert.mp3:.",
            "--add-data",
            f"{HERE}/../config.yaml:.",
        ]
    )
