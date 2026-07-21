"""Fail-closed production configuration check used by launchers and CI."""

from makepdf.web.operations import configuration_errors


def main() -> int:
    errors = configuration_errors(require_worker=False)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 78
    print("MakePDF configuration and service database are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
