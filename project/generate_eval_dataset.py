import argparse
import json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", default="flow-tests-template.json")
    parser.add_argument("--output", default="eval-dataset.jsonl")
    args = parser.parse_args()

    with open(args.template, "r", encoding="utf-8") as f:
        template = json.load(f)

    flow_input_node = template["flowInputNode"]["nodeName"]
    tests = template["tests"]

    with open(args.output, "w", encoding="utf-8") as out:
        for test in tests:
            record = {
                "prompt": test["prompt"],
                "referenceResponse": test["expected"],
                "flowInputNode": flow_input_node,
                "testId": test["id"],
            }
            out.write(json.dumps(record) + "\n")

    print(f"Wrote {len(tests)} eval records to {args.output}")


if __name__ == "__main__":
    main()