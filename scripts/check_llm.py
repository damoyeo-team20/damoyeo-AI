import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.llm import get_llm


def main() -> None:
    llm = get_llm()
    response = llm.invoke("한 문장으로 너 자신을 소개해줘.")
    print(response.text)


if __name__ == "__main__":
    main()
