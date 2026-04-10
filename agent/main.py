import argparse

from .orchestrator import OrchestratorAgent


def main() -> int:
    parser = argparse.ArgumentParser(description="Dev Ops Agent.")
    parser.add_argument("prompt", help="Natural-language prompt.")
    args = parser.parse_args()

    print(OrchestratorAgent().run(args.prompt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
