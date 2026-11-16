import argparse
import json
from pathlib import Path
from .extraction import extract, inventory, local_models
from .analytics import Scenario, analyze
from .evaluation import evaluate

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description='Offline bill extraction and reviewed energy scenarios')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('models', help='List installed local Ollama models')
    p = commands.add_parser('inventory')
    p.add_argument('folder', type=Path)
    p.add_argument('--output', type=Path, default=Path('output/inventory.json'))
    p = commands.add_parser('extract')
    p.add_argument('pdf', type=Path)
    p.add_argument('--model', default='llama3.1:8b')
    p.add_argument('--engine', choices=['llm','rules','hybrid'], default='hybrid')
    p.add_argument('--vision-model')
    p.add_argument('--force-vision', action='store_true')
    p.add_argument('--ocr', action='store_true', help='Use local Tesseract for scanned pages')
    p.add_argument('--max-pages', type=int)
    p.add_argument('--output', type=Path, default=Path('output/extractions'))
    p = commands.add_parser('analyze')
    p.add_argument('scenario', type=Path)
    p.add_argument('--output', type=Path, default=Path('output/analysis.json'))
    p = commands.add_parser('evaluate')
    p.add_argument('extraction', type=Path)
    p.add_argument('labels', type=Path)
    p.add_argument('--output', type=Path, default=Path('output/evaluation.json'))
    args = parser.parse_args()
    try:
        if args.command == 'models':
            print('\n'.join(local_models()))
        elif args.command == 'inventory':
            if not args.folder.is_dir():
                raise ValueError('Input folder does not exist')
            rows = inventory(args.folder)
            write_json(args.output, rows)
            print(f'{len(rows)} PDFs; {sum(r.get("pages", 0) for r in rows)} pages. Saved {args.output}')
        elif args.command == 'extract':
            target, result = extract(args.pdf, args.output, args.model, args.vision_model, args.max_pages, args.force_vision, args.ocr, args.engine)
            print(f'Saved {target}; complete={result["complete"]}. Review values before use.')
            if any(p['status'] == 'error' for p in result['pages']):
                return 1
        elif args.command == 'evaluate':
            result = evaluate(json.loads(args.extraction.read_text(encoding='utf-8-sig')),
                              json.loads(args.labels.read_text(encoding='utf-8-sig')))
            write_json(args.output, result)
            print(f'Evaluated {result["evaluated_fields"]} fields; correct={result["correct_fields"]}')
        else:
            s = Scenario.model_validate_json(args.scenario.read_text(encoding='utf-8-sig'))
            write_json(args.output, analyze(s))
            print(f'Saved {args.output}')
    except Exception as exc:
        parser.exit(1, f'Error: {exc}\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
