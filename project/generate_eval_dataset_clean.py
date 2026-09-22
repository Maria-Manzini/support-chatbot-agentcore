import argparse
import json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", default="flow_tests_template.json")
    parser.add_argument("--output", default="eval-dataset-clean.jsonl")
    args = parser.parse_args()

    with open(args.template, "r", encoding="utf-8") as f:
        template = json.load(f)

    tests = template["tests"]

    with open(args.output, "w", encoding="utf-8") as out:
        for test in tests:
            record = {
                "prompt": test["prompt"],
                "referenceResponse": test["expected"],
            }
            out.write(json.dumps(record) + "\n")

    print(f"Wrote {len(tests)} eval records to {args.output}")


if __name__ == "__main__":
    main()