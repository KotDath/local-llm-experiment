import json
import time
from pathlib import Path
from common import append_jsonl, utc_now
from model import Model

QUESTIONS = [
    ('fact', 'Какая столица Франции? Ответь одним предложением по-русски.'),
    ('logic', 'Все вороны — птицы. Все птицы — животные. Следует ли, что все вороны — животные? Объясни кратко.'),
    ('constraints', 'A длится 3 ч. B длится 2 ч после A. C длится 4 ч после A. D длится 1 ч после B и C. Исполнителей достаточно. Когда раньше всего закончится D и каков критический путь?'),
]


def main():
    model = Model()
    run = utc_now()
    for identifier, question in QUESTIONS:
        start = time.monotonic()
        answer = model.complete([{'role': 'user', 'content': question}])
        record = {'run': run, 'id': identifier, 'question': question, 'utc': utc_now(),
                  'total_ms': (time.monotonic() - start) * 1000, **answer}
        append_jsonl(Path(__file__).parent / 'results/day26.jsonl', record)
        print(identifier, answer['text'], flush=True)


if __name__ == '__main__':
    main()
