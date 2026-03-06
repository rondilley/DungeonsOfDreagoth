"""Entry point for `python -m dreagoth`."""

from dreagoth.app import DreagothApp


def main() -> None:
    app = DreagothApp()
    app.run()


if __name__ == "__main__":
    main()
