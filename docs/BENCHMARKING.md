# LBH V2 Benchmarking

LBH V2 is designed to be faster than V1 by reducing unnecessary screenshot, LLM, and action overhead.

## Why V2 should be faster

- Screenshots are resized by default.
- Coordinates are converted explicitly instead of relying on ad hoc click helpers.
- Dynamic batches reduce full observe/evaluate cycles between deterministic primitives.
- `wait-stable` avoids asking the model whether a page has stopped moving.
- Failure guards and skill candidates reduce repeated bad retries.

## Benchmark command

```powershell
python -m lbh.cli benchmark --task <task-id>
python -m lbh.cli benchmark --task <task-id> --action-json examples\click_resized_point.json
python -m lbh.cli benchmark --task <task-id> --batch-json examples\navigate_chatgpt_batch.json --stable-seconds 3 --timeout 60
```

## Reported metrics

- screenshot width and height
- screenshot byte size
- coordinate transform overhead
- primitive action timing when supplied
- batch timing when supplied
- `wait-stable` timing when requested
